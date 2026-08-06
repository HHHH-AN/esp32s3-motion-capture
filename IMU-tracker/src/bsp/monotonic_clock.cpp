#include "bsp/monotonic_clock.hpp"

#include <esp_timer.h>

namespace mocap::bsp {

std::uint64_t MonotonicClock::nowUs() {
  return static_cast<std::uint64_t>(esp_timer_get_time());
}

}  // namespace mocap::bsp
