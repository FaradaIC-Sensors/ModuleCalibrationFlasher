import serial
import time

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

SERIAL_BAUD = 115200
SERIAL_TIMEOUT_S = 0.1
FRAME_READ_TIMEOUT_S = 1.0
PING_SETTLE_TIME_S = 0.01


def _read_response_frame(ser):
    raw_bytes = []
    expected_length = None
    deadline = time.monotonic() + FRAME_READ_TIMEOUT_S

    while time.monotonic() < deadline:
        remaining = 1 if expected_length is None else expected_length - len(raw_bytes)
        if remaining <= 0:
            break

        resp = ser.read(remaining)
        if not resp:
            continue

        raw_bytes.extend(resp)

        if expected_length is None and raw_bytes:
            length_byte = raw_bytes[0]
            if length_byte == 0:
                return raw_bytes
            expected_length = length_byte + 1

    return raw_bytes


def _expected_ack_kind(frame, operation):
    if operation == OPERATION_WRITE:
        return RESPONSE_ACK_SHORT

    if operation == OPERATION_READ:
        request_len = frame[FRAME_LEN_LSB_POS] | (frame[FRAME_LEN_MSB_POS] << 8)
        return RESPONSE_ACK_SHORT if request_len == 0 else RESPONSE_ACK_LONG

    return None


def _send_ping(ser):
    try:
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


def ping_module(port):
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=SERIAL_TIMEOUT_S) as ser:
            return _send_ping(ser)
    except (serial.SerialException, serial.SerialTimeoutException):
        return False


def send_frame(port, frame, operation):
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=SERIAL_TIMEOUT_S) as ser:
            if not _send_ping(ser):
                return False, []

            time.sleep(PING_SETTLE_TIME_S)

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
