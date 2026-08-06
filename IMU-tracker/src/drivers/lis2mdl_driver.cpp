#include "drivers/lis2mdl_driver.hpp"

#include "bsp/monotonic_clock.hpp"

namespace mocap::drivers {
namespace {
constexpr std::uint8_t kWhoAmI = 0x4F;
constexpr std::uint8_t kExpectedWhoAmI = 0x40;
constexpr std::uint8_t kCfgRegA = 0x60;
constexpr std::uint8_t kCfgRegB = 0x61;
constexpr std::uint8_t kOutXl = 0x68;

std::int16_t readLeI16(const std::uint8_t* data) {
  return static_cast<std::int16_t>((static_cast<std::uint16_t>(data[1]) << 8U) | data[0]);
}
}

bool Lis2mdlDriver::begin() {
  std::uint8_t id = 0;
  if (!readWhoAmI(id) || id != kExpectedWhoAmI) return false;
  // TEMP_COMP=1, ODR=100 Hz, continuous mode.
  if (!writeRegister(kCfgRegA, 0x8CU)) return false;
  // Offset cancellation enabled for continuous mode.
  if (!writeRegister(kCfgRegB, 0x02U)) return false;
  configured_ = true;
  return true;
}

bool Lis2mdlDriver::readWhoAmI(std::uint8_t& value) {
  return readRegisters(kWhoAmI, &value, 1);
}

bool Lis2mdlDriver::readPolling(core::MagReading& reading) {
  reading = {};
  if (!configured_) return false;
  std::uint8_t raw[6]{};
  if (!readRegisters(kOutXl, raw, sizeof(raw))) return false;
  // LIS2MDL sensitivity is 1.5 mgauss/LSB = 0.15 uT/LSB.
  for (std::size_t i = 0; i < 3; ++i) {
    reading.field_ut[i] = static_cast<float>(readLeI16(&raw[i * 2])) * 0.15F;
  }
  reading.timestamp_us = bsp::MonotonicClock::nowUs();
  reading.valid = true;
  return true;
}

bool Lis2mdlDriver::readRegisters(std::uint8_t reg, std::uint8_t* data, std::uint8_t size) {
  if (data == nullptr || size == 0) return false;
  wire_.beginTransmission(address_);
  wire_.write(reg);
  if (wire_.endTransmission(false) != 0) return false;
  if (wire_.requestFrom(address_, size) != size) return false;
  for (std::uint8_t i = 0; i < size; ++i) data[i] = static_cast<std::uint8_t>(wire_.read());
  return true;
}

bool Lis2mdlDriver::writeRegister(std::uint8_t reg, std::uint8_t value) {
  wire_.beginTransmission(address_);
  wire_.write(reg);
  wire_.write(value);
  return wire_.endTransmission(true) == 0;
}

}  // namespace mocap::drivers
