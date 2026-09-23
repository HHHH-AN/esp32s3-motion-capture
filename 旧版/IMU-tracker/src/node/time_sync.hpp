#pragma once

#include <cstdint>

namespace mocap::node {

struct TimeSyncEstimate {
  std::int64_t offset_us{0};
  std::uint32_t round_trip_us{0};
  bool valid{false};
};

class TimeSync final {
 public:
  // Four timestamps use the NTP convention: gateway send t1, node receive t2,
  // node send t3 and gateway receive t4.
  static TimeSyncEstimate estimate(std::uint64_t t1, std::uint64_t t2,
                                   std::uint64_t t3, std::uint64_t t4);
};

}  // namespace mocap::node
