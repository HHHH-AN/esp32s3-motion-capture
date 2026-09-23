#include "bsp/irq_router.hpp"

#include <Arduino.h>

#include "bsp/board_pins.hpp"

namespace mocap::bsp {

TaskHandle_t IrqRouter::icm_task_ = nullptr;
TaskHandle_t IrqRouter::pmic_task_ = nullptr;

void IrqRouter::attachIcm(TaskHandle_t task) {
  icm_task_ = task;
  attachInterrupt(digitalPinToInterrupt(pins::kIcmInt1), onIcm, RISING);
}

void IrqRouter::attachPmic(TaskHandle_t task) {
  pmic_task_ = task;
  attachInterrupt(digitalPinToInterrupt(pins::kPmicIrq), onPmic, FALLING);
}

void IrqRouter::detachAll() {
  detachInterrupt(digitalPinToInterrupt(pins::kIcmInt1));
  detachInterrupt(digitalPinToInterrupt(pins::kPmicIrq));
  icm_task_ = nullptr;
  pmic_task_ = nullptr;
}

void IRAM_ATTR IrqRouter::onIcm() {
  if (icm_task_ == nullptr) return;
  BaseType_t wake = pdFALSE;
  vTaskNotifyGiveFromISR(icm_task_, &wake);
  if (wake == pdTRUE) portYIELD_FROM_ISR();
}

void IRAM_ATTR IrqRouter::onPmic() {
  if (pmic_task_ == nullptr) return;
  BaseType_t wake = pdFALSE;
  vTaskNotifyGiveFromISR(pmic_task_, &wake);
  if (wake == pdTRUE) portYIELD_FROM_ISR();
}

}  // namespace mocap::bsp
