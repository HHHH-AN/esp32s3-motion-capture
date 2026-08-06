#include "transport/ble/ble_transport.hpp"

#include <array>

#include "transport/ble/ble_fragmenter.hpp"
#include "transport/ble/gatt_ids.hpp"

namespace mocap::transport::ble {

bool BleTransport::start() {
  status_.started = gatt_.begin(name_);
  return status_.started;
}

void BleTransport::stop() {
  gatt_.stop();
  status_.started = false;
  status_.connected = false;
}

bool BleTransport::send(const std::uint8_t* data, std::size_t size) {
  constexpr std::size_t kAttOverhead = 3;
  constexpr std::size_t kPayload = kPreferredMtu - kAttOverhead;
  std::array<std::uint8_t, kPayload> fragment{};
  const std::size_t count = BleFragmenter::fragmentCount(size, kPayload);
  if (!status_.started || count == 0 || count > 255) return false;
  for (std::size_t index = 0; index < count; ++index) {
    const std::size_t fragment_size = BleFragmenter::makeFragment(
        data, size, packet_sequence_, index, kPayload, fragment.data(), fragment.size());
    if (fragment_size == 0 || !gatt_.notifyData(fragment.data(), fragment_size)) {
      ++status_.send_errors;
      return false;
    }
  }
  ++packet_sequence_;
  ++status_.packets_sent;
  return true;
}

TransportStatus BleTransport::status() const {
  status_.connected = gatt_.connected();
  return status_;
}

}  // namespace mocap::transport::ble
