#pragma once

#include <cstddef>
#include <cstdint>

#if MOCAP_ENABLE_BLE
#include <NimBLEDevice.h>
#endif

namespace mocap::transport::ble {

class BleGattService final {
 public:
  bool begin(const char* device_name);
  void stop();
  bool notifyData(const std::uint8_t* data, std::size_t size);
  bool notifyStatus(const std::uint8_t* data, std::size_t size);
  bool connected() const;

 private:
#if MOCAP_ENABLE_BLE
  NimBLEServer* server_{nullptr};
  NimBLECharacteristic* data_{nullptr};
  NimBLECharacteristic* status_{nullptr};
  NimBLECharacteristic* control_{nullptr};
#endif
  bool started_{false};
};

}  // namespace mocap::transport::ble
