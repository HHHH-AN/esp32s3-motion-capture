#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// A bounded FIFO of complete protocol lines. Partial socket sends advance only
// the head frame; later frames can never overwrite its unsent suffix.
template <size_t Capacity, size_t FrameBytes> class FrameTxQueue {
  static_assert(Capacity > 0 && FrameBytes > 0, "Queue dimensions must be positive");
  uint8_t frames_[Capacity][FrameBytes] = {};
  size_t lengths_[Capacity] = {};
  size_t head_ = 0, count_ = 0, offset_ = 0;

public:
  void clear() { head_ = count_ = offset_ = 0; }
  bool enqueue(const uint8_t *data, size_t length) {
    if (!data || !length || length > FrameBytes || count_ == Capacity) return false;
    const size_t tail = (head_ + count_) % Capacity;
    memcpy(frames_[tail], data, length);
    lengths_[tail] = length;
    ++count_;
    return true;
  }
  const uint8_t *data() const { return count_ ? frames_[head_] + offset_ : nullptr; }
  size_t remaining() const { return count_ ? lengths_[head_] - offset_ : 0; }
  bool consume(size_t length) {
    if (!count_ || length > remaining()) return false;
    offset_ += length;
    if (offset_ == lengths_[head_]) {
      head_ = (head_ + 1) % Capacity;
      --count_;
      offset_ = 0;
    }
    return true;
  }
};
