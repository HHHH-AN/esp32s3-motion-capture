#pragma once

#include <cstddef>
#include <cstdint>

namespace mocap::protocol {

std::uint16_t crc16CcittFalse(const std::uint8_t* data, std::size_t size);

}  // namespace mocap::protocol
