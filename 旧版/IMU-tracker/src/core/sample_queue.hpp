#pragma once

#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include <cstddef>

#include "core/motion_types.hpp"

namespace mocap::core {

class SampleQueue final {
 public:
  ~SampleQueue();
  bool begin(std::size_t depth);
  bool pushDropOldest(const MotionSample& sample);
  bool pop(MotionSample& sample, TickType_t wait = 0);
  std::size_t size() const;

 private:
  QueueHandle_t handle_{nullptr};
};

}  // namespace mocap::core
