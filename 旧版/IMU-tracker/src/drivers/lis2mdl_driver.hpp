#pragma once

#include <Wire.h>

#include <cstdint>

#include "core/motion_types.hpp"

namespace mocap::drivers {

class Lis2mdlDriver final {
 public:
  explicit Lis2mdlDriver(TwoWire& wire, std::uint8_t address = 0x1E)
      : wire_(wire), address_(address) {}

  bool begin();
  bool readWhoAmI(std::uint8_t& value);
  bool readPolling(core::MagReading& reading);

 private:
  bool readRegisters(std::uint8_t reg, std::uint8_t* data, std::uint8_t size);
  bool writeRegister(std::uint8_t reg, std::uint8_t value);
  TwoWire& wire_;
  std::uint8_t address_;
  bool configured_{false};
};

}  // namespace mocap::drivers
