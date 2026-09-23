#pragma once

#include "core/motion_types.hpp"
#include "drivers/lis2mdl_driver.hpp"

namespace mocap::core {

class MagSampler final {
 public:
  explicit MagSampler(drivers::Lis2mdlDriver& driver) : driver_(driver) {}
  bool begin() { return driver_.begin(); }
  bool sample();
  const MagReading& latest() const { return latest_; }

 private:
  drivers::Lis2mdlDriver& driver_;
  MagReading latest_{};
};

}  // namespace mocap::core
