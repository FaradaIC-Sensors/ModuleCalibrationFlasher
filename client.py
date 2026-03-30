from protocol import build_frame, OPERATION_READ, OPERATION_WRITE
from registers import REGISTERS_PAGE_SIZE


def build_empty_read_frame():
    # Empty read will wake the device or get and ACK
    frame = build_frame(OPERATION_READ, 0x0000, [], 0)
    return frame


def build_registers_read_full_register_pageframe():
    frame = build_frame(OPERATION_READ, 0x0000, [], REGISTERS_PAGE_SIZE)
    return frame


def build_registers_write_frame(address, data):
    frame = build_frame(OPERATION_WRITE, address, data, len(data))
    return frame
