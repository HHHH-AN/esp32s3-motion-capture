#pragma once

#include <array>
#include <cstdint>

namespace mocap::lifecycle {

enum class Fault : std::uint8_t {
  Pmic = 0,
  Imu,
  Magnetometer,
  SampleQueue,
  Transport,
  Wireless,
  Ota,
  Count,
};

struct FaultState {
  bool active{false};
  std::uint32_t occurrences{0};
  std::uint64_t first_seen_us{0};
  std::uint64_t last_seen_us{0};
};

class FaultManager final {
 public:
  void raise(Fault fault, std::uint64_t now_us);
  void clear(Fault fault);
  FaultState state(Fault fault) const;
  bool degraded() const;

 private:
  std::array<FaultState, static_cast<std::size_t>(Fault::Count)> faults_{};
};

}  // namespace mocap::lifecycle
