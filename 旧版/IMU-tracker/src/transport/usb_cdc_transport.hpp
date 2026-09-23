#pragma once

#include "transport/transport.hpp"

namespace mocap::transport {

class UsbCdcTransport final : public Transport {
 public:
  bool start() override;
  void stop() override;
  bool send(const std::uint8_t* data, std::size_t size) override;
  TransportStatus status() const override { return status_; }

 private:
  TransportStatus status_{};
};

}  // namespace mocap::transport
