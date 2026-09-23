#pragma once

#include <cstddef>
#include <cstdint>

#ifndef MOCAP_NODE_ID
#define MOCAP_NODE_ID 1
#endif

#ifndef MOCAP_DEVICE_ROLE
#define MOCAP_DEVICE_ROLE 1
#endif

#ifndef MOCAP_SAMPLE_RATE_HZ
#define MOCAP_SAMPLE_RATE_HZ 100
#endif

#ifndef MOCAP_ENABLE_BLE
#define MOCAP_ENABLE_BLE 0
#endif

#ifndef MOCAP_ENABLE_ESPNOW
#define MOCAP_ENABLE_ESPNOW 0
#endif

#ifndef MOCAP_USE_ICM_INTERRUPT
#define MOCAP_USE_ICM_INTERRUPT 0
#endif

namespace mocap::config {

inline constexpr char kFirmwareName[] = "imu-tracker";
inline constexpr char kFirmwareVersion[] = "0.1.0-dev";
inline constexpr std::uint8_t kNodeId = MOCAP_NODE_ID;
inline constexpr std::uint32_t kSampleRateHz = MOCAP_SAMPLE_RATE_HZ;
inline constexpr std::uint32_t kSamplePeriodUs = 1'000'000U / kSampleRateHz;
inline constexpr std::size_t kSampleQueueDepth = 32;
inline constexpr std::uint8_t kEspNowChannel = 1;

enum class DeviceRole : std::uint8_t { Leaf = 1, Gateway = 2 };
inline constexpr DeviceRole kDeviceRole = static_cast<DeviceRole>(MOCAP_DEVICE_ROLE);
inline constexpr bool kIsGateway = kDeviceRole == DeviceRole::Gateway;

static_assert(kNodeId <= 14, "node_id must be in the contracted range 0..14");
static_assert(kIsGateway ? kNodeId == 0 : kNodeId != 0,
              "gateway must use node 0 and leaf nodes must use 1..14");

}  // namespace mocap::config
