#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "node/node_registry.hpp"
#include "transport/transport.hpp"

namespace mocap::node {

class GatewayBatcher final {
 public:
  GatewayBatcher(transport::Transport& output, NodeRegistry& registry)
      : output_(output), registry_(registry) {}

  bool add(const std::uint8_t source_mac[6], const std::uint8_t* encoded,
           std::size_t encoded_size, std::uint64_t gateway_time_us);
  bool flush(std::uint64_t gateway_time_us);
  std::size_t pendingCount() const { return pending_count_; }

 private:
  struct BatchItem {
    bool present{false};
    std::array<std::uint8_t, 37> bytes{};
  };

  transport::Transport& output_;
  NodeRegistry& registry_;
  std::array<BatchItem, 15> pending_{};
  std::size_t pending_count_{0};
  std::uint32_t batch_sequence_{0};
};

}  // namespace mocap::node
