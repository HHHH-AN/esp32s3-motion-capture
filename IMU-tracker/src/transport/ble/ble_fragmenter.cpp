#include "transport/ble/ble_fragmenter.hpp"

#include <cstring>

namespace mocap::transport::ble {

std::size_t BleFragmenter::fragmentCount(std::size_t packet_size, std::size_t mtu_payload) {
  if (mtu_payload <= kHeaderSize) return 0;
  const std::size_t data_size = mtu_payload - kHeaderSize;
  return packet_size == 0 ? 0 : (packet_size + data_size - 1) / data_size;
}

std::size_t BleFragmenter::makeFragment(const std::uint8_t* packet, std::size_t packet_size,
                                        std::uint16_t packet_sequence,
                                        std::size_t fragment_index, std::size_t mtu_payload,
                                        std::uint8_t* output, std::size_t output_capacity) {
  const std::size_t count = fragmentCount(packet_size, mtu_payload);
  if (packet == nullptr || output == nullptr || packet_size > 0xFFFFU ||
      count == 0 || count > 255 ||
      fragment_index >= count || output_capacity < mtu_payload) return 0;
  const std::size_t data_capacity = mtu_payload - kHeaderSize;
  const std::size_t offset = fragment_index * data_capacity;
  const std::size_t remaining = packet_size - offset;
  const std::size_t data_size = remaining < data_capacity ? remaining : data_capacity;
  output[0] = static_cast<std::uint8_t>(packet_sequence);
  output[1] = static_cast<std::uint8_t>(packet_sequence >> 8U);
  output[2] = static_cast<std::uint8_t>(fragment_index);
  output[3] = static_cast<std::uint8_t>(count);
  output[4] = static_cast<std::uint8_t>(packet_size);
  output[5] = static_cast<std::uint8_t>(packet_size >> 8U);
  std::memcpy(output + kHeaderSize, packet + offset, data_size);
  return kHeaderSize + data_size;
}

}  // namespace mocap::transport::ble
