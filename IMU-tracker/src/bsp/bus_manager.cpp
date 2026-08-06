#include "bsp/bus_manager.hpp"

#include <Arduino.h>

#include "bsp/board_pins.hpp"

namespace mocap::bsp {

BusManager::BusManager() : pmic_wire_(0), mag_wire_(1) {}

BusManager& BusManager::instance() {
  static BusManager manager;
  return manager;
}

bool BusManager::begin() {
  if (started_) return true;

  pinMode(pins::kIcmCs, OUTPUT);
  digitalWrite(pins::kIcmCs, HIGH);
  pinMode(pins::kIcmInt1, INPUT);
  pinMode(pins::kPmicIrq, INPUT_PULLUP);

  SPI.begin(pins::kIcmSck, pins::kIcmMiso, pins::kIcmMosi, pins::kIcmCs);
  status_.sensor_spi = true;
  status_.pmic_i2c = pmic_wire_.begin(pins::kPmicSda, pins::kPmicScl, 400000U);
  status_.magnetometer_i2c = mag_wire_.begin(pins::kMagSda, pins::kMagScl, 400000U);
  // Each controller has an independent health state. A failed optional I2C bus
  // must not prevent SPI IMU acquisition or the other I2C controller from use.
  started_ = true;
  return status_.sensor_spi;
}

}  // namespace mocap::bsp
