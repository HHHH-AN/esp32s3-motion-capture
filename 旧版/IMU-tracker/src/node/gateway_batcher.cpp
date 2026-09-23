#include "node/gateway_batcher.hpp"

#include <algorithm>

#include "protocol/crc16.hpp"
#include "protocol/frame_types.hpp"
#include "protocol/wire_codec.hpp"

namespace mocap::node {
namespace {

std::uint16_t readU16(const std::uint8_t* data) {
  return static_cast<std::uint16_t>(data[0]) |
         (static_cast<std::uint16_t>(data[1]) << 8U);
}

std::uint32_t readU32(const std::uint8_t* data) {
  std::uint32_t value = 0;
  for (std::size_t i = 0; i < 4; ++i) value |= static_cast<std::uint32_t>(data[i]) << (8U * i);
  return value;
}

}  // namespace

bool GatewayBatcher::add(const std::uint8_t source_mac[6], const std::uint8_t* encoded,
                         std::size_t encoded_size, std::uint64_t gateway_time_us) {
  if (source_mac == nullptr || encoded == nullptr || encoded_size < 2 ||
      encoded[encoded_size - 1] != 0) return false;

  std::array<std::uint8_t, protocol::kMaxDecodedFrameSize> decoded{};
  const std::size_t size = protocol::WireCodec::cobsDecode(
      encoded, encoded_size - 1, decoded.data(), decoded.size());
  constexpr std::size_t kRawDecodedSize = protocol::kHeaderSize +
                                           protocol::kRawSamplePayloadSize + protocol::kCrcSize;
  if (size != kRawDecodedSize || decoded[0] != protocol::kMagic[0] ||
      decoded[1] != protocol::kMagic[1] || decoded[2] != protocol::kProtocolVersion ||
      decoded[3] != static_cast<std::uint8_t>(protocol::FrameType::RawSample) ||
      readU16(&decoded[4]) != protocol::kRawSamplePayloadSize) return false;
  const std::uint16_t received_crc = readU16(&decoded[size - 2]);
  if (received_crc != protocol::crc16CcittFalse(decoded.data(), size - 2)) return false;

  const std::uint8_t node_id = decoded[6];
  if (node_id == 0 || node_id >= pending_.size()) return false;
  if (!registry_.observe(node_id, source_mac, readU32(&decoded[7]), gateway_time_us)) return false;

  auto& item = pending_[node_id];
  if (!item.present) {
    item.present = true;
    ++pending_count_;
  }
  // Batch item is node_id + sequence + node timestamp + 24-byte RAW_SAMPLE payload.
  std::copy_n(&decoded[6], item.bytes.size(), item.bytes.data());
  return true;
}

bool GatewayBatcher::flush(std::uint64_t gateway_time_us) {
  if (pending_count_ == 0) return true;
  std::array<std::uint8_t, 1 + 14 * 37> payload{};
  std::uint8_t* cursor = payload.data();
  *cursor++ = static_cast<std::uint8_t>(pending_count_);
  for (std::size_t node_id = 1; node_id < pending_.size(); ++node_id) {
    auto& item = pending_[node_id];
    if (!item.present) continue;
    std::copy(item.bytes.begin(), item.bytes.end(), cursor);
    cursor += item.bytes.size();
    item.present = false;
  }
  const std::size_t payload_size = static_cast<std::size_t>(cursor - payload.data());
  pending_count_ = 0;
  protocol::EncodedFrame frame{};
  const protocol::FrameHeader header{protocol::FrameType::RawBatch,
                                     static_cast<std::uint16_t>(payload_size), 0,
                                     batch_sequence_++, gateway_time_us};
  return protocol::WireCodec::encodeFrame(header, payload.data(), payload_size, frame) &&
         output_.send(frame.bytes.data(), frame.size);
}

}  // namespace mocap::node
