#include "node/node_identity.hpp"

#include <Arduino.h>
#include <esp_mac.h>

namespace mocap::node {

NodeIdentity readNodeIdentity(std::uint8_t node_id, bool gateway) {
  NodeIdentity identity{};
  identity.node_id = node_id;
  identity.gateway = gateway;
  identity.device_uid = ESP.getEfuseMac();
  (void)esp_read_mac(identity.station_mac.data(), ESP_MAC_WIFI_STA);
  return identity;
}

}  // namespace mocap::node
