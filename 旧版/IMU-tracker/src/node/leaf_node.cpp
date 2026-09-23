#include "node/leaf_node.hpp"

namespace mocap::node {

bool LeafNode::start() {
  status_.started = link_.begin(channel_) && link_.addPeer(gateway_broadcast_.data());
  status_.connected = status_.started;
  return status_.started;
}

void LeafNode::stop() {
  link_.stop();
  status_.started = false;
  status_.connected = false;
}

bool LeafNode::send(const std::uint8_t* data, std::size_t size) {
  const bool ok = status_.started && link_.send(gateway_broadcast_.data(), data, size);
  if (ok) ++status_.packets_sent;
  else ++status_.send_errors;
  return ok;
}

}  // namespace mocap::node
