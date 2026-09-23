#pragma once

#include <cstdint>

namespace mocap::bsp {

class MonotonicClock final {
 public:
  static std::uint64_t nowUs();
};

}  // namespace mocap::bsp
