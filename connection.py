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
)


SERIAL_BAUD = 115200
SERIAL_TIMEOUT_S = 0.1
PING_SETTLE_TIME_S = 0.01


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


def ping_module(port):
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=SERIAL_TIMEOUT_S) as ser:
            return _send_ping(ser)
    except (serial.SerialException, serial.SerialTimeoutException):
        return False


def send_frame(port, frame, operation):
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=SERIAL_TIMEOUT_S) as ser:
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
