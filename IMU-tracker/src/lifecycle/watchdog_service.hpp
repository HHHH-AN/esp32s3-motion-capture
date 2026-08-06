#pragma once

#include <array>
#include <cstdint>

namespace mocap::lifecycle {

class WatchdogService final {
 public:
  static constexpr std::size_t kTaskCount = 4;
  void heartbeat(std::size_t task, std::uint64_t now_us);
  bool healthy(std::uint64_t now_us, std::uint64_t timeout_us) const;

 private:
  std::array<std::uint64_t, kTaskCount> heartbeats_{};
};

}  // namespace mocap::lifecycle
