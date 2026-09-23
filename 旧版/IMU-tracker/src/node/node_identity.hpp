#pragma once

#include <array>
#include <cstdint>

namespace mocap::node {

struct NodeIdentity {
  std::uint8_t node_id{0};
  std::uint64_t device_uid{0};
  std::array<std::uint8_t, 6> station_mac{};
  bool gateway{false};
};

NodeIdentity readNodeIdentity(std::uint8_t node_id, bool gateway);

}  // namespace mocap::node
