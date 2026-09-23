#pragma once

#include <cstdint>

namespace mocap::app {

class Application final {
 public:
  bool begin();
  void poll();

 private:
  std::uint64_t next_sample_us_{0};
  std::uint64_t next_status_us_{0};
  bool ready_{false};
};

Application& application();

}  // namespace mocap::app
