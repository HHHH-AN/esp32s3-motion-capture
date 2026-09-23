#include "config/command_dispatcher.hpp"

#include <Arduino.h>

namespace mocap::config {

CommandResult CommandDispatcher::dispatch(ControlCommand command, const std::uint8_t* payload,
                                           std::size_t size) {
  switch (command) {
    case ControlCommand::GetConfig:
      return {true, 0};
    case ControlCommand::SetStreaming:
      if (payload == nullptr || size != 1 || payload[0] > 1) return {false, 1};
      config_.streaming_enabled = payload[0] != 0;
      return {true, 0};
    case ControlCommand::SetNodeId:
      if (payload == nullptr || size != 1 || payload[0] == 0 || payload[0] > 14 ||
          config_.role == DeviceRole::Gateway) return {false, 1};
      config_.node_id = payload[0];
      return {true, 0};
    case ControlCommand::Reboot:
      // The caller must send CONTROL_ACK before acting on this accepted command.
      return {true, 0};
    default:
      return {false, 2};
  }
}

}  // namespace mocap::config
