#include "drivers/icm42688_driver.hpp"

#include <Arduino.h>

#include "bsp/monotonic_clock.hpp"
#include "drivers/icm42688_regs.hpp"

namespace mocap::drivers {
namespace {

std::int16_t readBeI16(const std::uint8_t* data) {
  return static_cast<std::int16_t>((static_cast<std::uint16_t>(data[0]) << 8U) | data[1]);
}

}  // namespace

bool Icm42688Driver::begin() {
  pinMode(cs_pin_, OUTPUT);
  digitalWrite(cs_pin_, HIGH);
  std::uint8_t id = 0;
  if (!readWhoAmI(id) || id != icm42688::kExpectedWhoAmI) return false;
  if (!writeRegister(icm42688::kDeviceConfig, icm42688::kSoftReset)) return false;
  delay(5);
  if (!readWhoAmI(id) || id != icm42688::kExpectedWhoAmI) return false;

  // FS_SEL=0: +-2000 dps / +-16 g. ODR code 0x08: 100 Hz.
  if (!writeRegister(icm42688::kGyroConfig0,
                     icm42688::kGyro2000Dps | icm42688::kOdr100Hz)) return false;
  if (!writeRegister(icm42688::kAccelConfig0,
                     icm42688::kAccel16g | icm42688::kOdr100Hz)) return false;
  // Gyro and accelerometer low-noise modes. Polling remains the safe default.
  if (!writeRegister(0x4E, 0x0F)) return false;
  delay(50);
  configured_ = true;
  return true;
}

bool Icm42688Driver::readWhoAmI(std::uint8_t& value) {
  return readRegisters(icm42688::kWhoAmI, &value, 1);
}

bool Icm42688Driver::readPolling(core::ImuReading& reading) {
  reading = {};
  if (!configured_) return false;
  std::uint8_t raw[14]{};
  if (!readRegisters(icm42688::kTempData1, raw, sizeof(raw))) return false;
  const std::int16_t temp = readBeI16(raw);
  for (std::size_t i = 0; i < 3; ++i) {
    reading.accel_g[i] = static_cast<float>(readBeI16(&raw[2 + i * 2])) / 2048.0F;
    reading.gyro_dps[i] = static_cast<float>(readBeI16(&raw[8 + i * 2])) / 16.4F;
  }
  reading.temperature_c = static_cast<float>(temp) / 132.48F + 25.0F;
  reading.timestamp_us = bsp::MonotonicClock::nowUs();
  reading.valid = true;
  return true;
}

bool Icm42688Driver::enableFifoInterrupt(std::uint16_t watermark_bytes) {
  if (!configured_ || watermark_bytes == 0 || watermark_bytes > 0x0FFFU) return false;
  // Standard FIFO packets: accel + gyro + temperature + timestamp. This path is
  // compile-time disabled until GPIO8 polarity and FIFO packet bytes are observed
  // on a real board.
  if (!writeRegister(icm42688::kFifoConfig, 0x00)) return false;  // bypass while configuring
  if (!writeRegister(icm42688::kFifoConfig2, static_cast<std::uint8_t>(watermark_bytes)))
    return false;
  if (!writeRegister(icm42688::kFifoConfig3,
                     static_cast<std::uint8_t>((watermark_bytes >> 8U) & 0x0FU))) return false;
  if (!writeRegister(icm42688::kFifoConfig1, 0x07)) return false;  // temp, gyro, accel
  if (!writeRegister(icm42688::kIntConfig, 0x03)) return false;   // INT1 high, push-pull
  // Datasheet 14.50: clear INT_CONFIG1 bit 4 before using INT1.
  if (!writeRegister(icm42688::kIntConfig1, 0x00)) return false;
  if (!writeRegister(icm42688::kIntSource0, 0x04)) return false;  // FIFO threshold -> INT1
  return writeRegister(icm42688::kFifoConfig, 0x40);              // stream mode
}

bool Icm42688Driver::fifoCount(std::uint16_t& bytes) {
  std::uint8_t raw[2]{};
  if (!readRegisters(icm42688::kFifoCountH, raw, sizeof(raw))) return false;
  bytes = static_cast<std::uint16_t>(((static_cast<std::uint16_t>(raw[0]) & 0x0FU) << 8U) |
                                     raw[1]);
  return true;
}

bool Icm42688Driver::parseLatestStandardFifoPacket(const std::uint8_t* data, std::size_t size,
                                                    core::ImuReading& reading) {
  // A standard accel+gyro+temp+timestamp packet is 16 bytes including its header.
  // Walk from the end so a delayed task consumes the newest complete packet.
  constexpr std::size_t kPacketSize = 16;
  reading = {};
  if (data == nullptr || size < kPacketSize) return false;
  const std::uint8_t* packet = data + size - kPacketSize;
  const std::uint8_t header = packet[0];
  const bool has_accel = (header & 0x40U) != 0;
  const bool has_gyro = (header & 0x20U) != 0;
  if (!has_accel || !has_gyro || (header & 0x80U) != 0) return false;
  for (std::size_t i = 0; i < 3; ++i) {
    reading.accel_g[i] = static_cast<float>(readBeI16(&packet[1 + i * 2])) / 2048.0F;
    reading.gyro_dps[i] = static_cast<float>(readBeI16(&packet[7 + i * 2])) / 16.4F;
  }
  reading.temperature_c = static_cast<float>(static_cast<std::int8_t>(packet[13])) / 2.07F + 25.0F;
  reading.timestamp_us = bsp::MonotonicClock::nowUs();
  reading.valid = true;
  return true;
}

bool Icm42688Driver::readFifo(std::uint8_t* output, std::size_t capacity,
                              std::size_t& bytes_read) {
  bytes_read = 0;
  std::uint16_t available = 0;
  if (output == nullptr || !fifoCount(available)) return false;
  if (available > capacity) {
    (void)flushFifo();
    return false;
  }
  if (available == 0) return true;
  if (!readRegisters(icm42688::kFifoData, output, available)) return false;
  bytes_read = available;
  return true;
}

bool Icm42688Driver::flushFifo() {
  return writeRegister(icm42688::kSignalPathReset, 0x04);
}

bool Icm42688Driver::readRegisters(std::uint8_t reg, std::uint8_t* data, std::size_t size) {
  if (data == nullptr || size == 0) return false;
  spi_.beginTransaction(settings_);
  digitalWrite(cs_pin_, LOW);
  spi_.transfer(static_cast<std::uint8_t>(reg | 0x80U));
  for (std::size_t i = 0; i < size; ++i) data[i] = spi_.transfer(0x00);
  digitalWrite(cs_pin_, HIGH);
  spi_.endTransaction();
  return true;
}

bool Icm42688Driver::writeRegister(std::uint8_t reg, std::uint8_t value) {
  spi_.beginTransaction(settings_);
  digitalWrite(cs_pin_, LOW);
  spi_.transfer(static_cast<std::uint8_t>(reg & 0x7FU));
  spi_.transfer(value);
  digitalWrite(cs_pin_, HIGH);
  spi_.endTransaction();
  delayMicroseconds(10);
  return true;
}

}  // namespace mocap::drivers
