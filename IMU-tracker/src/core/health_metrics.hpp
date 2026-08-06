#pragma once

#include <cstdint>

namespace mocap::core {

struct HealthSnapshot {
  std::uint32_t samples{0};
  std::uint32_t imu_errors{0};
  std::uint32_t mag_errors{0};
  std::uint32_t fifo_overflows{0};
  std::uint32_t queue_overflows{0};
  std::uint32_t transport_errors{0};
  std::uint32_t wireless_drops{0};
  std::uint16_t queue_high_water{0};
};

class HealthMetrics final {
 public:
  void sampleProduced();
  void imuError();
  void magError();
  void fifoOverflow();
  void queueOverflow();
  void transportError();
  void wirelessDrop();
  void observeQueueDepth(std::uint16_t depth);
  HealthSnapshot snapshot() const;

 private:
  volatile HealthSnapshot values_{};
};

}  // namespace mocap::core
