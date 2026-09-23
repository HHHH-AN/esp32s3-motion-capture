#pragma once

#include <array>

namespace mocap::core {

using Vector3f = std::array<float, 3>;
using AxisMatrix = std::array<std::array<float, 3>, 3>;

Vector3f transformIcmToBoard(const Vector3f& sensor);
Vector3f transformLisToBoard(const Vector3f& sensor);

}  // namespace mocap::core
