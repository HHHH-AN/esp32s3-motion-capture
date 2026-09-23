#include "node/node_registry.hpp"

#include <cstring>

namespace mocap::node {

bool NodeRegistry::observe(std::uint8_t node_id, const std::uint8_t mac[6],
                           std::uint32_t sequence, std::uint64_t now_us) {
  if (node_id == 0 || node_id >= nodes_.size() || mac == nullptr) return false;
  auto& node = nodes_[node_id];
  if (node.seen && std::memcmp(node.mac.data(), mac, 6) != 0) return false;
  node.seen = true;
  node.node_id = node_id;
  std::memcpy(node.mac.data(), mac, 6);
  node.last_sequence = sequence;
  node.last_seen_us = now_us;
  ++node.packet_count;
  return true;
}

const NodeRecord* NodeRegistry::find(std::uint8_t node_id) const {
  return node_id < nodes_.size() && nodes_[node_id].seen ? &nodes_[node_id] : nullptr;
}

std::size_t NodeRegistry::onlineCount(std::uint64_t now_us, std::uint64_t timeout_us) const {
  std::size_t count = 0;
  for (const auto& node : nodes_) {
    if (node.seen && now_us >= node.last_seen_us && now_us - node.last_seen_us <= timeout_us)
      ++count;
  }
  return count;
}

}  // namespace mocap::node
