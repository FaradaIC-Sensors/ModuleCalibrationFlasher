import struct
from registers import Registers, REGISTERS_PAGE_SIZE


class Module:
    def __init__(self):
        # Byte fields
        self.register_map_ver_minor = 0
        self.register_map_ver_major = 0
        self.status = 0
        self.control = 0
        self.config = 0
        self.firmware_ver_minor = 0
        self.firmware_ver_major = 0
        # Float (32-bit) fields
        self._concentration = 0.0
        self._temperature = 0.0
        self._humidity = 0.0
        self._current = 0.0
        self._pressure = 0.0
        self._gain = 0.0
        self._zero_offset = 0.0
        self._calibration_intercept = 0.0
        self._calibration_current = 0.0
        self._calibration_humidity = 0.0
        self._calibration_temperature = 0.0
        self._calibration_temperature_current = 0.0
        self._calibration_mae = 0.0
        self._calibration_r2 = 0.0
        # 16-bit unsigned
        self.v_reg = 0
        self.v_batt = 0
        self.measurements_length = 0
        self.measurements_offset = 0
        self.average_num = 0
        self.temperature_raw = 0
        self.humidity_raw = 0
        # 32-bit unsigned
        self.concentration_raw_sum = 0
        self.module_id = 0
        self.adc_period = 0
        self.reg_measurements_counter = 0
        self.calibration_timestamp = 0
        # New uint8 boundary registers
        self.calibration_bound_low = 0
        self.calibration_bound_high = 0
        self.concentration_bound_low = 0
        self.concentration_bound_high = 0
        # New uint32 values
        self.sensor_id = 0
        self.calibration_period = 0
        self.rh_potentials_tbl_0 = 0
        self.rh_potentials_tbl_1 = 0
        self.rh_potentials_tbl_2 = 0
        self.rh_potentials_tbl_3 = 0
        self.rh_potentials_tbl_4 = 0
        self.rh_potentials_tbl_5 = 0
        self.rh_potentials_tbl_6 = 0
        self.rh_potentials_tbl_7 = 0
        self.rh_potentials_tbl_8 = 0
        self.rh_potentials_tbl_9 = 0

    def __str__(self):
        fields = [
            ("Module ID", self.module_id),
            (
                "Register Map Version",
                f"{self.register_map_ver_major}.{self.register_map_ver_minor}",
            ),
            (
                "Firmware Version",
                f"{self.firmware_ver_major}.{self.firmware_ver_minor}",
            ),
            ("Status", f"0x{self.status:02X}"),
            ("Control", f"0x{self.control:02X}"),
            ("Config", f"0x{self.config:02X}"),
            ("Concentration", f"{self.concentration:.6f}"),
            ("Temperature", f"{self.temperature:.6f}"),
            ("Humidity", f"{self.humidity:.6f}"),
            ("Current", f"{self.current:.6f}"),
            ("Pressure", f"{self.pressure:.6f}"),
            ("Gain", f"{self.gain:.6f}"),
            ("Zero Offset", f"{self.zero_offset:.6f}"),
            ("V_Reg", self.v_reg),
            ("V_Batt", self.v_batt),
            ("ADC Period", self.adc_period),
            ("Measurements Length", self.measurements_length),
            ("Measurements Offset", self.measurements_offset),
            ("Average Num", self.average_num),
            ("Cal Intercept", f"{self.calibration_intercept:.6f}"),
            ("Cal Current", f"{self.calibration_current:.6f}"),
            ("Cal Humidity", f"{self.calibration_humidity:.6f}"),
            ("Cal Temperature", f"{self.calibration_temperature:.6f}"),
            ("Cal Temp Current", f"{self.calibration_temperature_current:.6f}"),
            ("Cal MAE", f"{self.calibration_mae:.6f}"),
            ("Cal R2", f"{self.calibration_r2:.6f}"),
            ("Calibration Timestamp", self.calibration_timestamp),
            ("Cal Bound Low", self.calibration_bound_low),
            ("Cal Bound High", self.calibration_bound_high),
            ("Conc Bound Low", self.concentration_bound_low),
            ("Conc Bound High", self.concentration_bound_high),
            ("Conc Raw Sum", self.concentration_raw_sum),
            ("Temp Raw", self.temperature_raw),
            ("Humidity Raw", self.humidity_raw),
            (
                "RH Potentials Table: ",
                f"{self.rh_potentials_tbl_0}, {self.rh_potentials_tbl_1}, {self.rh_potentials_tbl_2}, {self.rh_potentials_tbl_3}, {self.rh_potentials_tbl_4}, {self.rh_potentials_tbl_5}, {self.rh_potentials_tbl_6}, {self.rh_potentials_tbl_7}, {self.rh_potentials_tbl_8}, {self.rh_potentials_tbl_9}",
            ),
        ]
        w = max(len(n) for n, _ in fields)
        return "\n".join(f"{n:<{w}} : {v}" for n, v in fields)

    # ------------- 32-bit float quantization & properties -------------
    @staticmethod
    def _as_f32(value):
        """Quantize a Python float to IEEE-754 single precision and return that value."""
        try:
            f = float(0.0 if value is None else value)
        except Exception:
            f = 0.0
        return struct.unpack("<f", struct.pack("<f", f))[0]

    def _get_concentration(self):
        return self._concentration

    def _set_concentration(self, v):
        self._concentration = self._as_f32(v)

    concentration = property(_get_concentration, _set_concentration)

    def _get_temperature(self):
        return self._temperature

    def _set_temperature(self, v):
        self._temperature = self._as_f32(v)

    temperature = property(_get_temperature, _set_temperature)

    def _get_humidity(self):
        return self._humidity

    def _set_humidity(self, v):
        self._humidity = self._as_f32(v)

    humidity = property(_get_humidity, _set_humidity)

    def _get_current(self):
        return self._current

    def _set_current(self, v):
        self._current = self._as_f32(v)

    current = property(_get_current, _set_current)

    def _get_pressure(self):
        return self._pressure

    def _set_pressure(self, v):
        self._pressure = self._as_f32(v)

    pressure = property(_get_pressure, _set_pressure)

    def _get_gain(self):
        return self._gain

    def _set_gain(self, v):
        self._gain = self._as_f32(v)

    gain = property(_get_gain, _set_gain)

    def _get_zero_offset(self):
        return self._zero_offset

    def _set_zero_offset(self, v):
        self._zero_offset = self._as_f32(v)

    zero_offset = property(_get_zero_offset, _set_zero_offset)

    def _get_calibration_intercept(self):
        return self._calibration_intercept

    def _set_calibration_intercept(self, v):
        self._calibration_intercept = self._as_f32(v)

    calibration_intercept = property(
        _get_calibration_intercept, _set_calibration_intercept
    )

    def _get_calibration_current(self):
        return self._calibration_current

    def _set_calibration_current(self, v):
        self._calibration_current = self._as_f32(v)

    calibration_current = property(_get_calibration_current, _set_calibration_current)

    def _get_calibration_humidity(self):
        return self._calibration_humidity

    def _set_calibration_humidity(self, v):
        self._calibration_humidity = self._as_f32(v)

    calibration_humidity = property(
        _get_calibration_humidity, _set_calibration_humidity
    )

    def _get_calibration_temperature(self):
        return self._calibration_temperature

    def _set_calibration_temperature(self, v):
        self._calibration_temperature = self._as_f32(v)

    calibration_temperature = property(
        _get_calibration_temperature, _set_calibration_temperature
    )
    
    def _get_calibration_temperature_current(self):
        return self._calibration_temperature_current

    def _set_calibration_temperature_current(self, v):
        self._calibration_temperature_current = self._as_f32(v)

    calibration_temperature_current = property(
        _get_calibration_temperature_current, _set_calibration_temperature_current
    )

    def _get_calibration_mae(self):
        return self._calibration_mae

    def _set_calibration_mae(self, v):
        self._calibration_mae = self._as_f32(v)

    calibration_mae = property(_get_calibration_mae, _set_calibration_mae)

    def _get_calibration_r2(self):
        return self._calibration_r2

    def _set_calibration_r2(self, v):
        self._calibration_r2 = self._as_f32(v)

    calibration_r2 = property(_get_calibration_r2, _set_calibration_r2)

    # --------------------- Helpers ---------------------
    @staticmethod
    def _u16(data, lo, hi):
        return data[lo] | (data[hi] << 8)

    @staticmethod
    def _u32(data, b0, b1, b2, b3):
        return data[b0] | (data[b1] << 8) | (data[b2] << 16) | (data[b3] << 24)

    @staticmethod
    def _f32(data, b0, b1, b2, b3):
        return struct.unpack("<f", bytes([data[b0], data[b1], data[b2], data[b3]]))[0]

    # ------------------ Public API --------------------
    def deserialize(self, data):
        if len(data) < REGISTERS_PAGE_SIZE:
            return False
        # Bytes
        self.register_map_ver_minor = data[Registers.REG_MAP_VER_LSB]
        self.register_map_ver_major = data[Registers.REG_MAP_VER_MSB]
        self.control = data[Registers.REG_CONTROL]
        self.status = data[Registers.REG_STATUS]
        self.config = data[Registers.REG_CONFIG]
        self.firmware_ver_minor = data[Registers.REG_FIRMWARE_VER_LSB]
        self.firmware_ver_major = data[Registers.REG_FIRMWARE_VER_MSB]
        # Floats
        self.concentration = self._f32(
            data,
            Registers.REG_CONCENTRATION_LLSB,
            Registers.REG_CONCENTRATION_LMSB,
            Registers.REG_CONCENTRATION_MLSB,
            Registers.REG_CONCENTRATION_MMSB,
        )
        self.temperature = self._f32(
            data,
            Registers.REG_TEMPERATURE_LLSB,
            Registers.REG_TEMPERATURE_LMSB,
            Registers.REG_TEMPERATURE_MLSB,
            Registers.REG_TEMPERATURE_MMSB,
        )
        self.humidity = self._f32(
            data,
            Registers.REG_HUMIDITY_LLSB,
            Registers.REG_HUMIDITY_LMSB,
            Registers.REG_HUMIDITY_MLSB,
            Registers.REG_HUMIDITY_MMSB,
        )
        self.current = self._f32(
            data,
            Registers.REG_CURRENT_LLSB,
            Registers.REG_CURRENT_LMSB,
            Registers.REG_CURRENT_MLSB,
            Registers.REG_CURRENT_MMSB,
        )
        self.pressure = self._f32(
            data,
            Registers.REG_PRESSURE_LLSB,
            Registers.REG_PRESSURE_LMSB,
            Registers.REG_PRESSURE_MLSB,
            Registers.REG_PRESSURE_MMSB,
        )
        self.gain = self._f32(
            data,
            Registers.REG_GAIN_LLSB,
            Registers.REG_GAIN_LMSB,
            Registers.REG_GAIN_MLSB,
            Registers.REG_GAIN_MMSB,
        )
        self.zero_offset = self._f32(
            data,
            Registers.REG_ZERO_OFFSET_LLSB,
            Registers.REG_ZERO_OFFSET_LMSB,
            Registers.REG_ZERO_OFFSET_MLSB,
            Registers.REG_ZERO_OFFSET_MMSB,
        )
        self.calibration_intercept = self._f32(
            data,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_LLSB,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_LMSB,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_MLSB,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_MMSB,
        )
        self.calibration_current = self._f32(
            data,
            Registers.REG_CALIBRATION_DATA_CURRENT_LLSB,
            Registers.REG_CALIBRATION_DATA_CURRENT_LMSB,
            Registers.REG_CALIBRATION_DATA_CURRENT_MLSB,
            Registers.REG_CALIBRATION_DATA_CURRENT_MMSB,
        )
        self.calibration_humidity = self._f32(
            data,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_LLSB,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_LMSB,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_MLSB,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_MMSB,
        )
        self.calibration_temperature = self._f32(
            data,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_LLSB,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_LMSB,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_MLSB,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_MMSB,
        )
        self.calibration_temperature_current = self._f32(
            data,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_LLSB,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_LMSB,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_MLSB,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_MMSB,
        )
        # Calibration timestamp (u32)
        self.calibration_timestamp = self._u32(
            data,
            Registers.REG_CALIBRATION_TIMESTAMP_LLSB,
            Registers.REG_CALIBRATION_TIMESTAMP_LMSB,
            Registers.REG_CALIBRATION_TIMESTAMP_MLSB,
            Registers.REG_CALIBRATION_TIMESTAMP_MMSB,
        )
        # New uint8 boundary registers
        self.calibration_bound_low = data[Registers.REG_CALIBRATION_BOUND_LOW]
        self.calibration_bound_high = data[Registers.REG_CALIBRATION_BOUND_HIGH]
        self.concentration_bound_low = data[Registers.REG_CONCENTRATION_BOUND_LOW]
        self.concentration_bound_high = data[Registers.REG_CONCENTRATION_BOUND_HIGH]
        # Calibration quality metrics (float32)
        self.calibration_mae = self._f32(
            data,
            Registers.REG_CALIBRATION_MAE_LLSB,
            Registers.REG_CALIBRATION_MAE_LMSB,
            Registers.REG_CALIBRATION_MAE_MLSB,
            Registers.REG_CALIBRATION_MAE_MMSB,
        )
        self.calibration_r2 = self._f32(
            data,
            Registers.REG_CALIBRATION_R2_LLSB,
            Registers.REG_CALIBRATION_R2_LMSB,
            Registers.REG_CALIBRATION_R2_MLSB,
            Registers.REG_CALIBRATION_R2_MMSB,
        )
        # New uint32 values
        self.sensor_id = self._u32(
            data,
            Registers.REG_SENSOR_ID_LLSB,
            Registers.REG_SENSOR_ID_LMSB,
            Registers.REG_SENSOR_ID_MLSB,
            Registers.REG_SENSOR_ID_MMSB,
        )
        self.calibration_period = self._u32(
            data,
            Registers.REG_CALIBRATION_PERIOD_LLSB,
            Registers.REG_CALIBRATION_PERIOD_LMSB,
            Registers.REG_CALIBRATION_PERIOD_MLSB,
            Registers.REG_CALIBRATION_PERIOD_MMSB,
        )
        # 32-bit ints
        self.concentration_raw_sum = self._u32(
            data,
            Registers.REG_CONCENTRATION_RAW_SUM_LLSB,
            Registers.REG_CONCENTRATION_RAW_SUM_LMSB,
            Registers.REG_CONCENTRATION_RAW_SUM_MLSB,
            Registers.REG_CONCENTRATION_RAW_SUM_MMSB,
        )
        self.module_id = self._u32(
            data,
            Registers.REG_DEVICE_ID_LLSB,
            Registers.REG_DEVICE_ID_LMSB,
            Registers.REG_DEVICE_ID_MLSB,
            Registers.REG_DEVICE_ID_MMSB,
        )
        self.adc_period = self._u32(
            data,
            Registers.REG_ADC_PERIOD_LLSB,
            Registers.REG_ADC_PERIOD_LMSB,
            Registers.REG_ADC_PERIOD_MLSB,
            Registers.REG_ADC_PERIOD_MMSB,
        )
        self.reg_measurements_counter = self._u32(
            data,
            Registers.REG_MEASUREMENTS_COUNTER_LLSB,
            Registers.REG_MEASUREMENTS_COUNTER_LMSB,
            Registers.REG_MEASUREMENTS_COUNTER_MLSB,
            Registers.REG_MEASUREMENTS_COUNTER_MMSB,
        )
        # 16-bit ints
        self.v_reg = self._u16(
            data, Registers.REG_DEVICE_VREG_LSB, Registers.REG_DEVICE_VREG_MSB
        )
        self.v_batt = self._u16(
            data, Registers.REG_DEVICE_VBATT_LSB, Registers.REG_DEVICE_VBATT_MSB
        )
        self.measurements_length = self._u16(
            data,
            Registers.REG_MEASUREMENTS_LENGTH_LSB,
            Registers.REG_MEASUREMENTS_LENGTH_MSB,
        )
        self.measurements_offset = self._u16(
            data,
            Registers.REG_MEASUREMENTS_OFFSET_LSB,
            Registers.REG_MEASUREMENTS_OFFSET_MSB,
        )
        self.average_num = self._u16(
            data, Registers.REG_AVERAGE_NUM_LSB, Registers.REG_AVERAGE_NUM_MSB
        )
        self.temperature_raw = self._u16(
            data,
            Registers.REG_TEMPERATURE_RAW_SHT40_LSB,
            Registers.REG_TEMPERATURE_RAW_SHT40_MSB,
        )
        self.humidity_raw = self._u16(
            data,
            Registers.REG_HUMIDITY_RAW_SHT40_LSB,
            Registers.REG_HUMIDITY_RAW_SHT40_MSB,
        )
        self.rh_potentials_tbl_0 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_0_L,
            Registers.REG_RH_POTENTIALS_TBL_0_H,
        )
        self.rh_potentials_tbl_1 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_1_L,
            Registers.REG_RH_POTENTIALS_TBL_1_H,
        )
        self.rh_potentials_tbl_2 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_2_L,
            Registers.REG_RH_POTENTIALS_TBL_2_H,
        )
        self.rh_potentials_tbl_3 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_3_L,
            Registers.REG_RH_POTENTIALS_TBL_3_H,
        )
        self.rh_potentials_tbl_4 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_4_L,
            Registers.REG_RH_POTENTIALS_TBL_4_H,
        )
        self.rh_potentials_tbl_5 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_5_L,
            Registers.REG_RH_POTENTIALS_TBL_5_H,
        )
        self.rh_potentials_tbl_6 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_6_L,
            Registers.REG_RH_POTENTIALS_TBL_6_H,
        )
        self.rh_potentials_tbl_7 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_7_L,
            Registers.REG_RH_POTENTIALS_TBL_7_H,
        )
        self.rh_potentials_tbl_8 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_8_L,
            Registers.REG_RH_POTENTIALS_TBL_8_H,
        )
        self.rh_potentials_tbl_9 = self._u16(
            data,
            Registers.REG_RH_POTENTIALS_TBL_9_L,
            Registers.REG_RH_POTENTIALS_TBL_9_H,
        )
        return True

    def _blank_page(self):
        return bytearray([0] * REGISTERS_PAGE_SIZE)

    def _module_config_buffer(self):
        return bytearray([0] * 12)

    def _module_calibration_buffer(self):
        # Buffer spans from MEASUREMENTS_OFFSET_LSB (0x88) through SENSOR_ID_MMSB (0xB7)
        size = (
            Registers.REG_SENSOR_ID_MMSB
            - Registers.REG_MEASUREMENTS_OFFSET_LSB
            + 1
        )
        return bytearray([0] * size)

    def _module_rh_potentials_buffer(self):
        # Buffer spans from RH_POTENTIALS_TBL_0_L (0xB4) through RH_POTENTIALS_TBL_9_H (0xC7)
        size = (
            Registers.REG_RH_POTENTIALS_TBL_9_H
            - Registers.REG_RH_POTENTIALS_TBL_0_L
            + 1
        )
        return bytearray([0] * size)

    def _module_control_buffer(self):
        return bytearray([0] * 1)

    @staticmethod
    def _put_u16(page, lo, hi, value):
        v = int(value) & 0xFFFF
        page[lo] = v & 0xFF
        page[hi] = (v >> 8) & 0xFF

    @staticmethod
    def _put_u32(page, b0, b1, b2, b3, value):
        v = int(value) & 0xFFFFFFFF
        page[b0] = v & 0xFF
        page[b1] = (v >> 8) & 0xFF
        page[b2] = (v >> 16) & 0xFF
        page[b3] = (v >> 24) & 0xFF

    @staticmethod
    def _put_f32(page, b0, b1, b2, b3, value):
        b = struct.pack("<f", float(value))
        page[b0], page[b1], page[b2], page[b3] = b

    def serialize_control(self):
        """Serialize only control register (and leave all others zero)."""
        buffer = self._module_control_buffer()
        base_address = Registers.REG_CONTROL
        buffer[Registers.REG_CONTROL - base_address] = int(self.control) & 0xFF
        return base_address, list(buffer)

    def serialize_config(self):
        """Serialize config register (single byte at REG_CONFIG)."""
        buffer = bytearray([int(self.config) & 0xFF])
        return Registers.REG_CONFIG, list(buffer)

    def serialize_module_config(self):
        """Serialize module configuration: module_id, gain, zero_offset."""
        buffer = self._module_config_buffer()
        base_address = Registers.REG_DEVICE_ID_LLSB
        self._put_u32(
            buffer,
            Registers.REG_DEVICE_ID_LLSB - base_address,
            Registers.REG_DEVICE_ID_LMSB - base_address,
            Registers.REG_DEVICE_ID_MLSB - base_address,
            Registers.REG_DEVICE_ID_MMSB - base_address,
            self.module_id,
        )
        self._put_f32(
            buffer,
            Registers.REG_GAIN_LLSB - base_address,
            Registers.REG_GAIN_LMSB - base_address,
            Registers.REG_GAIN_MLSB - base_address,
            Registers.REG_GAIN_MMSB - base_address,
            self.gain,
        )
        self._put_f32(
            buffer,
            Registers.REG_ZERO_OFFSET_LLSB - base_address,
            Registers.REG_ZERO_OFFSET_LMSB - base_address,
            Registers.REG_ZERO_OFFSET_MLSB - base_address,
            Registers.REG_ZERO_OFFSET_MMSB - base_address,
            self.zero_offset,
        )
        return base_address, list(buffer)

    def serialize_rh_potentials(self):
        buffer = self._module_rh_potentials_buffer()
        base_address = Registers.REG_RH_POTENTIALS_TBL_0_L
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_0_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_0_H - base_address,
            self.rh_potentials_tbl_0,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_1_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_1_H - base_address,
            self.rh_potentials_tbl_1,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_2_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_2_H - base_address,
            self.rh_potentials_tbl_2,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_3_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_3_H - base_address,
            self.rh_potentials_tbl_3,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_4_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_4_H - base_address,
            self.rh_potentials_tbl_4,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_5_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_5_H - base_address,
            self.rh_potentials_tbl_5,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_6_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_6_H - base_address,
            self.rh_potentials_tbl_6,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_7_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_7_H - base_address,
            self.rh_potentials_tbl_7,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_8_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_8_H - base_address,
            self.rh_potentials_tbl_8,
        )
        self._put_u16(
            buffer,
            Registers.REG_RH_POTENTIALS_TBL_9_L - base_address,
            Registers.REG_RH_POTENTIALS_TBL_9_H - base_address,
            self.rh_potentials_tbl_9,
        )
        return base_address, list(buffer)

    def serialize_calibration_config(self):
        """Serialize calibration-related configuration including measurements offset,
        averaging number, calibration floats, timestamp and boundary registers."""
        buffer = self._module_calibration_buffer()
        base_address = Registers.REG_MEASUREMENTS_OFFSET_LSB
        # Measurements offset & average
        self._put_u16(
            buffer,
            Registers.REG_MEASUREMENTS_OFFSET_LSB - base_address,
            Registers.REG_MEASUREMENTS_OFFSET_MSB - base_address,
            self.measurements_offset,
        )
        self._put_u16(
            buffer,
            Registers.REG_AVERAGE_NUM_LSB - base_address,
            Registers.REG_AVERAGE_NUM_MSB - base_address,
            self.average_num,
        )
        # Calibration floats
        self._put_f32(
            buffer,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_LLSB - base_address,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_LMSB - base_address,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_MLSB - base_address,
            Registers.REG_CALIBRATION_DATA_INTERCEPT_MMSB - base_address,
            self.calibration_intercept,
        )
        self._put_f32(
            buffer,
            Registers.REG_CALIBRATION_DATA_CURRENT_LLSB - base_address,
            Registers.REG_CALIBRATION_DATA_CURRENT_LMSB - base_address,
            Registers.REG_CALIBRATION_DATA_CURRENT_MLSB - base_address,
            Registers.REG_CALIBRATION_DATA_CURRENT_MMSB - base_address,
            self.calibration_current,
        )
        self._put_f32(
            buffer,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_LLSB - base_address,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_LMSB - base_address,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_MLSB - base_address,
            Registers.REG_CALIBRATION_DATA_HUMIDITY_MMSB - base_address,
            self.calibration_humidity,
        )
        self._put_f32(
            buffer,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_LLSB - base_address,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_LMSB - base_address,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_MLSB - base_address,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_MMSB - base_address,
            self.calibration_temperature,
        )
        self._put_f32(
            buffer,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_LLSB - base_address,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_LMSB - base_address,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_MLSB - base_address,
            Registers.REG_CALIBRATION_DATA_TEMPERATURE_CURRENT_MMSB - base_address,
            self.calibration_temperature_current,
        )
        # Timestamp (u32)
        self._put_u32(
            buffer,
            Registers.REG_CALIBRATION_TIMESTAMP_LLSB - base_address,
            Registers.REG_CALIBRATION_TIMESTAMP_LMSB - base_address,
            Registers.REG_CALIBRATION_TIMESTAMP_MLSB - base_address,
            Registers.REG_CALIBRATION_TIMESTAMP_MMSB - base_address,
            self.calibration_timestamp,
        )
        # Boundary registers (u8)
        buffer[Registers.REG_CALIBRATION_BOUND_LOW - base_address] = (
            int(self.calibration_bound_low) & 0xFF
        )
        buffer[Registers.REG_CALIBRATION_BOUND_HIGH - base_address] = (
            int(self.calibration_bound_high) & 0xFF
        )
        buffer[Registers.REG_CONCENTRATION_BOUND_LOW - base_address] = (
            int(self.concentration_bound_low) & 0xFF
        )
        buffer[Registers.REG_CONCENTRATION_BOUND_HIGH - base_address] = (
            int(self.concentration_bound_high) & 0xFF
        )
        # Calibration quality metrics (float32)
        self._put_f32(
            buffer,
            Registers.REG_CALIBRATION_MAE_LLSB - base_address,
            Registers.REG_CALIBRATION_MAE_LMSB - base_address,
            Registers.REG_CALIBRATION_MAE_MLSB - base_address,
            Registers.REG_CALIBRATION_MAE_MMSB - base_address,
            self.calibration_mae,
        )
        self._put_f32(
            buffer,
            Registers.REG_CALIBRATION_R2_LLSB - base_address,
            Registers.REG_CALIBRATION_R2_LMSB - base_address,
            Registers.REG_CALIBRATION_R2_MLSB - base_address,
            Registers.REG_CALIBRATION_R2_MMSB - base_address,
            self.calibration_r2,
        )
        # New uint32 values
        self._put_u32(
            buffer,
            Registers.REG_SENSOR_ID_LLSB - base_address,
            Registers.REG_SENSOR_ID_LMSB - base_address,
            Registers.REG_SENSOR_ID_MLSB - base_address,
            Registers.REG_SENSOR_ID_MMSB - base_address,
            self.sensor_id,
        )
        self._put_u32(
            buffer,
            Registers.REG_CALIBRATION_PERIOD_LLSB - base_address,
            Registers.REG_CALIBRATION_PERIOD_LMSB - base_address,
            Registers.REG_CALIBRATION_PERIOD_MLSB - base_address,
            Registers.REG_CALIBRATION_PERIOD_MMSB - base_address,
            self.calibration_period,
        )
        return base_address, list(buffer)

    def control_start_measurement_set(self):
        self.control = 0x01

    def control_start_sht40_measurement_set(self):
        self.control = 0x02

    def control_store_settings_to_flash(self):
        self.control = 0x04

    def control_store_script_to_flash(self):
        self.control = 0x08
