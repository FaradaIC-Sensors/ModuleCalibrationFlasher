import time
import json
import ctypes
import glob
import threading
import os
import sys
import subprocess
import tkinter as tk
from enum import IntEnum
from tkinter import ttk, filedialog
import serial.tools.list_ports

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

APP_VERSION = "0.5"
APP_WINDOW_TITLE = f"FaradaIC Module Calibration Flasher v{APP_VERSION}"
SECTION_HEADER_FONT = ("TkDefaultFont", 10, "bold")

from module import Module
from connection import send_frame
from client import (
    build_registers_read_frame,
    build_registers_write_frame,
)
from protocol import (
    BLULOG_MAX_PAYLOAD_SIZE,
    OPERATION_READ,
    OPERATION_WRITE,
    blulog_process_frame,
    process_frame,
)
from registers import REGISTERS_PAGE_SIZE
import settings_backup


# ---------------- Utility -----------------


def configure_process_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def set_window_icon(root):
    ico_path = os.path.join(APP_DIR, "assets", "app.ico")
    if sys.platform == "win32" and os.path.isfile(ico_path):
        try:
            root.iconbitmap(ico_path)
            return
        except tk.TclError:
            pass

    png_path = os.path.join(APP_DIR, "assets", "app.png")
    if os.path.isfile(png_path):
        try:
            icon = tk.PhotoImage(file=png_path)
            root.iconphoto(True, icon)
            root._app_icon = icon
        except tk.TclError:
            pass


def discover_ports():
    ports = []

    def add_port(name):
        if not name:
            return
        if name.upper() == "COM1":
            return
        if name not in ports:
            ports.append(name)

    for p in serial.tools.list_ports.comports():
        add_port(p.device)

    if os.name != "nt":
        for name in glob.glob("/dev/ttyCH*"):
            add_port(name)

    def sort_key(v):
        try:
            if v.upper().startswith("COM"):
                return (0, int(v[3:]))
        except ValueError:
            pass
        return (1, v.lower())

    ports.sort(key=sort_key)
    return ports


DISCOVER_PORT_TIMEOUT = 2  # seconds per port


def _read_module_id_on_port(port: str, protocol: str = "faradaic"):
    try:
        data, error = _read_register_page(port, protocol)
        if error or not data:
            return None
        tmp = Module()
        if not tmp.deserialize(data):
            return None
        return getattr(tmp, "module_id", None)
    except Exception:
        return None


def _read_module_id_with_timeout(port: str, protocol: str = "faradaic"):
    result = [None]

    def _worker():
        result[0] = _read_module_id_on_port(port, protocol)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=DISCOVER_PORT_TIMEOUT)
    if t.is_alive():
        log(f"{port}: timed out after {DISCOVER_PORT_TIMEOUT}s — skipped")
        return None
    return result[0]


def action_discover_devices():
    ports = discover_ports()
    if not ports:
        log("No serial ports available for discovery")
        return
    protocol = _get_protocol()
    log(f"Starting discovery across {len(ports)} ports")
    found = []
    for p in ports:
        module_id = _read_module_id_with_timeout(p, protocol)
        if module_id is not None:
            log(f"{p}: F{int(module_id)}")
            found.append({"port": p, "module_id": int(module_id)})
        else:
            log(f"{p}: no frontend response")
    state["discovered_devices"] = found
    _update_discovered_list()
    log(f"Discovery complete — {len(found)} device(s) found")


def _update_discovered_list():
    lb = state.get("device_listbox")
    if not lb:
        return
    lb.delete(0, tk.END)
    for dev in state["discovered_devices"]:
        lb.insert(tk.END, f"{dev['port']}: F{dev['module_id']}")


def action_upload_calibration_all():
    devices = state.get("discovered_devices", [])
    if not devices:
        log("No discovered devices — run Discover first")
        return
    file_path = filedialog.askopenfilename(
        title="Open Calibration JSON (fleet)",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    if not file_path:
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            cal_data = json.load(f)
    except Exception as e:
        log(f"JSON load error: {e}")
        return

    for dev in devices:
        port = dev["port"]
        mid = dev["module_id"]
        key = _calibration_module_key(mid)
        entry = _get_calibration_entry(cal_data, mid)
        if not entry:
            log(f"{port}: key {key} not found in JSON — skipped")
            continue
        protocol = _get_protocol()
        try:
            tmp = Module()
            tmp.module_id = mid
            _apply_calibration_entry_to_module(tmp, entry)
            tmp.calibration_timestamp = int(time.time()) & 0xFFFFFFFF

            addr, data = tmp.serialize_calibration_config()
            status, resp = send_frame(
                port, build_registers_write_frame(addr, data, protocol), OPERATION_WRITE, protocol
            )
            if not status:
                code, name = _decode_nack(resp, protocol)
                if name:
                    log(f"{port}: write calibration config failed — NACK code={code} ({name})")
                else:
                    log(f"{port}: write calibration config failed — no response or unknown error (resp={resp})")
                continue

            tmp.control_store_settings_to_flash()
            c_addr, c_data = tmp.serialize_control()
            status, resp = send_frame(
                port, build_registers_write_frame(c_addr, c_data, protocol), OPERATION_WRITE, protocol
            )
            if not status:
                code, name = _decode_nack(resp, protocol)
                if name:
                    log(f"{port}: flash store failed — NACK code={code} ({name})")
                else:
                    log(f"{port}: flash store failed — no response or unknown error (resp={resp})")
                continue
            log(f"{port}: calibration uploaded for {key}")
        except Exception as e:
            log(f"{port}: error uploading calibration — {e}")
            continue

    log("Calibration upload complete")



# -------------- GUI State ---------------
state = {
    "selected_port": "",
    "lock": threading.Lock(),
    "log_lines": [],
    "log_auto_scroll_var": None,
    "root": None,
    "log_widget": None,
    "port_var": None,
    "port_combo": None,
    "discovered_devices": [],
    "device_listbox": None,
    "protocol_var": None,
}

def _get_protocol():
    var = state.get("protocol_var")
    return var.get() if var else "faradaic"


FARADAIC_NACK_ERROR_MAP = {
    0: "PARSE_SUCCESS",
    1: "FRAME_ERROR_NULL_PTR",
    2: "FRAME_ERROR_FIRST_NOT_STX",
    3: "FRAME_ERROR_LAST_NOT_ETX",
    4: "FRAME_ERROR_LENGTH_MISMATCH",
    5: "FRAME_ERROR_INVALID_OPERATION",
    6: "FRAME_ERROR_INVALID_ADDRESS",
    7: "CONTROL_ERROR_SCRIPT_IN_PROGRESS",
    51: "CMD_PARSE_ERROR_NULL_POINTER",
    52: "CMD_PARSE_ERROR_BUFFER_TOO_SMALL",
    53: "CMD_PARSE_ERROR_LINE_EMPTY",
    54: "CMD_PARSE_ERROR_LINE_TOO_SHORT",
    55: "CMD_PARSE_ERROR_INVALID_TIMESTAMP",
    56: "CMD_PARSE_ERROR_UNKNOWN_CMD",
    60: "CMD_PARSE_ERROR_PIN_MISSING_PARAMS",
    61: "CMD_PARSE_ERROR_PIN_UNKNOWN_PIN",
    62: "CMD_PARSE_ERROR_PIN_INVALID_STATE",
    70: "CMD_PARSE_ERROR_WE_MISSING_PARAMS",
    71: "CMD_PARSE_ERROR_WE_INVALID_POTENTIAL",
    80: "CMD_PARSE_ERROR_RE_MISSING_PARAMS",
    81: "CMD_PARSE_ERROR_RE_INVALID_POTENTIAL",
    90: "CMD_PARSE_ERROR_ADC_MISSING_PARAMS",
    91: "CMD_PARSE_ERROR_ADC_INVALID_PERIOD",
    92: "CMD_PARSE_ERROR_ADC_INVALID_SAMPLING_TIME",
    93: "CMD_PARSE_ERROR_ADC_INVALID_OVERSAMPLING",
    94: "CMD_PARSE_ERROR_5V_MISSING_PARAMS",
    95: "CMD_PARSE_ERROR_5V_WRONG_PARAMS",
    100: "SCRIPT_PARSE_ERROR_NULL_PTR",
    101: "SCRIPT_PARSE_ERROR_LINE_TOO_LONG",
    102: "SCRIPT_PARSE_ERROR_CMD_BUFFER_FULL",
    103: "SCRIPT_PARSE_ERROR_NO_VALID_COMMANDS",
    200: "SCRIPT_VALIDATION_ERROR_WE_POTENTIAL_RANGE",
    201: "SCRIPT_VALIDATION_ERROR_RE_POTENTIAL_RANGE",
    202: "SCRIPT_VALIDATION_ERROR_NO_BEGIN",
    203: "SCRIPT_VALIDATION_ERROR_NO_END",
    204: "SCRIPT_VALIDATION_ERROR_BEGIN_NOT_FIRST",
    205: "SCRIPT_VALIDATION_ERROR_END_NOT_LAST",
    206: "SCRIPT_VALIDATION_ERROR_TIMESTAMPS_NOT_ASCENDING",
    207: "SCRIPT_VALIDATION_ERROR_ADC_MISSING_STOP",
    208: "SCRIPT_VALIDATION_ERROR_ADC_INVALID_SAMPLING_TIME",
    209: "SCRIPT_VALIDATION_ERROR_ADC_INVALID_OVERSAMPLING",
    220: "SCRIPT_SAVE_TO_FLASH_FAILED",
}


BLULOG_NACK_ERROR_MAP = dict(FARADAIC_NACK_ERROR_MAP)
BLULOG_NACK_ERROR_MAP.update(
    {
        2: "FRAME_ERROR_INVALID_LENGTH_PREFIX",
        3: "FRAME_ERROR_FRAME_SIZE_MISMATCH",
        8: "FRAME_ERROR_CRC_MISMATCH",
    }
)


def _decode_nack(response_bytes, protocol="faradaic"):
    if not response_bytes or len(response_bytes) < 3:
        return None, None
    code = response_bytes[2]
    error_map = BLULOG_NACK_ERROR_MAP if protocol == "blulog" else FARADAIC_NACK_ERROR_MAP
    name = error_map.get(code)
    return code, name


# -------------- Logging -----------------
MAX_LOG_LINES = 5000


def log(msg: str):
    ts_line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    root = state.get("root")
    if not root:
        return

    def _append():
        log_widget = state.get("log_widget")
        if not log_widget:
            return
        log_widget.configure(state="normal")
        log_widget.insert("end", ts_line + "\n")
        state["log_lines"].append(ts_line)
        if len(state["log_lines"]) > MAX_LOG_LINES:
            excess = len(state["log_lines"]) - MAX_LOG_LINES
            log_widget.delete("1.0", f"{excess + 1}.0")
            state["log_lines"] = state["log_lines"][-MAX_LOG_LINES:]
        log_widget.configure(state="disabled")
        auto_var = state.get("log_auto_scroll_var")
        if auto_var and auto_var.get():
            log_widget.see("end")

    try:
        root.after_idle(_append)
    except RuntimeError:
        pass


def clear_log():
    log_widget = state.get("log_widget")
    if not log_widget:
        return
    log_widget.configure(state="normal")
    log_widget.delete("1.0", "end")
    log_widget.configure(state="disabled")
    state["log_lines"] = []


def copy_log():
    root = state.get("root")
    if root:
        root.clipboard_clear()
        root.clipboard_append("\n".join(state.get("log_lines", [])))


# --------------- Calibration Helpers ---------------


def _apply_calibration_entry_to_module(mod, entry):
    def _get(name, default=0.0):
        return entry.get(name, default)

    mod.calibration_intercept = float(_get("intercept", 0.0) or 0.0)
    mod.calibration_current = float(_get("current_param", 0.0) or 0.0)
    mod.calibration_humidity = float(_get("rh_param", 0.0) or 0.0)
    mod.calibration_temperature = float(_get("temp_param", 0.0) or 0.0)
    if hasattr(mod, "calibration_mae"):
        try:
            mod.calibration_mae = float(_get("mae", 0.0) or 0.0)
        except Exception:
            pass
    if hasattr(mod, "calibration_r2"):
        try:
            mod.calibration_r2 = float(_get("r2", 0.0) or 0.0)
        except Exception:
            pass
    try:
        low = int(float(_get("lower_limit", 0)))
        high = int(float(_get("upper_limit", 0)))
        mod.calibration_bound_low = max(0, min(255, low))
        mod.calibration_bound_high = max(0, min(255, high))
    except Exception as ce:
        log(f"Boundary parse error: {ce}")
    if hasattr(mod, "sensor_id"):
        try:
            mod.sensor_id = int(_get("sensor_id", 0)) & 0xFFFFFFFF
        except Exception:
            pass
    if hasattr(mod, "calibration_period"):
        try:
            mod.calibration_period = int(_get("period", 0)) & 0xFFFFFFFF
        except Exception:
            pass
    try:
        mod.measurements_offset = int(float(_get("measurement_offset", 0)))
    except Exception:
        pass
    try:
        mod.average_num = int(float(_get("averaging_number", 0)))
    except Exception:
        pass
    try:
        c_low = int(float(_get("concentration_lower_limit", 0)))
        c_high = int(float(_get("concentration_upper_limit", 0)))
        mod.concentration_bound_low = max(0, min(255, c_low))
        mod.concentration_bound_high = max(0, min(255, c_high))
    except Exception:
        pass
    if hasattr(mod, "calibration_temperature_current"):
        try:
            mod.calibration_temperature_current = float(_get("IT_param", 0.0) or 0.0)
        except Exception:
            pass


def _calibration_module_key(module_id):
    return f"F{int(module_id)}"


def _get_calibration_entry(data, module_id):
    key = _calibration_module_key(module_id)
    return data.get(key) or data.get(f"{key}-0")


def _read_registers(port, address, length, protocol):
    _process = blulog_process_frame if protocol == "blulog" else process_frame
    try:
        request = build_registers_read_frame(address, length, protocol)
    except ValueError as e:
        return None, str(e)

    status, response = send_frame(port, request, OPERATION_READ, protocol)
    if not status:
        code, name = _decode_nack(response, protocol)
        if name:
            return None, f"{port}: register read failed - NACK code={code} ({name})"
        if response:
            return None, f"{port}: register read failed - invalid response ({response})"
        return None, f"{port}: register read failed - no response"

    data = _process(response)
    if data is None:
        return None, f"{port}: register read failed - invalid frame"
    if len(data) != length:
        return None, f"{port}: register read failed - expected {length} bytes, got {len(data)}"
    return data, None


def _read_register_page(port, protocol):
    if protocol != "blulog":
        return _read_registers(port, 0x0000, REGISTERS_PAGE_SIZE, protocol)

    page = []
    offset = 0
    while offset < REGISTERS_PAGE_SIZE:
        chunk_len = min(REGISTERS_PAGE_SIZE - offset, BLULOG_MAX_PAYLOAD_SIZE)
        chunk, error = _read_registers(port, offset, chunk_len, protocol)
        if error:
            return None, error
        page.extend(chunk)
        offset += chunk_len
    return page, None


def _write_registers(port, address, data, protocol, what):
    """Write one register block, logging the decoded NACK on failure."""
    try:
        request = build_registers_write_frame(address, data, protocol)
    except ValueError as e:
        log(f"{port}: {what} write failed - {e}")
        return False

    status, response = send_frame(port, request, OPERATION_WRITE, protocol)
    if status:
        return True
    code, name = _decode_nack(response, protocol)
    if name:
        log(f"{port}: {what} write failed - NACK code={code} ({name})")
    elif response:
        log(f"{port}: {what} write failed - unexpected response ({response})")
    else:
        log(f"{port}: {what} write failed - no response")
    return False


def _read_script_with_plan(port, protocol, plan):
    script = []
    for address, length in plan:
        chunk, error = _read_registers(port, address, length, protocol)
        if error:
            return None, error
        script.extend(chunk)
    return script, None


def _read_script(port, protocol):
    """Read the measurement script buffer as far as the protocol can address it.

    A full-buffer read sits right on the firmware's payload bound check, so fall
    back to page-sized reads if the module rejects it.
    """
    script, error = _read_script_with_plan(
        port, protocol, settings_backup.script_read_plan(protocol)
    )
    if not error:
        return script, None

    log(f"{port}: full script read rejected, retrying page by page - {error}")
    return _read_script_with_plan(
        port,
        protocol,
        settings_backup.script_read_plan(protocol, settings_backup.SCRIPT_SAFE_CHUNK_SIZE),
    )


# --------------- Device Actions ---------------


def _read_module_broken(port, protocol=None):
    return _read_module(port, protocol)
    """Read full register page and return a deserialized Module, or None on failure."""
    if protocol is None:
        protocol = _get_protocol()
    data, error = _read_register_page(port, protocol)
    if not status:
        log(f"{port}: register read failed — no response")
        return None
    data = _process(frame)
    if not data:
        log(f"{port}: register read failed — invalid frame")
        return None
    tmp = Module()
    if not tmp.deserialize(data):
        log(f"{port}: register read failed — deserialization error")
        return None
    return tmp


def _read_module(port, protocol=None):
    """Read full register page and return a deserialized Module, or None on failure."""
    if protocol is None:
        protocol = _get_protocol()
    data, error = _read_register_page(port, protocol)
    if error:
        log(error)
        return None
    if not data:
        log(f"{port}: register read failed - empty payload")
        return None
    tmp = Module()
    if not tmp.deserialize(data):
        log(f"{port}: register read failed - deserialization error")
        return None
    return tmp


def action_read_info():
    port = state["selected_port"]
    if not port:
        log("No serial port selected")
        return
    result = _read_module(port, _get_protocol())
    if not result:
        log("Read info failed")
        return
    log(f"ModuleId: {result.module_id}")
    log(f"Firmware Version: {result.firmware_ver_major}.{result.firmware_ver_minor}")
    log(f"Register Map Version: {result.register_map_ver_major}.{result.register_map_ver_minor}")
    log(f"Idle Mode: {_idle_mode_label(result.config)} (REG_CONFIG 0x{result.config:02X})")


def action_get_module_settings_v11():
    """Back up settings and measurement script of a module still running v1.11."""
    port = state["selected_port"]
    if not port:
        log("No serial port selected")
        return
    protocol = _get_protocol()

    page, error = _read_register_page(port, protocol)
    if error:
        log(error)
        return

    script, error = _read_script(port, protocol)
    if error:
        log(f"{port}: script read failed, backing up settings only - {error}")
        script = []

    try:
        backup = settings_backup.build_backup(page, script, port, protocol)
    except ValueError as e:
        log(f"{port}: backup failed - {e}")
        return

    source = backup["source"]
    firmware_version = source["firmware_version"]
    if firmware_version != "1.11":
        log(f"{port}: warning - module reports firmware {firmware_version}, expected 1.11")

    module_id = source["module_id"]
    script_text = backup["script"]
    log(
        f"{port}: F{module_id} firmware {firmware_version}, "
        f"register map {source['register_map_version']}"
    )
    log(f"{port}: script {len(script_text)} bytes, {len(script_text.splitlines())} line(s)")
    for removed in backup["script_removed_lines"]:
        log(f"{port}: dropped script line not supported by v1.17: {removed}")
    if not script_text:
        log(f"{port}: warning - module returned an empty script")

    file_path = filedialog.asksaveasfilename(
        title="Save Module Settings (v1.11)",
        defaultextension=".json",
        initialfile=settings_backup.default_backup_filename(module_id, firmware_version),
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    if not file_path:
        log("Backup cancelled")
        return
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2)
    except OSError as e:
        log(f"Backup save error: {e}")
        return
    log(f"{port}: settings saved to {file_path}")


def action_write_module_settings_v17():
    """Restore a backup onto a module that has been re-flashed with v1.17."""
    port = state["selected_port"]
    if not port:
        log("No serial port selected")
        return
    protocol = _get_protocol()

    file_path = filedialog.askopenfilename(
        title="Open Module Settings JSON",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    if not file_path:
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        expected, script_bytes, removed_lines = settings_backup.parse_backup(payload)
    except (OSError, ValueError) as e:
        log(f"Backup load error: {e}")
        return
    for removed in removed_lines:
        log(f"Dropped script line not supported by v1.17: {removed}")
    forced = settings_backup.apply_v17_defaults(expected)

    current = _read_module(port, protocol)
    if not current:
        log(f"{port}: cannot reach module - aborting restore")
        return
    firmware_version = f"{current.firmware_ver_major}.{current.firmware_ver_minor}"
    if firmware_version != "1.17":
        log(f"{port}: warning - module reports firmware {firmware_version}, expected 1.17")
    log(f"{port}: restoring F{expected.module_id} from {os.path.basename(file_path)}")
    for note in forced:
        log(f"{port}: {note}")

    for what, address, data in settings_backup.settings_write_blocks(expected):
        if not _write_registers(port, address, data, protocol, what):
            log(f"{port}: restore aborted")
            return

    expected.control_store_settings_to_flash()
    address, data = expected.serialize_control()
    if not _write_registers(port, address, data, protocol, "store settings to flash"):
        log(f"{port}: restore aborted")
        return
    log(f"{port}: settings written and stored to flash")

    script_written = _restore_script(port, protocol, expected, script_bytes)

    time.sleep(0.1)
    verify = _read_module(port, protocol)
    if not verify:
        log(f"{port}: settings restored but read back failed - verify manually")
        return
    mismatched = settings_backup.verify_settings(expected, verify)
    if mismatched:
        log(f"{port}: verification mismatch on {', '.join(mismatched)}")
    else:
        log(f"{port}: verification passed")

    log(
        f"{port}: standby idle mode and the Blulog protocol take effect on the next reset - "
        "power-cycle the module, then talk to it with the Blulog protocol selected"
    )
    if script_written:
        log(f"{port}: migration complete")
    else:
        log(f"{port}: migration complete except for the script - see above")


def _restore_script(port, protocol, expected, script_bytes):
    """Upload the script and store it to flash. Returns False if it was skipped or failed."""
    if not script_bytes:
        log(f"{port}: backup holds no script - skipping script restore")
        return False
    if protocol == "blulog" and len(script_bytes) > BLULOG_MAX_PAYLOAD_SIZE:
        log(
            f"{port}: script is {len(script_bytes)} bytes and the Blulog protocol caps a frame at "
            f"{BLULOG_MAX_PAYLOAD_SIZE} - re-run the script restore over the FaradaIC protocol"
        )
        return False

    address = settings_backup.script_write_address()
    if not _write_registers(port, address, script_bytes, protocol, "script"):
        return False

    expected.control_store_script_to_flash()
    ctrl_address, ctrl_data = expected.serialize_control()
    if not _write_registers(port, ctrl_address, ctrl_data, protocol, "store script to flash"):
        return False
    log(f"{port}: script ({len(script_bytes)} bytes) written and stored to flash")
    return True


def _flash_firmware(firmware_filename):
    port = state["selected_port"]
    if not port:
        log("No serial port selected")
        return
    cwd = os.getcwd()
    programmer = os.path.join(cwd, "STM32CubeProgrammer", "bin", "STM32_PROGRAMMER_CLI.exe")
    firmware = os.path.join(cwd, "firmware", firmware_filename)
    if not os.path.isfile(programmer):
        log(f"STM32CubeProgrammer not found: {programmer}")
        return
    if not os.path.isfile(firmware):
        log(f"Firmware file not found: {firmware}")
        return
    flash_cmd = [programmer, "-c", f"port={port}", "br=115200", "-d", firmware, "-v", "-s"]
    log(f"[{port}] {' '.join(flash_cmd)}")
    log(f"[{port}] Firmware flashing started")

    def _worker():
        try:
            proc = subprocess.Popen(
                flash_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                log(line.rstrip())
            proc.wait()
            if proc.returncode != 0:
                log(f"[{port}] Flashing failed (exit code {proc.returncode})")
            else:
                log(f"[{port}] Firmware flashing completed successfully")
        except FileNotFoundError:
            log(f"[{port}] STM32CubeProgrammer CLI not found")
        except Exception as e:
            log(f"[{port}] Flashing error: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def action_flash_blulog_fw():
    _flash_firmware("Blulog_STM32L432_FEModule_v1.11_FM25L4J1.hex")


def action_flash_faradaic_fw():
    _flash_firmware("STM32L432_FEModule_v1.11_FM25L4J1.hex")


def action_run_sht40_measurement():
    port = state["selected_port"]
    if not port:
        log("No serial port selected")
        return
    protocol = _get_protocol()
    tmp = Module()
    tmp.control_start_sht40_measurement_set()
    addr, data = tmp.serialize_control()
    status, _ = send_frame(
        port, build_registers_write_frame(addr, data, protocol), OPERATION_WRITE, protocol
    )
    if not status:
        log("Failed to send SHT40 start control")
        return
    log("SHT40 measurement started")
    time.sleep(0.1)
    result = _read_module(port, protocol)
    if result:
        log(f"  Status:      0x{result.status:02X}")
        log(f"  Temperature: {result.temperature:.6f}")
        log(f"  Humidity:    {result.humidity:.6f}")
    else:
        log("  Read back failed")


class IdleMode(IntEnum):
    """REG_CONFIG bit 0: how the module idles between measurements."""

    SLEEP = 0
    STANDBY = 1


def _idle_mode_label(config):
    if config & settings_backup.REG_CONFIG_IDLE_MODE_STANDBY_MASK:
        return "Standby"
    return "Sleep (STOP2)"


def _set_idle_mode(mode):
    """Write REG_CONFIG bit 0 and store it to flash, leaving the other config bits alone.

    Read-modify-write: the UI only knows bit 0, but the firmware may define more.
    Takes effect on the next reset - power-cycle the module afterwards.
    """
    port = state["selected_port"]
    if not port:
        log("No serial port selected")
        return
    protocol = _get_protocol()

    current = _read_module(port, protocol)
    if not current:
        log(f"Set {_idle_mode_label(mode)} failed - cannot reach module")
        return
    previous_config = current.config & 0xFF

    mask = settings_backup.REG_CONFIG_IDLE_MODE_STANDBY_MASK
    if mode == IdleMode.STANDBY:
        current.config = previous_config | mask
    else:
        current.config = previous_config & ~mask & 0xFF

    address, data = current.serialize_config()
    if not _write_registers(port, address, data, protocol, "config"):
        return

    current.control_store_settings_to_flash()
    address, data = current.serialize_control()
    if not _write_registers(port, address, data, protocol, "store settings to flash"):
        return

    log(f"{port}: config 0x{previous_config:02X} -> 0x{current.config:02X} stored to flash")
    log(
        f"{port}: {_idle_mode_label(current.config)} takes effect on the next reset - "
        "power-cycle the module"
    )


def action_set_standby():
    _set_idle_mode(IdleMode.STANDBY)


def action_set_sleep():
    _set_idle_mode(IdleMode.SLEEP)


def action_start_measurement():
    port = state["selected_port"]
    if not port:
        log("No serial port selected")
        return
    protocol = _get_protocol()
    tmp = Module()
    tmp.control_start_measurement_set()
    addr, data = tmp.serialize_control()
    status, _ = send_frame(
        port, build_registers_write_frame(addr, data, protocol), OPERATION_WRITE, protocol
    )
    if not status:
        log("Failed to send measurement start control")
        return
    log("Measurement started")
    time.sleep(0.3)
    result = _read_module(port, protocol)
    if result:
        log(f"  Status:        0x{result.status:02X}")
        log(f"  Concentration: {result.concentration:.6f}")
        log(f"  Temperature:   {result.temperature:.6f}")
        log(f"  Humidity:      {result.humidity:.6f}")
        log(f"  Current:       {result.current:.6f}")
    else:
        log("  Read back failed")


# --------------- Port Selection ---------------


def refresh_ports_callback():
    ports = discover_ports()
    combo = state.get("port_combo")
    if combo:
        combo["values"] = ports
    if state["selected_port"] not in ports:
        state["selected_port"] = ports[0] if ports else ""
        port_var = state.get("port_var")
        if port_var:
            port_var.set(state["selected_port"])
    log("Ports refreshed")


def select_port_callback(event=None):
    port_var = state.get("port_var")
    if port_var:
        state["selected_port"] = port_var.get()
        log(f"Selected port: {state['selected_port']}")


# --------------- GUI Construction ---------------


def _build_fleet_col(parent):
    col = ttk.Frame(parent)

    ttk.Label(col, text="Protocol", font=SECTION_HEADER_FONT).pack(
        padx=4, pady=(4, 4), anchor=tk.W
    )
    protocol_var = tk.StringVar(value="faradaic")
    state["protocol_var"] = protocol_var
    radio_frame = ttk.Frame(col)
    radio_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
    ttk.Radiobutton(radio_frame, text="FaradaIC", variable=protocol_var, value="faradaic").pack(
        side=tk.LEFT, padx=(0, 8)
    )
    ttk.Radiobutton(radio_frame, text="Blulog", variable=protocol_var, value="blulog").pack(
        side=tk.LEFT
    )

    ttk.Label(col, text="Calibration Operations", font=SECTION_HEADER_FONT).pack(
        padx=4, pady=(4, 4), anchor=tk.W
    )

    btn_frame = ttk.Frame(col)
    btn_frame.pack(fill=tk.X, padx=4)
    ttk.Button(btn_frame, text="Discover", command=action_discover_devices).pack(
        fill=tk.X, pady=(0, 2)
    )
    ttk.Button(
        btn_frame, text="Upload Calibration", command=action_upload_calibration_all
    ).pack(fill=tk.X, pady=(0, 2))
    ttk.Separator(col, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4, pady=4)

    ttk.Label(col, text="Discovered Devices:").pack(padx=4, anchor=tk.W)
    lb = tk.Listbox(col, height=10, font=("Consolas", 9))
    lb.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 4))
    state["device_listbox"] = lb

    return col


def _build_device_col(parent):
    col = ttk.Frame(parent)

    ttk.Label(col, text="Device", font=SECTION_HEADER_FONT).pack(
        padx=4, pady=(4, 4), anchor=tk.W
    )

    port_frame = ttk.Frame(col)
    port_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
    ttk.Label(port_frame, text="Serial Port").pack(side=tk.LEFT, padx=(0, 4))
    port_var = tk.StringVar()
    combo = ttk.Combobox(
        port_frame, textvariable=port_var, values=discover_ports(), width=22
    )
    combo.pack(side=tk.LEFT)
    combo.bind("<<ComboboxSelected>>", select_port_callback)
    state["port_var"] = port_var
    state["port_combo"] = combo

    ttk.Button(col, text="Refresh Ports", command=refresh_ports_callback).pack(
        fill=tk.X, padx=4, pady=(0, 4)
    )

    ttk.Button(col, text="Read Info", command=action_read_info).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )
    ttk.Button(col, text="Run O2 Conc", command=action_start_measurement).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )
    ttk.Button(col, text="Run SHT40", command=action_run_sht40_measurement).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )
    ttk.Button(col, text="Set Standby", command=action_set_standby).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )
    ttk.Button(col, text="Set Sleep", command=action_set_sleep).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )

    ttk.Separator(col, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4, pady=4)
    ttk.Label(col, text="Migration", font=SECTION_HEADER_FONT).pack(
        padx=4, pady=(0, 4), anchor=tk.W
    )
    ttk.Button(
        col, text="Get Module Settings v11", command=action_get_module_settings_v11
    ).pack(fill=tk.X, padx=4, pady=(0, 2))
    ttk.Button(
        col, text="Write Module Settings v17", command=action_write_module_settings_v17
    ).pack(fill=tk.X, padx=4, pady=(0, 2))

    ttk.Separator(col, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4, pady=4)
    ttk.Label(col, text="Firmware", font=SECTION_HEADER_FONT).pack(
        padx=4, pady=(0, 4), anchor=tk.W
    )
    ttk.Button(col, text="Flash Blulog FW", command=action_flash_blulog_fw).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )
    ttk.Button(col, text="Flash FaradaIC FW", command=action_flash_faradaic_fw).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )

    return col


def _build_log_col(parent):
    col = ttk.Frame(parent)

    ctrl_frame = ttk.Frame(col)
    ctrl_frame.pack(fill=tk.X, padx=4, pady=4)
    auto_var = tk.BooleanVar(value=True)
    state["log_auto_scroll_var"] = auto_var
    ttk.Checkbutton(ctrl_frame, text="Auto Scroll", variable=auto_var).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    ttk.Button(ctrl_frame, text="Clear Log", command=clear_log).pack(
        side=tk.LEFT, padx=(0, 4)
    )
    ttk.Button(ctrl_frame, text="Copy Log", command=copy_log).pack(side=tk.LEFT)

    log_container = ttk.Frame(col)
    log_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
    log_text = tk.Text(
        log_container, state="disabled", wrap=tk.NONE, font=("Consolas", 9)
    )
    y_scroll = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=log_text.yview)
    x_scroll = ttk.Scrollbar(
        log_container, orient=tk.HORIZONTAL, command=log_text.xview
    )
    log_text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    log_text.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")
    log_container.grid_rowconfigure(0, weight=1)
    log_container.grid_columnconfigure(0, weight=1)
    state["log_widget"] = log_text

    return col


def create_gui():
    root = tk.Tk()
    root.title(APP_WINDOW_TITLE)
    root.geometry("800x600")
    set_window_icon(root)
    state["root"] = root

    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=1)

    paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
    paned.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

    fleet_col = _build_fleet_col(paned)
    fleet_col.configure(width=200)
    paned.add(fleet_col, weight=0)

    device_col = _build_device_col(paned)
    device_col.configure(width=180)
    paned.add(device_col, weight=0)

    log_col = _build_log_col(paned)
    log_col.configure(width=400)
    paned.add(log_col, weight=1)

    ports = discover_ports()
    if ports:
        state["selected_port"] = ports[0]
        state["port_var"].set(ports[0])

    return root


def run():
    configure_process_dpi_awareness()
    root = create_gui()
    root.mainloop()


if __name__ == "__main__":
    run()
