#pragma once

#include <cstdint>

#include "core/health_metrics.hpp"
#include "core/sample_queue.hpp"
#include "transport/transport.hpp"

namespace mocap::transport {

class StreamTask final {
 public:
  StreamTask(core::SampleQueue& queue, Transport& transport, core::HealthMetrics& health,
             std::uint8_t node_id)
      : queue_(queue), transport_(transport), health_(health), node_id_(node_id) {}

  bool poll();

 private:
  core::SampleQueue& queue_;
  Transport& transport_;
  core::HealthMetrics& health_;
  std::uint8_t node_id_;
  std::uint32_t sequence_{0};
};

}  // namespace mocap::transport
