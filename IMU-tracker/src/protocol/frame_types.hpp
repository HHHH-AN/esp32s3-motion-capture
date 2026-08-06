#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace mocap::protocol {

inline constexpr std::array<std::uint8_t, 2> kMagic{0x4D, 0x43};
inline constexpr std::uint8_t kProtocolVersion = 1;
inline constexpr std::size_t kHeaderSize = 19;
inline constexpr std::size_t kRawSamplePayloadSize = 24;
inline constexpr std::size_t kCrcSize = 2;
// RAW_BATCH v1 needs 1 + 14 * 37 = 519 bytes. Leave headroom for future status
// extensions while individual ESP-NOW leaf packets remain below 250 bytes.
inline constexpr std::size_t kMaxPayloadSize = 768;
inline constexpr std::size_t kMaxDecodedFrameSize = kHeaderSize + kMaxPayloadSize + kCrcSize;
inline constexpr std::size_t kMaxEncodedFrameSize = kMaxDecodedFrameSize + (kMaxDecodedFrameSize / 254) + 2;

enum class FrameType : std::uint8_t {
  RawSample = 1,
  RawBatch = 2,
  DeviceStatus = 3,
  Control = 4,
  ControlAck = 5,
  TimeSync = 6,
  Error = 7,
};

struct FrameHeader {
  FrameType type{FrameType::Error};
  std::uint16_t payload_length{0};
  std::uint8_t node_id{0};
  std::uint32_t sequence{0};
  std::uint64_t timestamp_us{0};
};

struct EncodedFrame {
  std::array<std::uint8_t, kMaxEncodedFrameSize> bytes{};
  std::size_t size{0};
};

}  // namespace mocap::protocol
