#include "core/sensor_frame.hpp"

namespace mocap::core {
namespace {

// TODO(HW-M0): replace identity matrices only after PCB footprint rotation and
// a physical +X/+Y/+Z test have been reviewed. These values are not measurements.
constexpr AxisMatrix kIcmToBoard{{{{1, 0, 0}}, {{0, 1, 0}}, {{0, 0, 1}}}};
constexpr AxisMatrix kLisToBoard{{{{1, 0, 0}}, {{0, 1, 0}}, {{0, 0, 1}}}};

Vector3f apply(const AxisMatrix& matrix, const Vector3f& vector) {
  Vector3f result{};
  for (std::size_t row = 0; row < 3; ++row) {
    for (std::size_t column = 0; column < 3; ++column) {
      result[row] += matrix[row][column] * vector[column];
    }
  }
  return result;
}
}

Vector3f transformIcmToBoard(const Vector3f& sensor) { return apply(kIcmToBoard, sensor); }
Vector3f transformLisToBoard(const Vector3f& sensor) { return apply(kLisToBoard, sensor); }

}  // namespace mocap::core
