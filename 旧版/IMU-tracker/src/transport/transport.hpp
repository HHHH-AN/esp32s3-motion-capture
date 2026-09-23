#pragma once

#include <cstddef>
#include <cstdint>

namespace mocap::transport {

struct TransportStatus {
  bool started{false};
  bool connected{false};
  std::uint32_t packets_sent{0};
  std::uint32_t send_errors{0};
};

class Transport {
 public:
  virtual ~Transport() = default;
  virtual bool start() = 0;
  virtual void stop() = 0;
  virtual bool send(const std::uint8_t* data, std::size_t size) = 0;
  virtual TransportStatus status() const = 0;
};

}  // namespace mocap::transport
