#pragma once

#include <cstdint>

namespace mocap::lifecycle {

enum class PowerAction : std::uint8_t { Continue, WarnLowBattery, StopStreaming, SafeShutdown };

class PowerPolicy final {
 public:
  PowerAction evaluate(std::uint16_t battery_mv, bool vbus_present) const;
};

}  // namespace mocap::lifecycle
