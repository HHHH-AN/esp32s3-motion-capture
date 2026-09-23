#pragma once

#include "core/health_metrics.hpp"
#include "core/imu_acquisition.hpp"
#include "core/mag_sampler.hpp"
#include "core/sample_queue.hpp"

namespace mocap::core {

class MotionSampler final {
 public:
  MotionSampler(ImuAcquisition& imu, MagSampler& mag, SampleQueue& queue,
                HealthMetrics& health)
      : imu_(imu), mag_(mag), queue_(queue), health_(health) {}

  bool begin();
  bool sampleOnce();

 private:
  ImuAcquisition& imu_;
  MagSampler& mag_;
  SampleQueue& queue_;
  HealthMetrics& health_;
  bool imu_ready_{false};
  bool mag_ready_{false};
};

}  // namespace mocap::core
