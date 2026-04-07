from protocol import (
    BLULOG_MAX_PAYLOAD_SIZE,
    OPERATION_READ,
    OPERATION_WRITE,
    blulog_build_frame,
    build_frame,
)
from registers import REGISTERS_PAGE_SIZE


def build_empty_read_frame(protocol="faradaic"):
    _build = blulog_build_frame if protocol == "blulog" else build_frame
    return _build(OPERATION_READ, 0x0000, [], 0)


def build_registers_read_frame(address, length, protocol="faradaic"):
    if protocol == "blulog" and length > BLULOG_MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Blulog protocol supports up to {BLULOG_MAX_PAYLOAD_SIZE} data bytes per read frame"
        )
    _build = blulog_build_frame if protocol == "blulog" else build_frame
    return _build(OPERATION_READ, address, [], length)


def build_registers_read_full_register_pageframe(protocol="faradaic"):
    return build_registers_read_frame(0x0000, REGISTERS_PAGE_SIZE, protocol)


def build_registers_write_frame(address, data, protocol="faradaic"):
    if protocol == "blulog" and len(data) > BLULOG_MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Blulog protocol supports up to {BLULOG_MAX_PAYLOAD_SIZE} data bytes per write frame"
        )
    _build = blulog_build_frame if protocol == "blulog" else build_frame
    return _build(OPERATION_WRITE, address, data, len(data))
