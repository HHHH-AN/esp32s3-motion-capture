#pragma once

#include <array>
#include <cstdint>

namespace mocap::node {

struct NodeRecord {
  bool seen{false};
  std::uint8_t node_id{0};
  std::array<std::uint8_t, 6> mac{};
  std::uint32_t last_sequence{0};
  std::uint64_t last_seen_us{0};
  std::uint32_t packet_count{0};
};

class NodeRegistry final {
 public:
  bool observe(std::uint8_t node_id, const std::uint8_t mac[6], std::uint32_t sequence,
               std::uint64_t now_us);
  const NodeRecord* find(std::uint8_t node_id) const;
  std::size_t onlineCount(std::uint64_t now_us, std::uint64_t timeout_us) const;

 private:
  std::array<NodeRecord, 15> nodes_{};
};

}  // namespace mocap::node
