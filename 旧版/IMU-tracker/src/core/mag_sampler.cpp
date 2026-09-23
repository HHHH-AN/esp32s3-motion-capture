#include "core/mag_sampler.hpp"

namespace mocap::core {

bool MagSampler::sample() {
  MagReading next{};
  if (!driver_.readPolling(next)) return false;
  latest_ = next;
  return true;
}

}  // namespace mocap::core
