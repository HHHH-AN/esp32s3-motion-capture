#pragma once

#include <cstdint>

namespace mocap::drivers::icm42688 {

inline constexpr std::uint8_t kDeviceConfig = 0x11;
inline constexpr std::uint8_t kIntConfig = 0x14;
inline constexpr std::uint8_t kFifoConfig = 0x16;
inline constexpr std::uint8_t kTempData1 = 0x1D;
inline constexpr std::uint8_t kIntStatus = 0x2D;
inline constexpr std::uint8_t kFifoCountH = 0x2E;
inline constexpr std::uint8_t kFifoData = 0x30;
inline constexpr std::uint8_t kGyroConfig0 = 0x4F;
inline constexpr std::uint8_t kAccelConfig0 = 0x50;
inline constexpr std::uint8_t kSignalPathReset = 0x4B;
inline constexpr std::uint8_t kFifoConfig1 = 0x5F;
inline constexpr std::uint8_t kFifoConfig2 = 0x60;
inline constexpr std::uint8_t kFifoConfig3 = 0x61;
inline constexpr std::uint8_t kIntSource0 = 0x65;
inline constexpr std::uint8_t kIntConfig1 = 0x64;
inline constexpr std::uint8_t kWhoAmI = 0x75;

inline constexpr std::uint8_t kExpectedWhoAmI = 0x47;
inline constexpr std::uint8_t kSoftReset = 0x01;
inline constexpr std::uint8_t kOdr100Hz = 0x08;
inline constexpr std::uint8_t kAccel16g = 0x00;
inline constexpr std::uint8_t kGyro2000Dps = 0x00;

}  // namespace mocap::drivers::icm42688
