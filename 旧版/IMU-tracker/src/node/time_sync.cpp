#include "node/time_sync.hpp"

#include <limits>

namespace mocap::node {

TimeSyncEstimate TimeSync::estimate(std::uint64_t t1, std::uint64_t t2,
                                    std::uint64_t t3, std::uint64_t t4) {
  TimeSyncEstimate result{};
  if (t4 < t1 || t3 < t2 || (t4 - t1) < (t3 - t2)) return result;
  const std::uint64_t rtt = (t4 - t1) - (t3 - t2);
  if (rtt > std::numeric_limits<std::uint32_t>::max()) return result;
  const auto forward = static_cast<std::int64_t>(t2) - static_cast<std::int64_t>(t1);
  const auto reverse = static_cast<std::int64_t>(t3) - static_cast<std::int64_t>(t4);
  result.offset_us = (forward + reverse) / 2;
  result.round_trip_us = static_cast<std::uint32_t>(rtt);
  result.valid = true;
  return result;
}

}  // namespace mocap::node
