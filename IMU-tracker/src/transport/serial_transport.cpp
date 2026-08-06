#include "transport/serial_transport.hpp"

namespace mocap::transport {

bool SerialTransport::start() {
  serial_.begin(baud_);
  status_.started = true;
  status_.connected = true;
  return true;
}

void SerialTransport::stop() {
  serial_.flush();
  serial_.end();
  status_.started = false;
  status_.connected = false;
}

bool SerialTransport::send(const std::uint8_t* data, std::size_t size) {
  if (!status_.started || data == nullptr || size == 0) return false;
  const bool ok = serial_.write(data, size) == size;
  if (ok) ++status_.packets_sent;
  else ++status_.send_errors;
  return ok;
}

}  // namespace mocap::transport
