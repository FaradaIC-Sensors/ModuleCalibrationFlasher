import serial
import time

from client import build_empty_read_frame
from protocol import (
    ACK_LENGTH,
    ETX,
    STX,
    ACK,
    NACK,
    READY,
    ACK_EMPTY_LENGTH,
    READY_LENGTH,
    NACK_LENGTH,
    FRAME_ETX_END_POS,
    FRAME_OP_POS,
    FRAME_LEN_LSB_POS,
    FRAME_LEN_MSB_POS,
    FRAME_PROTOCOL_OVERHEAD,
    FRAME_PROTOCOL_PREFIX_LEN,
    OPERATION_READ,
    OPERATION_WRITE,
    blulog_build_frame,
    BLULOG_READY_LENGTH,
    BLULOG_ACK_LENGTH,
    BLULOG_NACK_LENGTH,
    BLULOG_FRAME_PROTOCOL_OVERHEAD,
)


SERIAL_BAUD = 115200
SERIAL_TIMEOUT_S = 0.5
PING_SETTLE_TIME_S = 0.01
BLULOG_MAX_ATTEMPTS = 3
BLULOG_EMPTY_RETRY_DELAY_S = 0.05
BLULOG_READY_RETRY_DELAY_S = 0.02


def _read_ping_response(ser):
    """Read a short response (READY/ACK/NACK) after a ping. Returns True if device is awake."""
    found_frame = False
    response_bytes = []
    count = 0
    expected_length = 0

    while True:
        resp = ser.read(1)
        byte = resp[0] if resp else None
        if not byte:
            break
        if byte == STX:
            found_frame = True

        if found_frame:
            response_bytes.append(byte)
            count += 1

            if count == 2:
                if byte == ACK:
                    expected_length = ACK_LENGTH
                elif byte == READY:
                    expected_length = READY_LENGTH
                elif byte == NACK:
                    expected_length = NACK_LENGTH
                else:
                    return False

            if expected_length and len(response_bytes) >= expected_length:
                break

    if (
        expected_length > 0
        and len(response_bytes) == expected_length
        and response_bytes[-1 * FRAME_ETX_END_POS] == ETX
    ):
        op = response_bytes[FRAME_OP_POS]
        return op == ACK or op == READY

    return False


def _send_ping(ser):
    """Send ping frame and read response. Returns True if device responded."""
    ser.reset_input_buffer()
    frame = build_empty_read_frame()
    ser.write(frame)
    return _read_ping_response(ser)


def _read_blulog_response_frame(ser):
    """Read one Blulog length-prefixed response frame. Returns list of bytes or []."""
    first = ser.read(1)
    if not first:
        return []
    length = first[0]
    frame = bytearray(first)
    if length == 0:
        return list(frame)
    rest = ser.read(length)
    frame.extend(rest)
    return list(frame)


def _read_blulog_ping_response(ser):
    """Read and validate a Blulog ping response. Returns True if device is awake."""
    frame = _read_blulog_response_frame(ser)
    if len(frame) < BLULOG_READY_LENGTH:
        return False
    if frame[0] + 1 != len(frame):
        return False
    from protocol import _crc16_ccitt_false
    crc_received = frame[-2] | (frame[-1] << 8)
    if _crc16_ccitt_false(frame[:-2]) != crc_received:
        return False
    op = frame[FRAME_OP_POS]
    return op == ACK or op == READY


def _send_blulog_ping(ser):
    """Send Blulog-format ping frame. Returns True if device responded."""
    ser.reset_input_buffer()
    frame = blulog_build_frame(OPERATION_READ, 0x0000, [], 0)
    ser.write(frame)
    return _read_blulog_ping_response(ser)


def _exchange_blulog_frame(ser, frame):
    """Retry empty and READY responses like the working regression script."""
    last_response = []
    for attempt in range(BLULOG_MAX_ATTEMPTS):
        ser.reset_input_buffer()
        ser.write(frame)
        response_bytes = _read_blulog_response_frame(ser)
        last_response = response_bytes

        if not response_bytes and attempt + 1 < BLULOG_MAX_ATTEMPTS:
            time.sleep(BLULOG_EMPTY_RETRY_DELAY_S)
            continue

        op_code = response_bytes[FRAME_OP_POS] if len(response_bytes) > FRAME_OP_POS else None
        if op_code == READY and attempt + 1 < BLULOG_MAX_ATTEMPTS:
            time.sleep(BLULOG_READY_RETRY_DELAY_S)
            continue

        return response_bytes

    return last_response


def ping_module(port, protocol="faradaic"):
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=SERIAL_TIMEOUT_S) as ser:
            if protocol == "blulog":
                return _send_blulog_ping(ser)
            return _send_ping(ser)
    except (serial.SerialException, serial.SerialTimeoutException):
        return False


def send_frame(port, frame, operation, protocol="faradaic"):
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=SERIAL_TIMEOUT_S) as ser:
            if protocol == "blulog":
                response_bytes = _exchange_blulog_frame(ser, frame)
                if not response_bytes:
                    return False, []
                op_code = response_bytes[FRAME_OP_POS] if len(response_bytes) > 1 else None
                if op_code == ACK:
                    return True, response_bytes
                return False, response_bytes

            # Wake the device with a ping first
            if not _send_ping(ser):
                return False, []

            time.sleep(PING_SETTLE_TIME_S)

            # Now send the actual command
            ser.reset_input_buffer()
            ser.write(frame)

            response_bytes = []
            expected_length = 0
            op_code = None
            found_frame = False
            start_time = time.time_ns()

            while True:
                resp = ser.read(1)
                if not resp:
                    if (time.time_ns() - start_time) > 1_000_000_000:
                        return False, response_bytes
                    continue

                byte = resp[0]

                if not found_frame:
                    if byte != STX:
                        continue
                    found_frame = True
                    response_bytes = [byte]
                    continue

                response_bytes.append(byte)

                if len(response_bytes) == 2:
                    op_code = byte
                    if op_code == NACK:
                        expected_length = NACK_LENGTH
                    elif op_code == ACK:
                        if operation == OPERATION_READ:
                            expected_length = ACK_EMPTY_LENGTH
                        if operation == OPERATION_WRITE:
                            expected_length = 5
                    elif op_code == READY:
                        expected_length = READY_LENGTH
                    else:
                        expected_length = 0

                if op_code == ACK and len(response_bytes) >= FRAME_PROTOCOL_PREFIX_LEN and operation == OPERATION_READ:
                    frame_length = response_bytes[FRAME_LEN_LSB_POS] | (
                        response_bytes[FRAME_LEN_MSB_POS] << 8
                    )
                    if frame_length > 0:
                        expected_length = FRAME_PROTOCOL_OVERHEAD + frame_length
                    else:
                        expected_length = ACK_EMPTY_LENGTH

                if expected_length and len(response_bytes) >= expected_length:
                    if response_bytes[-1] != ETX:
                        return False, response_bytes
                    if op_code == ACK or op_code == READY:
                        return True, response_bytes
                    if op_code == NACK:
                        return False, response_bytes
                    return False, response_bytes

    except (serial.SerialException, serial.SerialTimeoutException):
        return False, []
