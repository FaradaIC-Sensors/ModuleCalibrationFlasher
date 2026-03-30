import serial
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
    OPERATION_WRITE
)
import time


def ping_module(port):
    try:
        with serial.Serial(port, 115200, timeout=0.05) as ser:
            frame = build_empty_read_frame()
            ser.write(frame)
            receiving = True
            found_frame = False
            response_bytes = []
            count = 0
            expected_length = 0
            start_time = time.time_ns()
            while receiving:
                resp = ser.read(1)
                byte = resp[0] if resp else None
                if not byte:
                    receiving = False
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

            # Got exactly the expected length and ETX
            if (
                expected_length > 0
                and len(response_bytes) == expected_length
                and response_bytes[-1 * FRAME_ETX_END_POS] == ETX
            ):
                if (
                    response_bytes[FRAME_OP_POS] == ACK
                    or response_bytes[FRAME_OP_POS] == READY
                ):
                    return True
                elif response_bytes[FRAME_OP_POS] == NACK:
                    return False

            # Read too many bytes and still no ETX
            if len(response_bytes) > expected_length:
                return False

            # Timeout 1s
            if (time.time_ns() - start_time) > 1_000_000_000:
                return False

            return False

    except (serial.SerialException, serial.SerialTimeoutException):
        return False


def send_frame(port, frame, operation):
    try:
        with serial.Serial(port, 115200, timeout=0.1) as ser:
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

                # Find start of frame
                if not found_frame:
                    if byte != STX:
                        continue
                    found_frame = True
                    response_bytes = [byte]
                    continue

                response_bytes.append(byte)

                # Determine op code and initial expected length
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
                        # Unknown response op
                        expected_length = 0

                # If ACK and we have the length bytes, adjust expected length for data payload
                if op_code == ACK and len(response_bytes) >= FRAME_PROTOCOL_PREFIX_LEN and operation == OPERATION_READ:
                    frame_length = response_bytes[FRAME_LEN_LSB_POS] | (
                        response_bytes[FRAME_LEN_MSB_POS] << 8
                    )
                    if frame_length > 0:
                        expected_length = FRAME_PROTOCOL_OVERHEAD + frame_length
                    else:
                        expected_length = ACK_EMPTY_LENGTH
                
                # When we have enough bytes, verify ETX and decide
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
