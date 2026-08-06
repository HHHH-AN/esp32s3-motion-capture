#include "drivers/axp2101_driver.hpp"

namespace mocap::drivers {
namespace {
constexpr std::uint8_t kStatus0 = 0x00;
constexpr std::uint8_t kStatus1 = 0x01;
constexpr std::uint8_t kChipId = 0x03;
}

bool Axp2101Driver::begin() {
  Axp2101Status status{};
  return readStatus(status);
}

bool Axp2101Driver::readStatus(Axp2101Status& status) {
  status = {};
  if (!readRegister(kChipId, status.chip_id)) return false;
  if (!readRegister(kStatus0, status.status0)) return false;
  if (!readRegister(kStatus1, status.status1)) return false;
  status.reachable = true;
  return true;
}

bool Axp2101Driver::readRegister(std::uint8_t reg, std::uint8_t& value) {
  wire_.beginTransmission(address_);
  wire_.write(reg);
  if (wire_.endTransmission(false) != 0) return false;
  if (wire_.requestFrom(address_, static_cast<std::uint8_t>(1)) != 1) return false;
  value = static_cast<std::uint8_t>(wire_.read());
  return true;
}

}  // namespace mocap::drivers
