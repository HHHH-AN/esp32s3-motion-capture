#include "lifecycle/power_policy.hpp"

namespace mocap::lifecycle {

PowerAction PowerPolicy::evaluate(std::uint16_t battery_mv, bool vbus_present) const {
  if (vbus_present) return PowerAction::Continue;
  // Conservative placeholders: verify them against the selected cell and AXP
  // measurements before connecting actions to actual regulator shutdown.
  if (battery_mv < 3200) return PowerAction::SafeShutdown;
  if (battery_mv < 3350) return PowerAction::StopStreaming;
  if (battery_mv < 3500) return PowerAction::WarnLowBattery;
  return PowerAction::Continue;
}

}  // namespace mocap::lifecycle
