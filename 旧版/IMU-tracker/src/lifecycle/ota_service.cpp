#include "lifecycle/ota_service.hpp"

#include <Update.h>

namespace mocap::lifecycle {

bool OtaService::begin(std::size_t image_size) {
  if (active_ || image_size == 0) return false;
  active_ = Update.begin(image_size, U_FLASH);
  return active_;
}

bool OtaService::write(const std::uint8_t* data, std::size_t size) {
  // Arduino-ESP32 2.x exposes a non-const pointer although Update does not
  // mutate the supplied image buffer.
  return active_ && data != nullptr && size > 0 &&
         Update.write(const_cast<std::uint8_t*>(data), size) == size;
}

bool OtaService::finish() {
  if (!active_) return false;
  const bool ok = Update.end(true);
  active_ = false;
  return ok;
}

void OtaService::abort() {
  if (active_) Update.abort();
  active_ = false;
}

}  // namespace mocap::lifecycle
