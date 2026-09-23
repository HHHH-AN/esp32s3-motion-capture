import * as THREE from "three";
import type { QuaternionWxyz, SkeletonFrameMessage, SkeletonJoint, Vector3Tuple } from "../types/messages";

const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

const lerpVector = (a: Vector3Tuple, b: Vector3Tuple, alpha: number): Vector3Tuple => [
  THREE.MathUtils.lerp(a[0], b[0], alpha),
  THREE.MathUtils.lerp(a[1], b[1], alpha),
  THREE.MathUtils.lerp(a[2], b[2], alpha),
];

const slerpQuaternion = (a: QuaternionWxyz, b: QuaternionWxyz, alpha: number): QuaternionWxyz => {
  const qa = new THREE.Quaternion(a[1], a[2], a[3], a[0]).normalize();
  const qb = new THREE.Quaternion(b[1], b[2], b[3], b[0]).normalize();
  const result = qa.slerp(qb, alpha).normalize();
  return [result.w, result.x, result.y, result.z];
};

const interpolateJoint = (a: SkeletonJoint, b: SkeletonJoint, alpha: number): SkeletonJoint => ({
  ...b,
  position_m: lerpVector(a.position_m, b.position_m, alpha),
  world_rotation_wxyz: slerpQuaternion(a.world_rotation_wxyz, b.world_rotation_wxyz, alpha),
  valid: a.valid && b.valid,
  data_age_ms: THREE.MathUtils.lerp(a.data_age_ms, b.data_age_ms, alpha),
});

export const interpolateSkeletonFrames = (
  a: SkeletonFrameMessage,
  b: SkeletonFrameMessage,
  alphaValue: number,
): SkeletonFrameMessage => {
  const alpha = clamp01(alphaValue);
  const bById = new Map(b.joints.map((joint) => [joint.joint_id, joint]));
  const seen = new Set<string>();
  const joints = a.joints.map((jointA) => {
    seen.add(jointA.joint_id);
    const jointB = bById.get(jointA.joint_id);
    return jointB ? interpolateJoint(jointA, jointB, alpha) : jointA;
  });
  for (const jointB of b.joints) {
    if (!seen.has(jointB.joint_id)) joints.push(jointB);
  }
  const nearest = alpha < 0.5 ? a : b;
  return {
    ...b,
    frame_time_us: Math.round(THREE.MathUtils.lerp(a.frame_time_us, b.frame_time_us, alpha)),
    root_position_m: lerpVector(a.root_position_m, b.root_position_m, alpha),
    joints,
    segments: nearest.segments,
    missing_nodes: nearest.missing_nodes,
    stale_nodes: nearest.stale_nodes,
    synchronization_quality: THREE.MathUtils.lerp(
      a.synchronization_quality,
      b.synchronization_quality,
      alpha,
    ),
  };
};

interface TimedFrame {
  readonly frame: SkeletonFrameMessage;
  readonly receivedAtMs: number;
}

export class SkeletonFrameInterpolator {
  private frames: TimedFrame[] = [];

  constructor(
    private readonly renderDelayMs = 35,
    private readonly historyWindowMs = Math.max(250, renderDelayMs * 4),
    private readonly maxFrames = 32,
  ) {}

  push(frame: SkeletonFrameMessage, receivedAtMs: number): void {
    const previous = this.frames.at(-1);
    if (previous && frame.frame_time_us <= previous.frame.frame_time_us) this.frames = [];
    this.frames.push({ frame, receivedAtMs });
    const cutoff = receivedAtMs - this.historyWindowMs;
    // A 35 ms render delay spans more than two frames at 60 Hz. Keep at least
    // four frames, then prune by both time and a hard memory bound.
    while (
      this.frames.length > 4
      && (this.frames.length > this.maxFrames || this.frames[1].receivedAtMs < cutoff)
    ) {
      this.frames.shift();
    }
  }

  sample(nowMs: number): SkeletonFrameMessage | null {
    if (this.frames.length === 0) return null;
    if (this.frames.length === 1) return this.frames[0].frame;
    const targetMs = nowMs - this.renderDelayMs;
    const afterIndex = this.frames.findIndex((item) => item.receivedAtMs >= targetMs);
    if (afterIndex === 0) return this.frames[0].frame;
    if (afterIndex < 0) return this.frames.at(-1)?.frame ?? null;
    const a = this.frames[afterIndex - 1];
    const b = this.frames[afterIndex];
    const duration = b.receivedAtMs - a.receivedAtMs;
    if (duration <= 0) return b.frame;
    const alpha = (targetMs - a.receivedAtMs) / duration;
    return interpolateSkeletonFrames(a.frame, b.frame, alpha);
  }

  clear(): void {
    this.frames = [];
  }
}
