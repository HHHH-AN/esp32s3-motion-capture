#pragma once

#include <cstddef>
#include <cstdint>

#include "core/motion_types.hpp"
#include "protocol/frame_types.hpp"

namespace mocap::protocol {

class WireCodec final {
 public:
  static bool encodeRawSample(std::uint8_t node_id, std::uint32_t sequence,
                              const core::MotionSample& sample, EncodedFrame& output);
  static bool encodeFrame(const FrameHeader& header, const std::uint8_t* payload,
                          std::size_t payload_size, EncodedFrame& output);
  static std::size_t cobsEncode(const std::uint8_t* input, std::size_t input_size,
                                std::uint8_t* output, std::size_t output_capacity);
  static std::size_t cobsDecode(const std::uint8_t* input, std::size_t input_size,
                                std::uint8_t* output, std::size_t output_capacity);
};

}  // namespace mocap::protocol
