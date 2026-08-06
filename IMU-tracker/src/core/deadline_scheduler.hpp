#pragma once

#include <cstdint>

namespace mocap::core {

// Returns true once when a deadline is due and advances it by one period. If the
// caller is more than max_late_periods behind, skip catch-up bursts and schedule
// the next event one complete period in the future.
inline bool advancePeriodicDeadline(std::uint64_t now_us, std::uint64_t period_us,
                                    std::uint32_t max_late_periods,
                                    std::uint64_t& next_deadline_us) {
  if (period_us == 0 || now_us < next_deadline_us) return false;
  next_deadline_us += period_us;
  const std::uint64_t allowed_lag = period_us * max_late_periods;
  if (now_us > next_deadline_us && now_us - next_deadline_us > allowed_lag)
    next_deadline_us = now_us + period_us;
  return true;
}

}  // namespace mocap::core
