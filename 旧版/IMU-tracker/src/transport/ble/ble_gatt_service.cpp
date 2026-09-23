#include "transport/ble/ble_gatt_service.hpp"

#include "transport/ble/gatt_ids.hpp"

namespace mocap::transport::ble {

bool BleGattService::begin(const char* device_name) {
#if MOCAP_ENABLE_BLE
  NimBLEDevice::init(device_name == nullptr ? "mocap-gateway" : device_name);
  NimBLEDevice::setMTU(kPreferredMtu);
  server_ = NimBLEDevice::createServer();
  auto* service = server_->createService(kServiceUuid);
  data_ = service->createCharacteristic(kDataUuid, NIMBLE_PROPERTY::NOTIFY);
  status_ = service->createCharacteristic(kStatusUuid,
                                          NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  control_ = service->createCharacteristic(kControlUuid, NIMBLE_PROPERTY::WRITE);
  service->start();
  auto* advertising = NimBLEDevice::getAdvertising();
  advertising->addServiceUUID(kServiceUuid);
  advertising->setScanResponse(true);
  NimBLEDevice::startAdvertising();
  started_ = true;
  return true;
#else
  (void)device_name;
  return false;
#endif
}

void BleGattService::stop() {
#if MOCAP_ENABLE_BLE
  if (started_) NimBLEDevice::deinit(true);
  server_ = nullptr;
  data_ = nullptr;
  status_ = nullptr;
  control_ = nullptr;
#endif
  started_ = false;
}

bool BleGattService::notifyData(const std::uint8_t* data, std::size_t size) {
#if MOCAP_ENABLE_BLE
  if (!connected() || data == nullptr || size == 0) return false;
  data_->setValue(data, size);
  data_->notify();
  return true;
#else
  (void)data;
  (void)size;
  return false;
#endif
}

bool BleGattService::notifyStatus(const std::uint8_t* data, std::size_t size) {
#if MOCAP_ENABLE_BLE
  if (!started_ || status_ == nullptr || data == nullptr || size == 0) return false;
  status_->setValue(data, size);
  if (connected()) status_->notify();
  return true;
#else
  (void)data;
  (void)size;
  return false;
#endif
}

bool BleGattService::connected() const {
#if MOCAP_ENABLE_BLE
  return started_ && server_ != nullptr && server_->getConnectedCount() > 0;
#else
  return false;
#endif
}

}  // namespace mocap::transport::ble
