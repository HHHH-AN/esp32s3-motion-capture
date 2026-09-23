#pragma once

#include <cstdint>

#include "config/app_config.hpp"

namespace mocap::config {

struct DeviceConfig {
  std::uint32_t schema_version{1};
  std::uint8_t node_id{kNodeId};
  DeviceRole role{kDeviceRole};
  std::uint16_t sample_rate_hz{kSampleRateHz};
  std::uint16_t accel_range_g{16};
  std::uint16_t gyro_range_dps{2000};
  std::uint8_t espnow_channel{kEspNowChannel};
  bool streaming_enabled{true};
};

class DeviceConfigStore final {
 public:
  bool load(DeviceConfig& config);
  bool save(const DeviceConfig& config);
  bool reset();
  static bool validate(const DeviceConfig& config);
};

}  // namespace mocap::config
