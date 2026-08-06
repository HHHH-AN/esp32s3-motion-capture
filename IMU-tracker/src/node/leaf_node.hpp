#pragma once

#include <array>

#include "node/espnow_link.hpp"
#include "transport/transport.hpp"

namespace mocap::node {

class LeafNode final : public transport::Transport {
 public:
  explicit LeafNode(EspNowLink& link, std::uint8_t channel) : link_(link), channel_(channel) {}
  bool start() override;
  void stop() override;
  bool send(const std::uint8_t* data, std::size_t size) override;
  transport::TransportStatus status() const override { return status_; }

 private:
  EspNowLink& link_;
  std::uint8_t channel_;
  const std::array<std::uint8_t, 6> gateway_broadcast_{0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  transport::TransportStatus status_{};
};

}  // namespace mocap::node
