#pragma once

#include <cstdint>

namespace mocap::bsp::pins {

inline constexpr std::int8_t kIcmInt1 = 8;
inline constexpr std::int8_t kIcmCs = 9;
inline constexpr std::int8_t kIcmMosi = 10;
inline constexpr std::int8_t kIcmSck = 11;
inline constexpr std::int8_t kIcmMiso = 12;

inline constexpr std::int8_t kMagSda = 35;
inline constexpr std::int8_t kMagScl = 36;

inline constexpr std::int8_t kPmicSda = 33;
inline constexpr std::int8_t kPmicScl = 47;
inline constexpr std::int8_t kPmicIrq = 48;

inline constexpr std::int8_t kUsbDm = 19;
inline constexpr std::int8_t kUsbDp = 20;

static_assert(kIcmCs != kIcmInt1 && kMagSda != kPmicSda && kMagScl != kPmicScl,
              "contracted buses must not share pins");

}  // namespace mocap::bsp::pins
