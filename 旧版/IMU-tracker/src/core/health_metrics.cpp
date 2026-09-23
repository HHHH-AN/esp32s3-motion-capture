#include "core/health_metrics.hpp"

#include <Arduino.h>

namespace mocap::core {
namespace {
portMUX_TYPE metrics_mux = portMUX_INITIALIZER_UNLOCKED;
}

#define MOCAP_INCREMENT(field)             \
  do {                                     \
    portENTER_CRITICAL(&metrics_mux);       \
    ++values_.field;                        \
    portEXIT_CRITICAL(&metrics_mux);        \
  } while (false)

void HealthMetrics::sampleProduced() { MOCAP_INCREMENT(samples); }
void HealthMetrics::imuError() { MOCAP_INCREMENT(imu_errors); }
void HealthMetrics::magError() { MOCAP_INCREMENT(mag_errors); }
void HealthMetrics::fifoOverflow() { MOCAP_INCREMENT(fifo_overflows); }
void HealthMetrics::queueOverflow() { MOCAP_INCREMENT(queue_overflows); }
void HealthMetrics::transportError() { MOCAP_INCREMENT(transport_errors); }
void HealthMetrics::wirelessDrop() { MOCAP_INCREMENT(wireless_drops); }

void HealthMetrics::observeQueueDepth(std::uint16_t depth) {
  portENTER_CRITICAL(&metrics_mux);
  if (depth > values_.queue_high_water) values_.queue_high_water = depth;
  portEXIT_CRITICAL(&metrics_mux);
}

HealthSnapshot HealthMetrics::snapshot() const {
  HealthSnapshot result;
  portENTER_CRITICAL(&metrics_mux);
  result.samples = values_.samples;
  result.imu_errors = values_.imu_errors;
  result.mag_errors = values_.mag_errors;
  result.fifo_overflows = values_.fifo_overflows;
  result.queue_overflows = values_.queue_overflows;
  result.transport_errors = values_.transport_errors;
  result.wireless_drops = values_.wireless_drops;
  result.queue_high_water = values_.queue_high_water;
  portEXIT_CRITICAL(&metrics_mux);
  return result;
}

#undef MOCAP_INCREMENT

}  // namespace mocap::core
