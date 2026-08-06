#pragma once

#include <cstddef>
#include <cstdint>

namespace mocap::lifecycle {

class OtaService final {
 public:
  bool begin(std::size_t image_size);
  bool write(const std::uint8_t* data, std::size_t size);
  bool finish();
  void abort();
  bool active() const { return active_; }

 private:
  bool active_{false};
};

}  // namespace mocap::lifecycle
