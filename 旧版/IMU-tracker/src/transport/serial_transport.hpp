#pragma once

#include <HardwareSerial.h>

#include "transport/transport.hpp"

namespace mocap::transport {

class SerialTransport final : public Transport {
 public:
  SerialTransport(HardwareSerial& serial, std::uint32_t baud)
      : serial_(serial), baud_(baud) {}
  bool start() override;
  void stop() override;
  bool send(const std::uint8_t* data, std::size_t size) override;
  TransportStatus status() const override { return status_; }

 private:
  HardwareSerial& serial_;
  std::uint32_t baud_;
  TransportStatus status_{};
};

}  // namespace mocap::transport
