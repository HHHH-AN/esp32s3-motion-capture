#include "config/calibration_store.hpp"

#include <Preferences.h>

#include <cstddef>

#include "protocol/crc16.hpp"

namespace mocap::config {
namespace {
constexpr char kNamespace[] = "mocap-cal";
constexpr char kKey[] = "sensor";
}

bool CalibrationStore::load(SensorCalibration& calibration) {
  Preferences preferences;
  if (!preferences.begin(kNamespace, true)) return false;
  const bool ok = preferences.getBytesLength(kKey) == sizeof(calibration) &&
                  preferences.getBytes(kKey, &calibration, sizeof(calibration)) == sizeof(calibration);
  preferences.end();
  return ok && calibration.schema_version == 1 && calibration.crc == calculateCrc(calibration);
}

bool CalibrationStore::save(SensorCalibration calibration) {
  calibration.schema_version = 1;
  calibration.crc = calculateCrc(calibration);
  Preferences preferences;
  if (!preferences.begin(kNamespace, false)) return false;
  const bool ok = preferences.putBytes(kKey, &calibration, sizeof(calibration)) == sizeof(calibration);
  preferences.end();
  return ok;
}

bool CalibrationStore::reset() {
  Preferences preferences;
  if (!preferences.begin(kNamespace, false)) return false;
  const bool ok = preferences.remove(kKey);
  preferences.end();
  return ok;
}

std::uint16_t CalibrationStore::calculateCrc(const SensorCalibration& calibration) {
  return protocol::crc16CcittFalse(reinterpret_cast<const std::uint8_t*>(&calibration),
                                   offsetof(SensorCalibration, crc));
}

}  // namespace mocap::config
