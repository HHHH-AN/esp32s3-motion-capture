#pragma once

#include <array>
#include <cstdint>

namespace mocap::core {

enum SampleFlag : std::uint16_t {
  kAccelValid = 1U << 0,
  kGyroValid = 1U << 1,
  kMagValid = 1U << 2,
  kTemperatureValid = 1U << 3,
  kMagStale = 1U << 4,
  kImuOverflow = 1U << 5,
  kQueueOverflow = 1U << 6,
  kSensorFault = 1U << 7,
};

struct ImuReading {
  std::array<float, 3> accel_g{};
  std::array<float, 3> gyro_dps{};
  float temperature_c{0.0F};
  std::uint64_t timestamp_us{0};
  bool valid{false};
};

struct MagReading {
  std::array<float, 3> field_ut{};
  std::uint64_t timestamp_us{0};
  bool valid{false};
};

// Wire-ready sample in the exact v1 fixed-point units.
struct MotionSample {
  std::array<std::int16_t, 3> accel_mg{};
  std::array<std::int16_t, 3> gyro_dps_x10{};
  std::array<std::int16_t, 3> mag_ut_x10{};
  std::int16_t temperature_c_x100{0};
  std::uint16_t mag_age_us{0};
  std::uint16_t status_flags{0};
  std::uint64_t timestamp_us{0};
};

static_assert(sizeof(MotionSample::accel_mg) == 6);

}  // namespace mocap::core
