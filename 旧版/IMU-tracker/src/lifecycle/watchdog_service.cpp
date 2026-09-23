#include "lifecycle/watchdog_service.hpp"

namespace mocap::lifecycle {

void WatchdogService::heartbeat(std::size_t task, std::uint64_t now_us) {
  if (task < heartbeats_.size()) heartbeats_[task] = now_us;
}

bool WatchdogService::healthy(std::uint64_t now_us, std::uint64_t timeout_us) const {
  for (const auto heartbeat : heartbeats_) {
    if (heartbeat != 0 && now_us >= heartbeat && now_us - heartbeat > timeout_us) return false;
  }
  return true;
}

}  // namespace mocap::lifecycle
