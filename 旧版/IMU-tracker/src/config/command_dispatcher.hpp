#pragma once

#include <cstddef>
#include <cstdint>

#include "config/device_config.hpp"

namespace mocap::config {

enum class ControlCommand : std::uint8_t {
  GetConfig = 1,
  SetStreaming = 2,
  SetNodeId = 3,
  Reboot = 4,
};

struct CommandResult {
  bool accepted{false};
  std::uint8_t error_code{0};
};

class CommandDispatcher final {
 public:
  explicit CommandDispatcher(DeviceConfig& config) : config_(config) {}
  CommandResult dispatch(ControlCommand command, const std::uint8_t* payload,
                         std::size_t size);

 private:
  DeviceConfig& config_;
};

}  // namespace mocap::config
