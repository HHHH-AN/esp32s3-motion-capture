#pragma once

#include "transport/ble/ble_gatt_service.hpp"
#include "transport/transport.hpp"

namespace mocap::transport::ble {

class BleTransport final : public Transport {
 public:
  explicit BleTransport(const char* name) : name_(name) {}
  bool start() override;
  void stop() override;
  bool send(const std::uint8_t* data, std::size_t size) override;
  TransportStatus status() const override;

 private:
  const char* name_;
  BleGattService gatt_{};
  mutable TransportStatus status_{};
  std::uint16_t packet_sequence_{0};
};

}  // namespace mocap::transport::ble
