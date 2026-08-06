#include "core/power_service.hpp"

namespace mocap::core {

bool PowerService::begin() { return driver_.begin() && refresh(); }
bool PowerService::refresh() { return driver_.readStatus(status_); }

}  // namespace mocap::core
