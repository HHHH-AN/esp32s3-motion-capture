#pragma once

// No installation role is inferred from the device's MAC or network role.
// tools/build_node.ps1 generates node_config.h from host/config/body_v1.json.
// Both headers are compiler includes, so changing the role rebuilds main.cpp.
#ifndef IMU_BODY_SLOT
#define IMU_BODY_SLOT "unassigned"
#endif
#ifndef IMU_NODE_CONFIG_VERSION
#define IMU_NODE_CONFIG_VERSION "body-v1-unassigned"
#endif
