#pragma once

#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

#include <cstddef>

#include "config/app_config.hpp"
#include "core/motion_types.hpp"
#include "drivers/icm42688_driver.hpp"

namespace mocap::core {

class ImuAcquisition final {
 public:
  explicit ImuAcquisition(drivers::Icm42688Driver& driver) : driver_(driver) {}
  bool begin();
  bool read(ImuReading& reading);
  std::size_t lastFifoBatchBytes() const { return last_fifo_batch_bytes_; }
  std::size_t lastFifoPacketCount() const { return last_fifo_packet_count_; }

 private:
  static void taskThunk(void* context);
  void taskMain();
  drivers::Icm42688Driver& driver_;
  QueueHandle_t readings_{nullptr};
  TaskHandle_t task_{nullptr};
  volatile std::size_t last_fifo_batch_bytes_{0};
  volatile std::size_t last_fifo_packet_count_{0};
};

}  // namespace mocap::core
