import { describe, expect, it } from "vitest";
import { interpolateSkeletonFrames, SkeletonFrameInterpolator } from "../three/frameInterpolator";
import type { SkeletonFrameMessage } from "../types/messages";

const frame = (time: number, x: number, rotation: readonly [number, number, number, number]): SkeletonFrameMessage => ({
  type: "skeleton.frame.v1",
  schema_version: 1,
  frame_time_us: time,
  root_position_m: [x, 0, 0],
  joints: [{
    joint_id: "pelvis",
    parent_joint_id: null,
    position_m: [x, 0, 0],
    world_rotation_wxyz: rotation,
    valid: true,
    data_age_ms: 1,
    virtual: false,
    node_id: 1,
  }],
  segments: [],
  missing_nodes: [],
  stale_nodes: [],
  synchronization_quality: 1,
});

describe("skeleton frame interpolation", () => {
  it("lerps positions and slerps rotations", () => {
    const a = frame(0, 0, [1, 0, 0, 0]);
    const b = frame(10_000, 2, [0, 0, 0, 1]);
    const middle = interpolateSkeletonFrames(a, b, 0.5);
    expect(middle.frame_time_us).toBe(5_000);
    expect(middle.root_position_m[0]).toBeCloseTo(1);
    expect(middle.joints[0].position_m[0]).toBeCloseTo(1);
    expect(Math.abs(middle.joints[0].world_rotation_wxyz[0])).toBeCloseTo(Math.sqrt(0.5), 6);
    expect(Math.abs(middle.joints[0].world_rotation_wxyz[3])).toBeCloseTo(Math.sqrt(0.5), 6);
  });

  it("interpolates within its bounded arrival history", () => {
    const buffer = new SkeletonFrameInterpolator(0);
    buffer.push(frame(10_000, 0, [1, 0, 0, 0]), 100);
    buffer.push(frame(20_000, 2, [1, 0, 0, 0]), 200);
    expect(buffer.sample(150)?.root_position_m[0]).toBeCloseTo(1);
    expect(buffer.sample(250)?.root_position_m[0]).toBeCloseTo(2);
  });

  it("keeps enough 60 Hz history for the default 35 ms render delay", () => {
    const buffer = new SkeletonFrameInterpolator();
    buffer.push(frame(0, 0, [1, 0, 0, 0]), 100);
    buffer.push(frame(16_667, 1, [1, 0, 0, 0]), 117);
    buffer.push(frame(33_333, 2, [1, 0, 0, 0]), 133);
    buffer.push(frame(50_000, 3, [1, 0, 0, 0]), 150);

    // At now=150 ms the delayed render target is 115 ms, between the first
    // two arrivals. A two-frame buffer would incorrectly clamp to x=2.
    const sampled = buffer.sample(150);
    expect(sampled?.root_position_m[0]).toBeCloseTo(15 / 17, 5);
    expect(sampled?.root_position_m[0]).toBeLessThan(1);
  });

  it("resets interpolation when replay seeks backwards", () => {
    const buffer = new SkeletonFrameInterpolator(0);
    buffer.push(frame(20_000, 2, [1, 0, 0, 0]), 200);
    buffer.push(frame(5_000, 5, [1, 0, 0, 0]), 210);
    expect(buffer.sample(220)?.frame_time_us).toBe(5_000);
  });
});
