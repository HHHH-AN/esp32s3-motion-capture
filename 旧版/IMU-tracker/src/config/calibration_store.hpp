#pragma once

#include <array>
#include <cstdint>

namespace mocap::config {

struct SensorCalibration {
  std::uint32_t schema_version{1};
  std::array<float, 3> gyro_bias_dps{};
  std::array<float, 3> accel_bias_g{};
  std::array<float, 9> accel_matrix{1, 0, 0, 0, 1, 0, 0, 0, 1};
  std::array<float, 3> mag_bias_ut{};
  std::array<float, 9> mag_matrix{1, 0, 0, 0, 1, 0, 0, 0, 1};
  std::uint16_t crc{0};
};

class CalibrationStore final {
 public:
  bool load(SensorCalibration& calibration);
  bool save(SensorCalibration calibration);
  bool reset();

 private:
  static std::uint16_t calculateCrc(const SensorCalibration& calibration);
};

}  // namespace mocap::config
