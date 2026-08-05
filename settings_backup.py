"""Settings/script backup and restore for the v1.11 -> v1.17 firmware migration.

The register offsets of the persisted settings block (0x7C-0xCB) plus REG_CONFIG
are identical in firmware v1.11 and v1.17, so a plain register dump migrates
cleanly. What breaks on upgrade is the flash settings structure version (3 -> 4):
v1.17 sees the mismatch on first boot and overwrites every stored setting with
defaults. Capturing the registers and the measurement script before flashing and
writing them back afterwards restores the module.

v1.17 also replaced the separate Blulog firmware image with REG_CONFIG_FIRMWARE
(0x4A), so a module that used to run the Blulog build needs that bit set during
the restore. v1.11 has no such register, so it is derived from the protocol the
backup was captured with.

Functions here are pure: reading and writing frames stays in main.py.
"""

import re
import time

from module import Module
from protocol import BLULOG_MAX_PAYLOAD_SIZE
from registers import Registers, REGISTERS_PAGE_SIZE, SCRIPT_PAGE1

BACKUP_FORMAT = "faradaic-fe-module-settings"
BACKUP_FORMAT_VERSION = 1

# The firmware holds the script in a 1024 byte buffer, but only pages 0x01 and
# 0x02 are addressable, so a read may not start past offset 511.
SCRIPT_BUFFER_SIZE = 1024
SCRIPT_PAGE_BASE_ADDRESS = int(SCRIPT_PAGE1) << 8
SCRIPT_MAX_READ_OFFSET = 511

CONFIG_FIRMWARE_PROTOCOL_MAIN = 0
CONFIG_FIRMWARE_PROTOCOL_BLULOG = 1

# REG_CONFIG bit 0: 0 = STOP2 idle, 1 = standby idle.
REG_CONFIG_IDLE_MODE_STANDBY_MASK = 0x01
# REG_CONFIG_FIRMWARE bit 0: 0 = main wire protocol, 1 = blulog.
REG_CONFIG_FIRMWARE_BLULOG_MASK = 0x01

RH_POTENTIALS_COUNT = 10


SCRIPT_SAFE_CHUNK_SIZE = 256


def script_read_plan(protocol="faradaic", max_chunk=None):
    """(address, length) pairs covering as much of the script buffer as the protocol allows.

    The main protocol reads the whole buffer in one frame. Blulog caps a payload
    at 248 bytes and cannot address a read past offset 511, so it reaches the
    first 744 bytes only. Pass max_chunk=SCRIPT_SAFE_CHUNK_SIZE for a plan that
    stays clear of the firmware's payload bound checks, at the cost of only
    covering the two addressable pages.
    """
    limit = BLULOG_MAX_PAYLOAD_SIZE if protocol == "blulog" else SCRIPT_BUFFER_SIZE
    if max_chunk:
        limit = min(limit, max_chunk)
    plan = []
    offset = 0
    while offset < SCRIPT_BUFFER_SIZE and offset <= SCRIPT_MAX_READ_OFFSET:
        length = min(limit, SCRIPT_BUFFER_SIZE - offset)
        plan.append((SCRIPT_PAGE_BASE_ADDRESS + offset, length))
        offset += length
    return plan


def script_write_address():
    """v1.17 only accepts a full script upload at page 0x01, offset 0x00."""
    return SCRIPT_PAGE_BASE_ADDRESS


def decode_script(raw_bytes):
    """Strip the zero fill after the stored script and decode the remaining text."""
    data = bytes(bytearray(raw_bytes)).rstrip(b"\x00")
    try:
        return data.decode("ascii")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def encode_script(text):
    return list(bytearray(text.encode("latin-1")))


# v1.17 dropped the H1-era `5V` command and the `CE_BUF` pin from the script
# parser, so a script carrying either is rejected on upload with
# CMD_PARSE_ERROR_UNKNOWN_CMD or CMD_PARSE_ERROR_PIN_UNKNOWN_PIN.
_LINE_SPLIT = re.compile(r"(\r\n|\r|\n)")


def is_removed_command(line):
    """True if the line is a `5V` command or a `PIN CE_BUF` command."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False

    # tokens[0] is the timestamp; tokens[1] is the command keyword.
    tokens = stripped.split()
    if len(tokens) < 2:
        return False

    command = tokens[1]
    if command == "5V":
        return True
    if command == "PIN" and len(tokens) >= 3 and tokens[2] == "CE_BUF":
        return True
    return False


def _split_keepends(text):
    """Split on CR/LF/CRLF only, keeping the terminators attached."""
    parts = _LINE_SPLIT.split(text)
    lines = [parts[i] + parts[i + 1] for i in range(0, len(parts) - 1, 2)]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def strip_unsupported_commands(text):
    """Drop lines v1.17 cannot parse. Returns (cleaned_text, removed_lines)."""
    kept = []
    removed = []
    for line in _split_keepends(text):
        if is_removed_command(line):
            removed.append(line.strip())
        else:
            kept.append(line)
    return "".join(kept), removed


def _rh_potentials_list(mod):
    return [int(getattr(mod, f"rh_potentials_tbl_{i}")) for i in range(RH_POTENTIALS_COUNT)]


def _apply_rh_potentials(mod, values):
    for i in range(RH_POTENTIALS_COUNT):
        value = values[i] if i < len(values) else 0
        setattr(mod, f"rh_potentials_tbl_{i}", int(value) & 0xFFFF)


def settings_from_module(mod):
    """Every register value that the firmware persists in flash settings."""
    return {
        "module_id": int(mod.module_id),
        "config": int(mod.config) & 0xFF,
        "config_firmware": int(getattr(mod, "config_firmware", 0)) & 0xFF,
        "gain": mod.gain,
        "zero_offset": mod.zero_offset,
        "measurements_offset": int(mod.measurements_offset),
        "average_num": int(mod.average_num),
        "calibration_intercept": mod.calibration_intercept,
        "calibration_current": mod.calibration_current,
        "calibration_humidity": mod.calibration_humidity,
        "calibration_temperature": mod.calibration_temperature,
        "calibration_temperature_current": mod.calibration_temperature_current,
        "calibration_timestamp": int(mod.calibration_timestamp),
        "calibration_mae": mod.calibration_mae,
        "calibration_r2": mod.calibration_r2,
        "calibration_period": int(mod.calibration_period),
        "calibration_bound_low": int(mod.calibration_bound_low),
        "calibration_bound_high": int(mod.calibration_bound_high),
        "concentration_bound_low": int(mod.concentration_bound_low),
        "concentration_bound_high": int(mod.concentration_bound_high),
        "sensor_id": int(mod.sensor_id),
        "rh_potentials_tbl": _rh_potentials_list(mod),
    }


def apply_settings_to_module(mod, settings):
    mod.module_id = int(settings.get("module_id", 0)) & 0xFFFFFFFF
    mod.config = int(settings.get("config", 0)) & 0xFF
    mod.config_firmware = int(settings.get("config_firmware", 0)) & 0xFF
    mod.gain = float(settings.get("gain", 0.0) or 0.0)
    mod.zero_offset = float(settings.get("zero_offset", 0.0) or 0.0)
    mod.measurements_offset = int(settings.get("measurements_offset", 0)) & 0xFFFF
    mod.average_num = int(settings.get("average_num", 0)) & 0xFFFF
    mod.calibration_intercept = float(settings.get("calibration_intercept", 0.0) or 0.0)
    mod.calibration_current = float(settings.get("calibration_current", 0.0) or 0.0)
    mod.calibration_humidity = float(settings.get("calibration_humidity", 0.0) or 0.0)
    mod.calibration_temperature = float(settings.get("calibration_temperature", 0.0) or 0.0)
    mod.calibration_temperature_current = float(
        settings.get("calibration_temperature_current", 0.0) or 0.0
    )
    mod.calibration_timestamp = int(settings.get("calibration_timestamp", 0)) & 0xFFFFFFFF
    mod.calibration_mae = float(settings.get("calibration_mae", 0.0) or 0.0)
    mod.calibration_r2 = float(settings.get("calibration_r2", 0.0) or 0.0)
    mod.calibration_period = int(settings.get("calibration_period", 0)) & 0xFFFFFFFF
    mod.calibration_bound_low = int(settings.get("calibration_bound_low", 0)) & 0xFF
    mod.calibration_bound_high = int(settings.get("calibration_bound_high", 0)) & 0xFF
    mod.concentration_bound_low = int(settings.get("concentration_bound_low", 0)) & 0xFF
    mod.concentration_bound_high = int(settings.get("concentration_bound_high", 0)) & 0xFF
    mod.sensor_id = int(settings.get("sensor_id", 0)) & 0xFFFFFFFF
    _apply_rh_potentials(mod, settings.get("rh_potentials_tbl", []))
    return mod


def build_backup(page_bytes, script_bytes, port="", protocol="faradaic"):
    """Turn a raw register page and script buffer into the JSON payload."""
    page = list(page_bytes)
    mod = Module()
    if not mod.deserialize(page):
        raise ValueError(
            f"register page too short: expected {int(REGISTERS_PAGE_SIZE)} bytes, got {len(page)}"
        )

    settings = settings_from_module(mod)
    # v1.11 has no REG_CONFIG_FIRMWARE; the wire protocol was baked into the image.
    settings["config_firmware"] = (
        CONFIG_FIRMWARE_PROTOCOL_BLULOG if protocol == "blulog" else CONFIG_FIRMWARE_PROTOCOL_MAIN
    )

    # The stored script is cleaned here so the saved file is ready to upload to
    # v1.17; raw.script_hex keeps the module's original bytes for reference.
    script_raw = bytes(bytearray(script_bytes)).rstrip(b"\x00")
    script_text, removed_lines = strip_unsupported_commands(decode_script(script_raw))
    return {
        "format": BACKUP_FORMAT,
        "format_version": BACKUP_FORMAT_VERSION,
        "source": {
            "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "port": port,
            "protocol": protocol,
            "module_id": int(mod.module_id),
            "firmware_version": f"{mod.firmware_ver_major}.{mod.firmware_ver_minor}",
            "register_map_version": f"{mod.register_map_ver_major}.{mod.register_map_ver_minor}",
        },
        "settings": settings,
        "script": script_text,
        "script_removed_lines": removed_lines,
        "raw": {
            "register_page_hex": bytes(bytearray(page)).hex(),
            "script_hex": script_raw.hex(),
        },
    }


def parse_backup(payload):
    """Validate a backup dict and return (Module, script_bytes, removed_lines).

    The unsupported-command filter runs again here so hand-edited files, and
    files written before the filter existed, still upload cleanly.
    """
    if not isinstance(payload, dict):
        raise ValueError("backup file must contain a JSON object")
    if payload.get("format") != BACKUP_FORMAT:
        raise ValueError(f"unexpected format {payload.get('format')!r}, expected {BACKUP_FORMAT!r}")
    version = payload.get("format_version")
    if version != BACKUP_FORMAT_VERSION:
        raise ValueError(
            f"unsupported format_version {version!r}, this build writes {BACKUP_FORMAT_VERSION}"
        )
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("backup file has no 'settings' object")

    mod = apply_settings_to_module(Module(), settings)

    script = payload.get("script")
    if not (isinstance(script, str) and script):
        script_hex = (payload.get("raw") or {}).get("script_hex") or ""
        script = decode_script(bytearray.fromhex(script_hex)) if script_hex else ""
    script, removed_lines = strip_unsupported_commands(script)
    return mod, (encode_script(script) if script else []), removed_lines


def apply_v17_defaults(mod):
    """Force standby idle mode and the Blulog wire protocol on before a restore.

    Both are required on the migrated fleet regardless of what the v1.11 module
    was configured for, so they are set rather than restored. Only bit 0 of each
    register is touched. Returns a note per bit that was not already set.
    """
    notes = []
    if not mod.config & REG_CONFIG_IDLE_MODE_STANDBY_MASK:
        notes.append("forcing idle mode to standby (REG_CONFIG bit 0)")
    if not mod.config_firmware & REG_CONFIG_FIRMWARE_BLULOG_MASK:
        notes.append("forcing wire protocol to Blulog (REG_CONFIG_FIRMWARE bit 0)")
    mod.config |= REG_CONFIG_IDLE_MODE_STANDBY_MASK
    mod.config_firmware |= REG_CONFIG_FIRMWARE_BLULOG_MASK
    return notes


def settings_write_blocks(mod, write_config_firmware=True):
    """(name, address, data) blocks covering every writable settings register.

    Together these span 0x7C-0xCB plus REG_CONFIG and REG_CONFIG_FIRMWARE, which
    is exactly what REG_CONTROL_STORE_SETTINGS_TO_FLASH persists.
    """
    blocks = [
        ("module config", *mod.serialize_module_config()),
        ("calibration", *mod.serialize_calibration_config()),
        ("rh potentials", *mod.serialize_rh_potentials()),
        ("config", *mod.serialize_config()),
    ]
    if write_config_firmware:
        blocks.append(("firmware config", *mod.serialize_config_firmware()))
    return blocks


def verify_settings(expected_mod, actual_mod):
    """Field names whose values differ between the backup and the module read back."""
    expected = settings_from_module(expected_mod)
    actual = settings_from_module(actual_mod)
    return [name for name, value in expected.items() if actual.get(name) != value]


def default_backup_filename(module_id, firmware_version=""):
    suffix = f"_v{firmware_version}" if firmware_version else ""
    return f"F{int(module_id)}{suffix}_settings.json"
