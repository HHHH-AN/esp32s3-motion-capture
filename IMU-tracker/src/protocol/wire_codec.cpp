#include "protocol/wire_codec.hpp"

#include <array>

#include "protocol/crc16.hpp"

namespace mocap::protocol {
namespace {

void putU16(std::uint8_t*& out, std::uint16_t value) {
  *out++ = static_cast<std::uint8_t>(value);
  *out++ = static_cast<std::uint8_t>(value >> 8U);
}

void putI16(std::uint8_t*& out, std::int16_t value) {
  putU16(out, static_cast<std::uint16_t>(value));
}

void putU32(std::uint8_t*& out, std::uint32_t value) {
  for (std::uint8_t i = 0; i < 4; ++i) *out++ = static_cast<std::uint8_t>(value >> (8U * i));
}

void putU64(std::uint8_t*& out, std::uint64_t value) {
  for (std::uint8_t i = 0; i < 8; ++i) *out++ = static_cast<std::uint8_t>(value >> (8U * i));
}

}  // namespace

bool WireCodec::encodeRawSample(std::uint8_t node_id, std::uint32_t sequence,
                                const core::MotionSample& sample, EncodedFrame& output) {
  std::array<std::uint8_t, kRawSamplePayloadSize> payload{};
  std::uint8_t* cursor = payload.data();
  for (const auto value : sample.accel_mg) putI16(cursor, value);
  for (const auto value : sample.gyro_dps_x10) putI16(cursor, value);
  for (const auto value : sample.mag_ut_x10) putI16(cursor, value);
  putI16(cursor, sample.temperature_c_x100);
  putU16(cursor, sample.mag_age_us);
  putU16(cursor, sample.status_flags);

  const FrameHeader header{FrameType::RawSample, static_cast<std::uint16_t>(payload.size()),
                           node_id, sequence, sample.timestamp_us};
  return encodeFrame(header, payload.data(), payload.size(), output);
}

bool WireCodec::encodeFrame(const FrameHeader& header, const std::uint8_t* payload,
                            std::size_t payload_size, EncodedFrame& output) {
  if (payload_size > kMaxPayloadSize || payload_size != header.payload_length ||
      (payload_size > 0 && payload == nullptr)) {
    return false;
  }

  std::array<std::uint8_t, kMaxDecodedFrameSize> decoded{};
  std::uint8_t* cursor = decoded.data();
  *cursor++ = kMagic[0];
  *cursor++ = kMagic[1];
  *cursor++ = kProtocolVersion;
  *cursor++ = static_cast<std::uint8_t>(header.type);
  putU16(cursor, header.payload_length);
  *cursor++ = header.node_id;
  putU32(cursor, header.sequence);
  putU64(cursor, header.timestamp_us);
  for (std::size_t i = 0; i < payload_size; ++i) *cursor++ = payload[i];
  const std::size_t without_crc = static_cast<std::size_t>(cursor - decoded.data());
  putU16(cursor, crc16CcittFalse(decoded.data(), without_crc));
  const std::size_t decoded_size = static_cast<std::size_t>(cursor - decoded.data());

  const std::size_t encoded_size =
      cobsEncode(decoded.data(), decoded_size, output.bytes.data(), output.bytes.size() - 1);
  if (encoded_size == 0 || encoded_size >= output.bytes.size()) return false;
  output.bytes[encoded_size] = 0;
  output.size = encoded_size + 1;
  return true;
}

std::size_t WireCodec::cobsEncode(const std::uint8_t* input, std::size_t input_size,
                                  std::uint8_t* output, std::size_t output_capacity) {
  if (output_capacity == 0 || (input_size > 0 && (input == nullptr || output == nullptr))) return 0;
  std::size_t read = 0;
  std::size_t write = 1;
  std::size_t code_index = 0;
  std::uint8_t code = 1;

  while (read < input_size) {
    if (input[read] == 0) {
      if (code_index >= output_capacity) return 0;
      output[code_index] = code;
      code = 1;
      code_index = write++;
      if (write > output_capacity) return 0;
      ++read;
    } else {
      if (write >= output_capacity) return 0;
      output[write++] = input[read++];
      ++code;
      if (code == 0xFF) {
        output[code_index] = code;
        code = 1;
        code_index = write++;
        if (write > output_capacity) return 0;
      }
    }
  }
  if (code_index >= output_capacity) return 0;
  output[code_index] = code;
  return write;
}

std::size_t WireCodec::cobsDecode(const std::uint8_t* input, std::size_t input_size,
                                  std::uint8_t* output, std::size_t output_capacity) {
  if (input == nullptr || output == nullptr) return 0;
  std::size_t read = 0;
  std::size_t write = 0;
  while (read < input_size) {
    const std::uint8_t code = input[read++];
    if (code == 0) return 0;
    for (std::uint8_t i = 1; i < code; ++i) {
      if (read >= input_size || write >= output_capacity) return 0;
      output[write++] = input[read++];
    }
    if (code != 0xFF && read < input_size) {
      if (write >= output_capacity) return 0;
      output[write++] = 0;
    }
  }
  return write;
}

}  // namespace mocap::protocol
