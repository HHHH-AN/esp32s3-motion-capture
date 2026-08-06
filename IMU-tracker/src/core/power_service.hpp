#pragma once

#include "drivers/axp2101_driver.hpp"

namespace mocap::core {

class PowerService final {
 public:
  explicit PowerService(drivers::Axp2101Driver& driver) : driver_(driver) {}
  bool begin();
  bool refresh();
  const drivers::Axp2101Status& status() const { return status_; }

 private:
  drivers::Axp2101Driver& driver_;
  drivers::Axp2101Status status_{};
};

}  // namespace mocap::core
