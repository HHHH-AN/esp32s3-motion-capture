#include "node/espnow_link.hpp"

#if MOCAP_ENABLE_ESPNOW
#include <WiFi.h>
#include <esp_arduino_version.h>
#include <esp_wifi.h>

#include <cstring>
#endif

namespace mocap::node {

#if MOCAP_ENABLE_ESPNOW
EspNowLink* EspNowLink::instance_ = nullptr;
#endif

bool EspNowLink::begin(std::uint8_t channel, ReceiveHandler handler, void* context) {
#if MOCAP_ENABLE_ESPNOW
  if (channel < 1 || channel > 13) return false;
  WiFi.mode(WIFI_STA);
  if (esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE) != ESP_OK) return false;
  if (esp_now_init() != ESP_OK) return false;
  handler_ = handler;
  context_ = context;
  instance_ = this;
  if (esp_now_register_recv_cb(onReceive) != ESP_OK) {
    esp_now_deinit();
    instance_ = nullptr;
    return false;
  }
  started_ = true;
  return true;
#else
  (void)channel;
  (void)handler;
  (void)context;
  return false;
#endif
}

void EspNowLink::stop() {
#if MOCAP_ENABLE_ESPNOW
  if (started_) {
    esp_now_unregister_recv_cb();
    esp_now_deinit();
  }
  if (instance_ == this) instance_ = nullptr;
#endif
  started_ = false;
}

bool EspNowLink::addPeer(const std::uint8_t mac[6]) {
#if MOCAP_ENABLE_ESPNOW
  if (!started_ || mac == nullptr) return false;
  if (esp_now_is_peer_exist(mac)) return true;
  esp_now_peer_info_t peer{};
  std::memcpy(peer.peer_addr, mac, 6);
  peer.channel = 0;
  peer.encrypt = false;
  peer.ifidx = WIFI_IF_STA;
  return esp_now_add_peer(&peer) == ESP_OK;
#else
  (void)mac;
  return false;
#endif
}

bool EspNowLink::send(const std::uint8_t mac[6], const std::uint8_t* data, std::size_t size) {
#if MOCAP_ENABLE_ESPNOW
  return started_ && mac != nullptr && data != nullptr && size > 0 && size <= 250 &&
         esp_now_send(mac, data, size) == ESP_OK;
#else
  (void)mac;
  (void)data;
  (void)size;
  return false;
#endif
}

#if MOCAP_ENABLE_ESPNOW
#if ESP_ARDUINO_VERSION_MAJOR >= 3
void EspNowLink::onReceive(const esp_now_recv_info_t* info, const std::uint8_t* data, int size) {
  if (instance_ != nullptr && instance_->handler_ != nullptr && info != nullptr && size > 0)
    instance_->handler_(info->src_addr, data, static_cast<std::size_t>(size), instance_->context_);
}
#else
void EspNowLink::onReceive(const std::uint8_t* mac, const std::uint8_t* data, int size) {
  if (instance_ != nullptr && instance_->handler_ != nullptr && size > 0)
    instance_->handler_(mac, data, static_cast<std::size_t>(size), instance_->context_);
}
#endif
#endif

}  // namespace mocap::node
