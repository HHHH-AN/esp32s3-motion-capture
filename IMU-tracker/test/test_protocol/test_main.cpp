#include <unity.h>

#include <array>
#include <cstdint>

#include "core/motion_types.hpp"
#include "core/deadline_scheduler.hpp"
#include "protocol/crc16.hpp"
#include "protocol/frame_types.hpp"
#include "protocol/wire_codec.hpp"
#include "transport/ble/ble_fragmenter.hpp"

namespace {

std::uint16_t readU16(const std::uint8_t* data) {
  return static_cast<std::uint16_t>(data[0]) |
         (static_cast<std::uint16_t>(data[1]) << 8U);
}

std::uint32_t readU32(const std::uint8_t* data) {
  return static_cast<std::uint32_t>(data[0]) |
         (static_cast<std::uint32_t>(data[1]) << 8U) |
         (static_cast<std::uint32_t>(data[2]) << 16U) |
         (static_cast<std::uint32_t>(data[3]) << 24U);
}

void test_crc_standard_vector() {
  constexpr char text[] = "123456789";
  TEST_ASSERT_EQUAL_HEX16(
      0x29B1,
      mocap::protocol::crc16CcittFalse(reinterpret_cast<const std::uint8_t*>(text), 9));
}

void test_cobs_round_trip_with_zeros() {
  const std::array<std::uint8_t, 9> input{0, 1, 2, 0, 0, 3, 4, 5, 0};
  std::array<std::uint8_t, 16> encoded{};
  std::array<std::uint8_t, 16> decoded{};
  const auto encoded_size = mocap::protocol::WireCodec::cobsEncode(
      input.data(), input.size(), encoded.data(), encoded.size());
  TEST_ASSERT_GREATER_THAN(0, encoded_size);
  const auto decoded_size = mocap::protocol::WireCodec::cobsDecode(
      encoded.data(), encoded_size, decoded.data(), decoded.size());
  TEST_ASSERT_EQUAL(input.size(), decoded_size);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(input.data(), decoded.data(), input.size());
}

void test_raw_sample_v1_layout_and_crc() {
  mocap::core::MotionSample sample{};
  sample.accel_mg = {1, -2, 3};
  sample.gyro_dps_x10 = {-4, 5, -6};
  sample.mag_ut_x10 = {7, 8, -9};
  sample.temperature_c_x100 = 2534;
  sample.mag_age_us = 10000;
  sample.status_flags = 0x000F;
  sample.timestamp_us = 0x0102030405060708ULL;

  mocap::protocol::EncodedFrame frame{};
  TEST_ASSERT_TRUE(mocap::protocol::WireCodec::encodeRawSample(3, 0x11223344, sample, frame));
  TEST_ASSERT_EQUAL_HEX8(0, frame.bytes[frame.size - 1]);

  std::array<std::uint8_t, mocap::protocol::kMaxDecodedFrameSize> decoded{};
  const auto decoded_size = mocap::protocol::WireCodec::cobsDecode(
      frame.bytes.data(), frame.size - 1, decoded.data(), decoded.size());
  TEST_ASSERT_EQUAL(mocap::protocol::kHeaderSize + mocap::protocol::kRawSamplePayloadSize + 2,
                    decoded_size);
  TEST_ASSERT_EQUAL_HEX8(0x4D, decoded[0]);
  TEST_ASSERT_EQUAL_HEX8(0x43, decoded[1]);
  TEST_ASSERT_EQUAL_UINT8(1, decoded[2]);
  TEST_ASSERT_EQUAL_UINT8(1, decoded[3]);
  TEST_ASSERT_EQUAL_UINT16(24, readU16(&decoded[4]));
  TEST_ASSERT_EQUAL_UINT8(3, decoded[6]);
  TEST_ASSERT_EQUAL_HEX32(0x11223344, readU32(&decoded[7]));
  TEST_ASSERT_EQUAL_HEX8(0x08, decoded[11]);
  TEST_ASSERT_EQUAL_INT16(-2, static_cast<std::int16_t>(readU16(&decoded[21])));
  TEST_ASSERT_EQUAL_UINT16(10000, readU16(&decoded[39]));
  TEST_ASSERT_EQUAL_HEX16(0x000F, readU16(&decoded[41]));
  TEST_ASSERT_EQUAL_HEX16(
      mocap::protocol::crc16CcittFalse(decoded.data(), decoded_size - 2),
      readU16(&decoded[decoded_size - 2]));
}

void test_contract_golden_raw_frame_v1_exact_bytes() {
  // Mirrored from ../../contracts/golden/raw-frame-v1.json. The repository CI
  // contract check owns the source JSON; this assertion makes firmware drift a
  // byte-for-byte test failure instead of silently changing the wire format.
  constexpr std::array<std::uint8_t, 47> expected{
      0x06, 0x4d, 0x43, 0x01, 0x01, 0x18, 0x03, 0x01, 0x2a, 0x01, 0x01, 0x07,
      0xcb, 0x04, 0xfb, 0x71, 0x1f, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x06,
      0xe8, 0x03, 0xf6, 0xff, 0x14, 0x04, 0xe2, 0xff, 0xfa, 0x0a, 0x83, 0xff,
      0xf4, 0x01, 0xc4, 0x09, 0x88, 0x13, 0x03, 0x03, 0x57, 0x2e, 0x00};
  mocap::core::MotionSample sample{};
  sample.accel_mg = {0, 0, 1000};
  sample.gyro_dps_x10 = {-10, 20, -30};
  sample.mag_ut_x10 = {250, -125, 500};
  sample.temperature_c_x100 = 2500;
  sample.mag_age_us = 5000;
  sample.status_flags = 3;
  sample.timestamp_us = 1234567890123ULL;
  mocap::protocol::EncodedFrame actual{};
  TEST_ASSERT_TRUE(mocap::protocol::WireCodec::encodeRawSample(1, 42, sample, actual));
  TEST_ASSERT_EQUAL(expected.size(), actual.size);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(expected.data(), actual.bytes.data(), expected.size());
}

void test_ble_fragment_header_matches_contract() {
  std::array<std::uint8_t, 300> packet{};
  for (std::size_t i = 0; i < packet.size(); ++i) packet[i] = static_cast<std::uint8_t>(i);
  constexpr std::size_t mtu_payload = 244;
  std::array<std::uint8_t, mtu_payload> fragment{};
  TEST_ASSERT_EQUAL_UINT32(2, mocap::transport::ble::BleFragmenter::fragmentCount(
                                  packet.size(), mtu_payload));
  const auto size = mocap::transport::ble::BleFragmenter::makeFragment(
      packet.data(), packet.size(), 0x1234, 1, mtu_payload, fragment.data(), fragment.size());
  TEST_ASSERT_EQUAL_UINT32(68, size);
  TEST_ASSERT_EQUAL_HEX8(0x34, fragment[0]);
  TEST_ASSERT_EQUAL_HEX8(0x12, fragment[1]);
  TEST_ASSERT_EQUAL_UINT8(1, fragment[2]);
  TEST_ASSERT_EQUAL_UINT8(2, fragment[3]);
  TEST_ASSERT_EQUAL_HEX8(0x2C, fragment[4]);
  TEST_ASSERT_EQUAL_HEX8(0x01, fragment[5]);
  TEST_ASSERT_EQUAL_UINT8(packet[238], fragment[6]);
}

void test_deadline_does_not_underflow_when_next_is_in_future() {
  std::uint64_t next = 1'000'000;
  TEST_ASSERT_TRUE(mocap::core::advancePeriodicDeadline(1'000'000, 10'000, 5, next));
  TEST_ASSERT_EQUAL_UINT64(1'010'000, next);
  TEST_ASSERT_FALSE(mocap::core::advancePeriodicDeadline(1'001'000, 10'000, 5, next));
  TEST_ASSERT_EQUAL_UINT64(1'010'000, next);
}

void test_deadline_skips_large_catch_up_burst() {
  std::uint64_t next = 100;
  TEST_ASSERT_TRUE(mocap::core::advancePeriodicDeadline(1'000'000, 10'000, 5, next));
  TEST_ASSERT_EQUAL_UINT64(1'010'000, next);
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_crc_standard_vector);
  RUN_TEST(test_cobs_round_trip_with_zeros);
  RUN_TEST(test_raw_sample_v1_layout_and_crc);
  RUN_TEST(test_contract_golden_raw_frame_v1_exact_bytes);
  RUN_TEST(test_ble_fragment_header_matches_contract);
  RUN_TEST(test_deadline_does_not_underflow_when_next_is_in_future);
  RUN_TEST(test_deadline_skips_large_catch_up_burst);
  return UNITY_END();
}
