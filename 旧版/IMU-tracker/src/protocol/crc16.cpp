#include "protocol/crc16.hpp"

namespace mocap::protocol {

std::uint16_t crc16CcittFalse(const std::uint8_t* data, std::size_t size) {
  std::uint16_t crc = 0xFFFFU;
  for (std::size_t i = 0; i < size; ++i) {
    crc ^= static_cast<std::uint16_t>(data[i]) << 8U;
    for (std::uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x8000U) != 0U ? static_cast<std::uint16_t>((crc << 1U) ^ 0x1021U)
                                  : static_cast<std::uint16_t>(crc << 1U);
    }
  }
  return crc;
}

}  // namespace mocap::protocol
