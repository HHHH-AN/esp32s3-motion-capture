#include "core/sample_queue.hpp"

namespace mocap::core {

SampleQueue::~SampleQueue() {
  if (handle_ != nullptr) vQueueDelete(handle_);
}

bool SampleQueue::begin(std::size_t depth) {
  if (handle_ != nullptr || depth == 0) return false;
  handle_ = xQueueCreate(static_cast<UBaseType_t>(depth), sizeof(MotionSample));
  return handle_ != nullptr;
}

bool SampleQueue::pushDropOldest(const MotionSample& sample) {
  if (handle_ == nullptr) return false;
  if (xQueueSend(handle_, &sample, 0) == pdTRUE) return true;
  MotionSample discarded{};
  (void)xQueueReceive(handle_, &discarded, 0);
  return xQueueSend(handle_, &sample, 0) == pdTRUE;
}

bool SampleQueue::pop(MotionSample& sample, TickType_t wait) {
  return handle_ != nullptr && xQueueReceive(handle_, &sample, wait) == pdTRUE;
}

std::size_t SampleQueue::size() const {
  return handle_ == nullptr ? 0U : static_cast<std::size_t>(uxQueueMessagesWaiting(handle_));
}

}  // namespace mocap::core
