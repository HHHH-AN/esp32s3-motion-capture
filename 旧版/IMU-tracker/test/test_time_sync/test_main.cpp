#include <unity.h>

#include "node/time_sync.hpp"

namespace {

void test_ntp_style_offset_and_round_trip_estimate() {
  const auto estimate = mocap::node::TimeSync::estimate(1'000, 1'200, 1'250, 1'150);
  TEST_ASSERT_TRUE(estimate.valid);
  TEST_ASSERT_EQUAL_INT64(150, estimate.offset_us);
  TEST_ASSERT_EQUAL_UINT32(100, estimate.round_trip_us);
}

void test_invalid_timestamp_order_is_rejected() {
  const auto estimate = mocap::node::TimeSync::estimate(1'000, 1'200, 1'250, 900);
  TEST_ASSERT_FALSE(estimate.valid);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_ntp_style_offset_and_round_trip_estimate);
  RUN_TEST(test_invalid_timestamp_order_is_rejected);
  return UNITY_END();
}
