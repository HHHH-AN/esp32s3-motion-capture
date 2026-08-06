#pragma once

#include <cstddef>
#include <cstdint>

#include "config/app_config.hpp"

#if MOCAP_ENABLE_ESPNOW
#include <esp_arduino_version.h>
#include <esp_now.h>
#endif

namespace mocap::node {

class EspNowLink final {
 public:
  using ReceiveHandler = void (*)(const std::uint8_t* source_mac, const std::uint8_t* data,
                                  std::size_t size, void* context);

  bool begin(std::uint8_t channel, ReceiveHandler handler = nullptr, void* context = nullptr);
  void stop();
  bool addPeer(const std::uint8_t mac[6]);
  bool send(const std::uint8_t mac[6], const std::uint8_t* data, std::size_t size);
  bool started() const { return started_; }

 private:
#if MOCAP_ENABLE_ESPNOW
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  static void onReceive(const esp_now_recv_info_t* info, const std::uint8_t* data, int size);
#else
  static void onReceive(const std::uint8_t* mac, const std::uint8_t* data, int size);
#endif
  static EspNowLink* instance_;
#endif
  ReceiveHandler handler_{nullptr};
  void* context_{nullptr};
  bool started_{false};
};

}  // namespace mocap::node
