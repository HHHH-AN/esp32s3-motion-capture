#include "transport/usb_cdc_transport.hpp"

#include <Arduino.h>

namespace mocap::transport {

bool UsbCdcTransport::start() {
  Serial.begin(115200);
  status_.started = true;
  status_.connected = true;
  return true;
}

void UsbCdcTransport::stop() {
  Serial.flush();
  status_.started = false;
  status_.connected = false;
}

bool UsbCdcTransport::send(const std::uint8_t* data, std::size_t size) {
  if (!status_.started || data == nullptr || size == 0) return false;
  const bool ok = Serial.write(data, size) == size;
  if (ok) ++status_.packets_sent;
  else ++status_.send_errors;
  return ok;
}

}  // namespace mocap::transport
