#pragma once

#include <cstddef>
#include <cstdint>

namespace mocap::transport::ble {

struct FragmentHeader {
  std::uint16_t frame_id;
  std::uint8_t fragment_index;
  std::uint8_t fragment_count;
  std::uint16_t total_frame_length;
};

class BleFragmenter final {
 public:
  static constexpr std::size_t kHeaderSize = 6;
  static std::size_t fragmentCount(std::size_t packet_size, std::size_t mtu_payload);
  static std::size_t makeFragment(const std::uint8_t* packet, std::size_t packet_size,
                                  std::uint16_t packet_sequence, std::size_t fragment_index,
                                  std::size_t mtu_payload, std::uint8_t* output,
                                  std::size_t output_capacity);
};

}  // namespace mocap::transport::ble
