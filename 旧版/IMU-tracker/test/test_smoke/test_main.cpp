#include <Arduino.h>
#include <unity.h>

#include "bsp/board_pins.hpp"
#include "config/app_config.hpp"

void test_hardware_contract_constants() {
  TEST_ASSERT_EQUAL_INT8(8, mocap::bsp::pins::kIcmInt1);
  TEST_ASSERT_EQUAL_INT8(19, mocap::bsp::pins::kUsbDm);
  TEST_ASSERT_EQUAL_INT8(20, mocap::bsp::pins::kUsbDp);
  TEST_ASSERT_EQUAL_UINT32(100, mocap::config::kSampleRateHz);
}

void setup() {
  delay(1000);
  UNITY_BEGIN();
  RUN_TEST(test_hardware_contract_constants);
  UNITY_END();
}

void loop() {}
