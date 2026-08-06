#include "core/imu_acquisition.hpp"

#include <array>

#include "bsp/irq_router.hpp"

namespace mocap::core {

bool ImuAcquisition::begin() {
  if (!driver_.begin()) return false;
#if MOCAP_USE_ICM_INTERRUPT
  readings_ = xQueueCreate(32, sizeof(ImuReading));
  if (readings_ == nullptr || !driver_.enableFifoInterrupt()) return false;
  if (xTaskCreatePinnedToCore(taskThunk, "icm-fifo", 4096, this, 5, &task_, 1) != pdPASS)
    return false;
  bsp::IrqRouter::attachIcm(task_);
#endif
  return true;
}

bool ImuAcquisition::read(ImuReading& reading) {
#if MOCAP_USE_ICM_INTERRUPT
  return readings_ != nullptr &&
         xQueueReceive(readings_, &reading, pdMS_TO_TICKS(20)) == pdTRUE;
#else
  return driver_.readPolling(reading);
#endif
}

void ImuAcquisition::taskThunk(void* context) {
  static_cast<ImuAcquisition*>(context)->taskMain();
}

void ImuAcquisition::taskMain() {
#if MOCAP_USE_ICM_INTERRUPT
  std::array<std::uint8_t, 2048> fifo{};
  for (;;) {
    (void)ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    std::size_t bytes = 0;
    if (driver_.readFifo(fifo.data(), fifo.size(), bytes) && bytes > 0) {
      constexpr std::size_t kPacketSize = 16;
      std::size_t packet_count = 0;
      for (std::size_t offset = 0; offset + kPacketSize <= bytes; offset += kPacketSize) {
        ImuReading reading{};
        if (!driver_.parseLatestStandardFifoPacket(fifo.data() + offset, kPacketSize, reading))
          continue;
        if (xQueueSend(readings_, &reading, 0) != pdTRUE) {
          ImuReading discarded{};
          (void)xQueueReceive(readings_, &discarded, 0);
          (void)xQueueSend(readings_, &reading, 0);
        }
        ++packet_count;
      }
      last_fifo_batch_bytes_ = bytes;
      last_fifo_packet_count_ = packet_count;
    }
  }
#else
  vTaskDelete(nullptr);
#endif
}

}  // namespace mocap::core
