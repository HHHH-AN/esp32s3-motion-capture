#pragma once

namespace mocap::transport::ble {

inline constexpr char kServiceUuid[] = "a0e50001-7c2b-4f18-a902-6f34bca10001";
inline constexpr char kDataUuid[] = "a0e50002-7c2b-4f18-a902-6f34bca10001";
inline constexpr char kStatusUuid[] = "a0e50003-7c2b-4f18-a902-6f34bca10001";
inline constexpr char kControlUuid[] = "a0e50004-7c2b-4f18-a902-6f34bca10001";
inline constexpr char kGatewayName[] = "MOCAP-GW-00";
inline constexpr std::size_t kPreferredMtu = 247;

}  // namespace mocap::transport::ble
