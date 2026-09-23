#include "lifecycle/fault_manager.hpp"

namespace mocap::lifecycle {

void FaultManager::raise(Fault fault, std::uint64_t now_us) {
  auto& state = faults_[static_cast<std::size_t>(fault)];
  if (!state.active) state.first_seen_us = now_us;
  state.active = true;
  state.last_seen_us = now_us;
  ++state.occurrences;
}

void FaultManager::clear(Fault fault) {
  faults_[static_cast<std::size_t>(fault)].active = false;
}

FaultState FaultManager::state(Fault fault) const {
  return faults_[static_cast<std::size_t>(fault)];
}

bool FaultManager::degraded() const {
  for (const auto& fault : faults_) if (fault.active) return true;
  return false;
}

}  // namespace mocap::lifecycle
