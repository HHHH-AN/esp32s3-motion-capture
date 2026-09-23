#pragma once

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace mocap::bsp {

class IrqRouter final {
 public:
  static void attachIcm(TaskHandle_t task);
  static void attachPmic(TaskHandle_t task);
  static void detachAll();

 private:
  static void IRAM_ATTR onIcm();
  static void IRAM_ATTR onPmic();
  static TaskHandle_t icm_task_;
  static TaskHandle_t pmic_task_;
};

}  // namespace mocap::bsp
