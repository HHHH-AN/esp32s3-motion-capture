import * as THREE from "three";
import type { QuaternionWxyz, Vector3Tuple } from "../types/messages";

// Project (+X forward, +Y left, +Z up) -> Three.js (+X right, +Y up, +Z back).
// p_three = (-p_project.y, p_project.z, -p_project.x)
const PROJECT_TO_THREE = new THREE.Matrix4().set(
  0, -1, 0, 0,
  0, 0, 1, 0,
  -1, 0, 0, 0,
  0, 0, 0, 1,
);
const BASIS_ROTATION = new THREE.Quaternion().setFromRotationMatrix(PROJECT_TO_THREE).normalize();
const INVERSE_BASIS_ROTATION = BASIS_ROTATION.clone().invert();

export const projectVectorToThree = ([x, y, z]: Vector3Tuple): THREE.Vector3 =>
  new THREE.Vector3(-y, z, -x);

export const projectQuaternionToThree = ([w, x, y, z]: QuaternionWxyz): THREE.Quaternion => {
  const projectRotation = new THREE.Quaternion(x, y, z, w).normalize();
  return BASIS_ROTATION.clone()
    .multiply(projectRotation)
    .multiply(INVERSE_BASIS_ROTATION)
    .normalize();
};

export const threeQuaternionToWxyz = (quaternion: THREE.Quaternion): QuaternionWxyz => {
  const projectRotation = INVERSE_BASIS_ROTATION.clone()
    .multiply(quaternion)
    .multiply(BASIS_ROTATION)
    .normalize();
  return [projectRotation.w, projectRotation.x, projectRotation.y, projectRotation.z];
};
