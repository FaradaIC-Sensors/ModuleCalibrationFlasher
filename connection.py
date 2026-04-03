import serial

from client import build_empty_read_frame
from protocol import (
    FRAME_LEN_LSB_POS,
    FRAME_LEN_MSB_POS,
    OPERATION_READ,
    OPERATION_WRITE,
    RESPONSE_ACK_LONG,
    RESPONSE_ACK_SHORT,
    RESPONSE_NACK,
    RESPONSE_READY,
    parse_response,
)


SERIAL_TIMEOUT_S = 0.5


def _read_response_frame(ser):
    raw_bytes = []

    resp = ser.read(1)
    if not resp:
        return raw_bytes

    length_byte = resp[0]
    raw_bytes.append(length_byte)

    if length_byte == 0:
        return raw_bytes

    rest = ser.read(length_byte)
    raw_bytes.extend(rest)
    return raw_bytes


def _expected_ack_kind(frame, operation):
    if operation == OPERATION_WRITE:
        return RESPONSE_ACK_SHORT

    if operation == OPERATION_READ:
        request_len = frame[FRAME_LEN_LSB_POS] | (frame[FRAME_LEN_MSB_POS] << 8)
        return RESPONSE_ACK_SHORT if request_len == 0 else RESPONSE_ACK_LONG

    return None


def ping_module(port):
    try:
        with serial.Serial(port, 115200, timeout=SERIAL_TIMEOUT_S) as ser:
            ser.reset_input_buffer()
            frame = build_empty_read_frame()
            ser.write(bytes(frame))

            response_bytes = _read_response_frame(ser)
            parsed = parse_response(response_bytes)
            if not parsed:
                return False
            return parsed["kind"] in (RESPONSE_READY, RESPONSE_ACK_SHORT)

    except (serial.SerialException, serial.SerialTimeoutException):
        return False


def send_frame(port, frame, operation):
    try:
        with serial.Serial(port, 115200, timeout=SERIAL_TIMEOUT_S) as ser:
            ser.reset_input_buffer()
            ser.write(bytes(frame))

            response_bytes = _read_response_frame(ser)
            if not response_bytes:
                return False, []

            parsed = parse_response(response_bytes)
            if not parsed:
                return False, response_bytes

            if parsed["kind"] == RESPONSE_NACK:
                return False, response_bytes

            expected_ack_kind = _expected_ack_kind(frame, operation)
            if parsed["kind"] != expected_ack_kind:
                return False, response_bytes

            return True, response_bytes

    except (serial.SerialException, serial.SerialTimeoutException):
        return False, []
