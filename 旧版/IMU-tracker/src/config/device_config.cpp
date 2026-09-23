#include "config/device_config.hpp"

#include <Preferences.h>

namespace mocap::config {
namespace {
constexpr char kNamespace[] = "mocap-config";
constexpr char kKey[] = "device";
}

bool DeviceConfigStore::load(DeviceConfig& config) {
  Preferences preferences;
  if (!preferences.begin(kNamespace, true)) return false;
  const std::size_t size = preferences.getBytesLength(kKey);
  const bool ok = size == sizeof(DeviceConfig) &&
                  preferences.getBytes(kKey, &config, sizeof(config)) == sizeof(config) &&
                  validate(config);
  preferences.end();
  return ok;
}

bool DeviceConfigStore::save(const DeviceConfig& config) {
  if (!validate(config)) return false;
  Preferences preferences;
  if (!preferences.begin(kNamespace, false)) return false;
  const bool ok = preferences.putBytes(kKey, &config, sizeof(config)) == sizeof(config);
  preferences.end();
  return ok;
}

bool DeviceConfigStore::reset() {
  Preferences preferences;
  if (!preferences.begin(kNamespace, false)) return false;
  const bool ok = preferences.remove(kKey);
  preferences.end();
  return ok;
}

bool DeviceConfigStore::validate(const DeviceConfig& config) {
  if (config.schema_version != 1 || config.node_id > 14 || config.sample_rate_hz != 100 ||
      config.accel_range_g != 16 || config.gyro_range_dps != 2000 ||
      config.espnow_channel < 1 || config.espnow_channel > 13) return false;
  return config.role == DeviceRole::Gateway ? config.node_id == 0 : config.node_id != 0;
}

}  // namespace mocap::config
