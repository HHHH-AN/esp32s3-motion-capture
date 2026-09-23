#pragma once

#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include <array>
#include <cstddef>
#include <cstdint>

#include "node/espnow_link.hpp"
#include "node/gateway_batcher.hpp"
#include "node/node_registry.hpp"
#include "transport/transport.hpp"

namespace mocap::node {

class Gateway final {
 public:
  Gateway(EspNowLink& link, transport::Transport& output, std::uint8_t channel)
      : link_(link), output_(output), channel_(channel), batcher_(output, registry_) {}
  ~Gateway();

  bool begin();
  void stop();
  void poll(std::uint64_t now_us);
  const NodeRegistry& registry() const { return registry_; }
  std::uint32_t receiveDrops() const { return receive_drops_; }

 private:
  struct RadioPacket {
    std::array<std::uint8_t, 6> source_mac{};
    std::uint16_t size{0};
    std::array<std::uint8_t, 250> bytes{};
  };

  static void receiveThunk(const std::uint8_t* source_mac, const std::uint8_t* data,
                           std::size_t size, void* context);
  void receive(const std::uint8_t* source_mac, const std::uint8_t* data, std::size_t size);

  EspNowLink& link_;
  transport::Transport& output_;
  std::uint8_t channel_;
  NodeRegistry registry_{};
  GatewayBatcher batcher_;
  QueueHandle_t receive_queue_{nullptr};
  std::uint64_t next_flush_us_{0};
  volatile std::uint32_t receive_drops_{0};
};

}  // namespace mocap::node
