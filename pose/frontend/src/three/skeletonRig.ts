import * as THREE from "three";
import type { SkeletonFrameMessage, SkeletonJoint, SkeletonSegment } from "../types/messages";
import { projectVectorToThree } from "./coordinateTransform";

export class SkeletonRig {
  readonly group = new THREE.Group();
  private readonly jointGeometry = new THREE.SphereGeometry(0.035, 12, 8);
  private readonly jointMaterials = {
    valid: new THREE.MeshStandardMaterial({ color: 0x65f0c2, roughness: 0.45 }),
    invalid: new THREE.MeshStandardMaterial({ color: 0x526273, roughness: 0.7 }),
    virtual: new THREE.MeshStandardMaterial({ color: 0xf5b84b, roughness: 0.55 }),
  };
  private readonly lineMaterials = {
    valid: new THREE.LineBasicMaterial({ color: 0x63a9ff }),
    invalid: new THREE.LineBasicMaterial({ color: 0x384653 }),
    virtual: new THREE.LineDashedMaterial({ color: 0xf5b84b, dashSize: 0.06, gapSize: 0.035 }),
  };
  private readonly jointMeshes = new Map<string, THREE.Mesh>();
  private readonly segmentLines = new Map<string, THREE.Line>();

  constructor() {
    this.group.name = "human-14-skeleton";
  }

  applyFrame(frame: SkeletonFrameMessage): void {
    const jointById = new Map(frame.joints.map((joint) => [joint.joint_id, joint]));
    this.removeAbsent(frame);
    frame.joints.forEach((joint) => this.updateJoint(joint));
    frame.segments.forEach((segment) => this.updateSegment(segment, jointById));
    // Backend joint positions are already absolute project-world positions.
    // root_position_m is frame metadata and must not be added a second time.
    this.group.position.set(0, 0, 0);
  }

  setVisible(visible: boolean): void {
    this.group.visible = visible;
  }

  dispose(): void {
    this.jointGeometry.dispose();
    Object.values(this.jointMaterials).forEach((material) => material.dispose());
    Object.values(this.lineMaterials).forEach((material) => material.dispose());
    this.segmentLines.forEach((line) => line.geometry.dispose());
    this.jointMeshes.clear();
    this.segmentLines.clear();
  }

  private updateJoint(joint: SkeletonJoint): void {
    let mesh = this.jointMeshes.get(joint.joint_id);
    if (!mesh) {
      mesh = new THREE.Mesh(this.jointGeometry, this.jointMaterials.valid);
      mesh.name = `joint:${joint.joint_id}`;
      this.jointMeshes.set(joint.joint_id, mesh);
      this.group.add(mesh);
    }
    mesh.position.copy(projectVectorToThree(joint.position_m));
    mesh.material = joint.virtual
      ? this.jointMaterials.virtual
      : joint.valid
        ? this.jointMaterials.valid
        : this.jointMaterials.invalid;
  }

  private updateSegment(segment: SkeletonSegment, jointById: ReadonlyMap<string, SkeletonJoint>): void {
    const start = jointById.get(segment.start_joint_id);
    const end = jointById.get(segment.end_joint_id);
    let line = this.segmentLines.get(segment.segment_id);
    if (!start || !end) {
      if (line) line.visible = false;
      return;
    }
    if (!line) {
      line = new THREE.Line(new THREE.BufferGeometry(), this.lineMaterials.valid);
      line.name = `segment:${segment.segment_id}`;
      this.segmentLines.set(segment.segment_id, line);
      this.group.add(line);
    }
    line.visible = true;
    line.geometry.dispose();
    line.geometry = new THREE.BufferGeometry().setFromPoints([
      projectVectorToThree(start.position_m),
      projectVectorToThree(end.position_m),
    ]);
    line.material = segment.virtual
      ? this.lineMaterials.virtual
      : start.valid && end.valid
        ? this.lineMaterials.valid
        : this.lineMaterials.invalid;
    if (segment.virtual) line.computeLineDistances();
  }

  private removeAbsent(frame: SkeletonFrameMessage): void {
    const jointIds = new Set(frame.joints.map((joint) => joint.joint_id));
    for (const [id, mesh] of this.jointMeshes) {
      if (!jointIds.has(id)) {
        this.group.remove(mesh);
        this.jointMeshes.delete(id);
      }
    }
    const segmentIds = new Set(frame.segments.map((segment) => segment.segment_id));
    for (const [id, line] of this.segmentLines) {
      if (!segmentIds.has(id)) {
        line.geometry.dispose();
        this.group.remove(line);
        this.segmentLines.delete(id);
      }
    }
  }
}
