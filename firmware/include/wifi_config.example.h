#pragma once

// Empty SSID selects hotspot mode; set router credentials for station mode.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
#define WIFI_TCP_PORT 9000

#define WIFI_AP_SSID "ESP32-IMU"
#define WIFI_AP_PASSWORD "SET_A_NEW_WIFI_PASSWORD"

#define IMU_NODE_ID "right_wrist"
// 1: derive a unique protocol ID from the chip MAC; 0: use IMU_NODE_ID above.
#define IMU_USE_MAC_NODE_ID 1
#define IMU_SAMPLE_RATE_HZ 100
