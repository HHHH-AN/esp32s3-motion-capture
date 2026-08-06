#include "node/gateway.hpp"

#include <cstring>

#include "core/deadline_scheduler.hpp"

namespace mocap::node {

Gateway::~Gateway() {
  stop();
  if (receive_queue_ != nullptr) vQueueDelete(receive_queue_);
}

bool Gateway::begin() {
  if (receive_queue_ == nullptr) receive_queue_ = xQueueCreate(32, sizeof(RadioPacket));
  if (receive_queue_ == nullptr || !output_.start()) return false;
  if (!link_.begin(channel_, receiveThunk, this)) {
    output_.stop();
    return false;
  }
  next_flush_us_ = 0;
  return true;
}

void Gateway::stop() {
  link_.stop();
  output_.stop();
}

void Gateway::poll(std::uint64_t now_us) {
  RadioPacket packet{};
  while (receive_queue_ != nullptr && xQueueReceive(receive_queue_, &packet, 0) == pdTRUE) {
    if (!batcher_.add(packet.source_mac.data(), packet.bytes.data(), packet.size, now_us))
      ++receive_drops_;
  }
  if (next_flush_us_ == 0) next_flush_us_ = now_us + 10'000U;
  if (core::advancePeriodicDeadline(now_us, 10'000U, 5, next_flush_us_)) {
    if (!batcher_.flush(now_us)) ++receive_drops_;
  }
}

void Gateway::receiveThunk(const std::uint8_t* source_mac, const std::uint8_t* data,
                           std::size_t size, void* context) {
  if (context != nullptr) static_cast<Gateway*>(context)->receive(source_mac, data, size);
}

void Gateway::receive(const std::uint8_t* source_mac, const std::uint8_t* data,
                      std::size_t size) {
  if (receive_queue_ == nullptr || source_mac == nullptr || data == nullptr || size == 0 ||
      size > RadioPacket{}.bytes.size()) {
    ++receive_drops_;
    return;
  }
  RadioPacket packet{};
  std::memcpy(packet.source_mac.data(), source_mac, packet.source_mac.size());
  packet.size = static_cast<std::uint16_t>(size);
  std::memcpy(packet.bytes.data(), data, size);
  if (xQueueSend(receive_queue_, &packet, 0) != pdTRUE) ++receive_drops_;
}

}  // namespace mocap::node
