import time
import json
import ctypes
import threading
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog
import serial.tools.list_ports

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

APP_VERSION = "0.4"
APP_WINDOW_TITLE = f"FaradaIC Module Calibration Flasher v{APP_VERSION}"

from module import Module
from connection import send_frame
from client import (
    build_registers_read_full_register_pageframe,
    build_registers_write_frame,
)
from protocol import OPERATION_READ, OPERATION_WRITE, process_frame


# ---------------- Utility -----------------


def discover_ports():
    ports = []
    for p in serial.tools.list_ports.comports():
        name = p.device
        if name.upper() == "COM1":
            continue
        ports.append(name)

    def sort_key(v):
        try:
            if v.upper().startswith("COM"):
                return int(v[3:])
        except ValueError:
            pass
        return 9999

    ports.sort(key=sort_key)
    return ports


DISCOVER_PORT_TIMEOUT = 2  # seconds per port


def _read_module_id_on_port(port: str):
    try:
        status, frame = send_frame(
            port, build_registers_read_full_register_pageframe(), OPERATION_READ
        )
        if not status:
            return None
        data = process_frame(frame)
        if not data:
            return None
        tmp = Module()
        if not tmp.deserialize(data):
            return None
        return getattr(tmp, "module_id", None)
    except Exception:
        return None


def _read_module_id_with_timeout(port: str):
    result = [None]

    def _worker():
        result[0] = _read_module_id_on_port(port)

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
        log("No COM ports available for discovery")
        return
    log(f"Starting discovery across {len(ports)} ports")
    found = []
    for p in ports:
        module_id = _read_module_id_with_timeout(p)
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
        try:
            tmp = Module()
            tmp.module_id = mid
            _apply_calibration_entry_to_module(tmp, entry)
            tmp.calibration_timestamp = int(time.time()) & 0xFFFFFFFF

            addr, data = tmp.serialize_calibration_config()
            status, resp = send_frame(
                port, build_registers_write_frame(addr, data), OPERATION_WRITE
            )
            if not status:
                code, name = _decode_nack(resp)
                if name:
                    log(f"{port}: write calibration config failed — NACK code={code} ({name})")
                else:
                    log(f"{port}: write calibration config failed — no response or unknown error (resp={resp})")
                continue

            tmp.control_store_settings_to_flash()
            c_addr, c_data = tmp.serialize_control()
            status, resp = send_frame(
                port, build_registers_write_frame(c_addr, c_data), OPERATION_WRITE
            )
            if not status:
                code, name = _decode_nack(resp)
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
}

NACK_ERROR_MAP = {
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


def _decode_nack(response_bytes):
    if not response_bytes or len(response_bytes) < 3:
        return None, None
    code = response_bytes[2]
    name = NACK_ERROR_MAP.get(code)
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


# --------------- Device Actions ---------------


def _read_module(port):
    """Read full register page and return a deserialized Module, or None on failure."""
    status, frame = send_frame(
        port, build_registers_read_full_register_pageframe(), OPERATION_READ
    )
    if not status:
        log(f"{port}: register read failed — no response")
        return None
    data = process_frame(frame)
    if not data:
        log(f"{port}: register read failed — invalid frame")
        return None
    tmp = Module()
    if not tmp.deserialize(data):
        log(f"{port}: register read failed — deserialization error")
        return None
    return tmp


def action_read_info():
    port = state["selected_port"]
    if not port:
        log("No COM port selected")
        return
    result = _read_module(port)
    if not result:
        log("Read info failed")
        return
    log(f"ModuleId: {result.module_id}")
    log(f"Firmware Version: {result.firmware_ver_major}.{result.firmware_ver_minor}")
    log(f"Register Map Version: {result.register_map_ver_major}.{result.register_map_ver_minor}")


def action_run_sht40_measurement():
    port = state["selected_port"]
    if not port:
        log("No COM port selected")
        return
    tmp = Module()
    tmp.control_start_sht40_measurement_set()
    addr, data = tmp.serialize_control()
    status, _ = send_frame(
        port, build_registers_write_frame(addr, data), OPERATION_WRITE
    )
    if not status:
        log("Failed to send SHT40 start control")
        return
    log("SHT40 measurement started")
    time.sleep(0.1)
    result = _read_module(port)
    if result:
        log(f"  Status:      0x{result.status:02X}")
        log(f"  Temperature: {result.temperature:.6f}")
        log(f"  Humidity:    {result.humidity:.6f}")
    else:
        log("  Read back failed")


def action_start_measurement():
    port = state["selected_port"]
    if not port:
        log("No COM port selected")
        return
    tmp = Module()
    tmp.control_start_measurement_set()
    addr, data = tmp.serialize_control()
    status, _ = send_frame(
        port, build_registers_write_frame(addr, data), OPERATION_WRITE
    )
    if not status:
        log("Failed to send measurement start control")
        return
    log("Measurement started")
    time.sleep(0.25)
    result = _read_module(port)
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

    ttk.Label(col, text="Module Operations", font=("TkDefaultFont", 10, "bold")).pack(
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

    ttk.Label(col, text="Device", font=("TkDefaultFont", 10, "bold")).pack(
        padx=4, pady=(4, 4), anchor=tk.W
    )

    port_frame = ttk.Frame(col)
    port_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
    ttk.Label(port_frame, text="COM Port").pack(side=tk.LEFT, padx=(0, 4))
    port_var = tk.StringVar()
    combo = ttk.Combobox(
        port_frame, textvariable=port_var, values=discover_ports(), width=12
    )
    combo.pack(side=tk.LEFT)
    combo.bind("<<ComboboxSelected>>", select_port_callback)
    state["port_var"] = port_var
    state["port_combo"] = combo

    ttk.Button(col, text="Refresh Ports", command=refresh_ports_callback).pack(
        fill=tk.X, padx=4, pady=(0, 4)
    )

    ttk.Separator(col, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=4, pady=4)

    ttk.Button(col, text="Read Info", command=action_read_info).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )
    ttk.Button(col, text="Run O2 Conc", command=action_start_measurement).pack(
        fill=tk.X, padx=4, pady=(0, 2)
    )
    ttk.Button(col, text="Run SHT40", command=action_run_sht40_measurement).pack(
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
    ico_path = os.path.join(APP_DIR, "assets", "app.ico")
    if os.path.isfile(ico_path):
        root.iconbitmap(ico_path)
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
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    root = create_gui()
    root.mainloop()


if __name__ == "__main__":
    run()
