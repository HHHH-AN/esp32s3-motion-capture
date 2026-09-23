#include "core/motion_sampler.hpp"

#include <cmath>
#include <limits>

#include "config/app_config.hpp"
#include "core/sensor_frame.hpp"

namespace mocap::core {
namespace {

std::int16_t scaledI16(float value, float scale) {
  const float scaled = std::round(value * scale);
  if (scaled > static_cast<float>(std::numeric_limits<std::int16_t>::max()))
    return std::numeric_limits<std::int16_t>::max();
  if (scaled < static_cast<float>(std::numeric_limits<std::int16_t>::min()))
    return std::numeric_limits<std::int16_t>::min();
  return static_cast<std::int16_t>(scaled);
}

}  // namespace

bool MotionSampler::begin() {
  imu_ready_ = imu_.begin();
  mag_ready_ = mag_.begin();
  return imu_ready_;
}

bool MotionSampler::sampleOnce() {
  if (!imu_ready_) return false;
  ImuReading imu{};
  if (!imu_.read(imu)) {
    health_.imuError();
    return false;
  }

  if (mag_ready_ && !mag_.sample()) health_.magError();
  const MagReading& mag = mag_.latest();
  const Vector3f accel = transformIcmToBoard(imu.accel_g);
  const Vector3f gyro = transformIcmToBoard(imu.gyro_dps);
  const Vector3f field = transformLisToBoard(mag.field_ut);

  MotionSample sample{};
  sample.timestamp_us = imu.timestamp_us;
  sample.status_flags = kAccelValid | kGyroValid | kTemperatureValid;
  for (std::size_t i = 0; i < 3; ++i) {
    sample.accel_mg[i] = scaledI16(accel[i], 1000.0F);
    sample.gyro_dps_x10[i] = scaledI16(gyro[i], 10.0F);
    sample.mag_ut_x10[i] = scaledI16(field[i], 10.0F);
  }
  sample.temperature_c_x100 = scaledI16(imu.temperature_c, 100.0F);

  if (mag.valid && imu.timestamp_us >= mag.timestamp_us) {
    const std::uint64_t age = imu.timestamp_us - mag.timestamp_us;
    sample.mag_age_us = age > 0xFFFFU ? 0xFFFFU : static_cast<std::uint16_t>(age);
    sample.status_flags |= kMagValid;
    if (age > 100'000U) sample.status_flags |= kMagStale;
  } else {
    sample.status_flags |= kSensorFault;
  }

  const bool had_capacity = queue_.size() < config::kSampleQueueDepth;
  if (!had_capacity) sample.status_flags |= kQueueOverflow;
  if (!queue_.pushDropOldest(sample)) return false;
  if (!had_capacity) {
    health_.queueOverflow();
  }
  health_.sampleProduced();
  health_.observeQueueDepth(static_cast<std::uint16_t>(queue_.size()));
  return true;
}

}  // namespace mocap::core
