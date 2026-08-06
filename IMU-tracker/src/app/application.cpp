#include "app/application.hpp"

#include <Arduino.h>
#include <esp_system.h>

#include "bsp/board_pins.hpp"
#include "bsp/bus_manager.hpp"
#include "bsp/monotonic_clock.hpp"
#include "config/app_config.hpp"
#include "config/device_config.hpp"
#include "core/deadline_scheduler.hpp"
#include "core/health_metrics.hpp"
#include "core/imu_acquisition.hpp"
#include "core/mag_sampler.hpp"
#include "core/motion_sampler.hpp"
#include "core/power_service.hpp"
#include "core/sample_queue.hpp"
#include "drivers/axp2101_driver.hpp"
#include "drivers/icm42688_driver.hpp"
#include "drivers/lis2mdl_driver.hpp"
#include "node/espnow_link.hpp"
#include "node/gateway.hpp"
#include "node/leaf_node.hpp"
#include "transport/ble/ble_transport.hpp"
#include "transport/ble/gatt_ids.hpp"
#include "transport/stream_task.hpp"
#include "transport/usb_cdc_transport.hpp"

namespace mocap::app {
namespace {

core::HealthMetrics health;
core::SampleQueue samples;
transport::UsbCdcTransport usb;
core::MotionSampler* sampler = nullptr;
transport::StreamTask* stream = nullptr;
core::PowerService* power = nullptr;
node::Gateway* gateway = nullptr;
config::DeviceConfig device_config{};

void printBootInformation() {
  Serial.printf("%s %s node=%u role=%s\n", config::kFirmwareName, config::kFirmwareVersion,
                device_config.node_id,
                device_config.role == config::DeviceRole::Gateway ? "gateway" : "leaf");
  Serial.printf("flash=%u psram=%u reset_reason=%d\n", ESP.getFlashChipSize(), ESP.getPsramSize(),
                static_cast<int>(esp_reset_reason()));
  Serial.printf("USB contract: D-=GPIO%d D+=GPIO%d\n", bsp::pins::kUsbDm, bsp::pins::kUsbDp);
}

}  // namespace

Application& application() {
  static Application instance;
  return instance;
}

bool Application::begin() {
  if (!usb.start()) return false;
  delay(250);

  config::DeviceConfigStore config_store;
  if (!config_store.load(device_config)) device_config = {};
  device_config.role = config::kDeviceRole;
  if (device_config.role == config::DeviceRole::Gateway) device_config.node_id = 0;
  else if (device_config.node_id == 0) device_config.node_id = config::kNodeId;
  printBootInformation();

  auto& buses = bsp::BusManager::instance();
  if (!buses.begin()) {
    Serial.println("ERROR: failed to initialize the critical sensor SPI bus");
    return false;
  }
  const auto bus_status = buses.status();
  if (!bus_status.pmic_i2c) Serial.println("WARN: PMIC I2C controller failed to start");
  if (!bus_status.magnetometer_i2c)
    Serial.println("WARN: magnetometer I2C controller failed; six-axis sampling remains available");

  static drivers::Axp2101Driver axp(buses.pmicWire());
  static core::PowerService power_service(axp);
  power = &power_service;
  if (power->begin()) {
    const auto status = power->status();
    Serial.printf("AXP2101 reachable chip_id=0x%02X status=%02X/%02X (read-only)\n",
                  status.chip_id, status.status0, status.status1);
  } else {
    Serial.println("WARN: AXP2101 status unavailable; no PMIC register was written");
  }

  if (!samples.begin(config::kSampleQueueDepth)) {
    Serial.println("ERROR: failed to create sample queue");
    return false;
  }

  if (device_config.role == config::DeviceRole::Gateway) {
#if MOCAP_ENABLE_ESPNOW
    static node::EspNowLink radio;
#if MOCAP_ENABLE_BLE
    static transport::ble::BleTransport ble(transport::ble::kGatewayName);
    static node::Gateway gateway_service(radio, ble, device_config.espnow_channel);
#else
    static node::Gateway gateway_service(radio, usb, device_config.espnow_channel);
#endif
    gateway = &gateway_service;
    if (!gateway->begin()) {
      Serial.println("ERROR: gateway ESP-NOW/output transport initialization failed");
      return false;
    }
    Serial.println("gateway ready: ESP-NOW ingress and 10 ms RAW_BATCH aggregation enabled");
#else
    Serial.println("ERROR: gateway build requires MOCAP_ENABLE_ESPNOW=1");
    return false;
#endif
    ready_ = true;
    next_status_us_ = bsp::MonotonicClock::nowUs() + 1'000'000U;
    return true;
  }

  static drivers::Icm42688Driver icm(buses.sensorSpi(), bsp::pins::kIcmCs);
  static drivers::Lis2mdlDriver lis(buses.magWire());
  static core::ImuAcquisition imu(icm);
  static core::MagSampler mag(lis);
  static core::MotionSampler motion_sampler(imu, mag, samples, health);
#if MOCAP_ENABLE_ESPNOW
  static node::EspNowLink radio;
  static node::LeafNode leaf(radio, device_config.espnow_channel);
  if (!leaf.start()) {
    Serial.println("ERROR: leaf ESP-NOW initialization failed");
    return false;
  }
  static transport::StreamTask stream_task(samples, leaf, health, device_config.node_id);
#elif MOCAP_ENABLE_BLE
  static char ble_name[20]{};
  snprintf(ble_name, sizeof(ble_name), "MOCAP-NODE-%02u", device_config.node_id);
  static transport::ble::BleTransport ble(ble_name);
  if (!ble.start()) {
    Serial.println("ERROR: leaf BLE initialization failed");
    return false;
  }
  static transport::StreamTask stream_task(samples, ble, health, device_config.node_id);
#else
  static transport::StreamTask stream_task(samples, usb, health, device_config.node_id);
#endif
  sampler = &motion_sampler;
  stream = &stream_task;

  if (!sampler->begin()) {
    Serial.println("ERROR: ICM-42688-P polling bring-up failed; stream remains disabled");
    return false;
  }
  Serial.println("ICM ready; LIS failures are non-fatal. Polling mode active at 100 Hz.");
  Serial.println("Binary COBS stream starts after this line; do not parse boot text as packets.");
  ready_ = true;
  next_sample_us_ = bsp::MonotonicClock::nowUs();
  next_status_us_ = next_sample_us_ + 1'000'000U;
  return true;
}

void Application::poll() {
  if (!ready_) {
    delay(100);
    return;
  }
  const std::uint64_t now = bsp::MonotonicClock::nowUs();
  if (sampler != nullptr && core::advancePeriodicDeadline(
                                now, config::kSamplePeriodUs, 5, next_sample_us_)) {
    sampler->sampleOnce();
  }
  if (stream != nullptr) {
    while (stream->poll()) {}
  }
  if (gateway != nullptr) gateway->poll(now);
  if (power != nullptr && now >= next_status_us_) {
    next_status_us_ += 1'000'000U;
    (void)power->refresh();
  }
  delay(1);
}

}  // namespace mocap::app
