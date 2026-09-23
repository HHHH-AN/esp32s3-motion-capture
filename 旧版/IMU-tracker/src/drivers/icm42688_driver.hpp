#pragma once

#include <SPI.h>

#include <cstddef>
#include <cstdint>

#include "core/motion_types.hpp"

namespace mocap::drivers {

class Icm42688Driver final {
 public:
  Icm42688Driver(SPIClass& spi, std::int8_t cs_pin) : spi_(spi), cs_pin_(cs_pin) {}

  bool begin();
  bool readWhoAmI(std::uint8_t& value);
  bool readPolling(core::ImuReading& reading);
  bool enableFifoInterrupt(std::uint16_t watermark_bytes = 16);
  bool fifoCount(std::uint16_t& bytes);
  bool flushFifo();
  bool readFifo(std::uint8_t* output, std::size_t capacity, std::size_t& bytes_read);
  bool parseLatestStandardFifoPacket(const std::uint8_t* data, std::size_t size,
                                     core::ImuReading& reading);

 private:
  bool readRegisters(std::uint8_t reg, std::uint8_t* data, std::size_t size);
  bool writeRegister(std::uint8_t reg, std::uint8_t value);
  SPIClass& spi_;
  std::int8_t cs_pin_;
  SPISettings settings_{8'000'000U, SPI_MSBFIRST, SPI_MODE0};
  bool configured_{false};
};

}  // namespace mocap::drivers
