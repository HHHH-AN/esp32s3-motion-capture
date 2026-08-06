import * as THREE from "three";
import type { NodePoseMessage } from "../types/messages";
import { projectQuaternionToThree } from "./coordinateTransform";

export class ImuCube {
  readonly group = new THREE.Group();
  private readonly geometry = new THREE.BoxGeometry(0.42, 0.12, 0.28);
  private readonly material = new THREE.MeshStandardMaterial({
    color: 0x36d1dc,
    roughness: 0.32,
    metalness: 0.18,
  });
  private readonly mesh = new THREE.Mesh(this.geometry, this.material);

  constructor() {
    this.mesh.castShadow = true;
    this.mesh.receiveShadow = true;
    this.group.add(this.mesh);
    this.group.add(new THREE.AxesHelper(0.45));
    this.group.position.set(0, 1.15, 0);
    this.group.name = "single-node-pose";
  }

  applyPose(pose: NodePoseMessage): void {
    this.group.quaternion.copy(projectQuaternionToThree(pose.quaternion_wxyz));
    this.material.color.setHSL(0.52, 0.72, 0.35 + pose.quality * 0.2);
  }

  setVisible(visible: boolean): void {
    this.group.visible = visible;
  }

  dispose(): void {
    this.geometry.dispose();
    this.material.dispose();
  }
}
