from protocol import build_frame, OPERATION_READ, OPERATION_WRITE


def build_empty_read_frame():
    # Empty read will wake the device or get and ACK
    frame = build_frame(OPERATION_READ, 0x0000, [], 0)
    return frame


def build_registers_read_frame(address, length):
    frame = build_frame(OPERATION_READ, address, [], length)
    return frame


def build_registers_write_frame(address, data):
    frame = build_frame(OPERATION_WRITE, address, data, len(data))
    return frame
