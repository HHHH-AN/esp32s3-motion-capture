import * as THREE from "three";
import { describe, expect, it } from "vitest";
import {
  projectQuaternionToThree,
  projectVectorToThree,
  threeQuaternionToWxyz,
} from "../three/coordinateTransform";

const expectVector = (actual: THREE.Vector3, expected: readonly number[]): void => {
  expect(actual.x).toBeCloseTo(expected[0], 6);
  expect(actual.y).toBeCloseTo(expected[1], 6);
  expect(actual.z).toBeCloseTo(expected[2], 6);
};

describe("project coordinate transform", () => {
  it("maps (+X forward,+Y left,+Z up) to (-Y,Z,-X)", () => {
    expectVector(projectVectorToThree([2, 3, 5]), [-3, 5, -2]);
  });

  it("changes quaternion basis consistently with vector conversion", () => {
    const half = Math.sqrt(0.5);
    const projectQuarterTurnAroundX = [half, half, 0, 0] as const;
    const threeRotation = projectQuaternionToThree(projectQuarterTurnAroundX);
    const rotatedThreeVector = projectVectorToThree([0, 1, 0]).applyQuaternion(threeRotation);
    expectVector(rotatedThreeVector, projectVectorToThree([0, 0, 1]).toArray());
  });

  it("round-trips a normalized quaternion", () => {
    const original = [0.9238795, 0, 0.3826834, 0] as const;
    const roundTrip = threeQuaternionToWxyz(projectQuaternionToThree(original));
    roundTrip.forEach((component, index) => expect(component).toBeCloseTo(original[index], 6));
  });
});
