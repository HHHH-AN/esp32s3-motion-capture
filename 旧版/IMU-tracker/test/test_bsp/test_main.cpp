#include <Arduino.h>
#include <unity.h>

#include "bsp/board_pins.hpp"
#include "config/app_config.hpp"

namespace {

void test_hardware_contract_pin_map() {
  TEST_ASSERT_EQUAL_INT8(8, mocap::bsp::pins::kIcmInt1);
  TEST_ASSERT_EQUAL_INT8(9, mocap::bsp::pins::kIcmCs);
  TEST_ASSERT_EQUAL_INT8(33, mocap::bsp::pins::kPmicSda);
  TEST_ASSERT_EQUAL_INT8(47, mocap::bsp::pins::kPmicScl);
  TEST_ASSERT_EQUAL_INT8(35, mocap::bsp::pins::kMagSda);
  TEST_ASSERT_EQUAL_INT8(36, mocap::bsp::pins::kMagScl);
  TEST_ASSERT_EQUAL_INT8(19, mocap::bsp::pins::kUsbDm);
  TEST_ASSERT_EQUAL_INT8(20, mocap::bsp::pins::kUsbDp);
  TEST_ASSERT_EQUAL_UINT32(100, mocap::config::kSampleRateHz);
}

}  // namespace

void setup() {
  delay(500);
  UNITY_BEGIN();
  RUN_TEST(test_hardware_contract_pin_map);
  UNITY_END();
}

void loop() {}
