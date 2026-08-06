import { describe, expect, it } from "vitest";
import { getNodeTelemetry } from "../components/nodeTelemetry";
import type { NodePoseMessage, SkeletonFrameMessage } from "../types/messages";

const pose: NodePoseMessage = {
  type: "pose.frame.v1",
  schema_version: 1,
  node_id: 1,
  frame_time_us: 1,
  quaternion_wxyz: [1, 0, 0, 0],
  quality: 0.75,
  data_age_ms: 5,
  status_flags: 0,
};

const skeleton = (missing: readonly number[] = [], stale: readonly number[] = []): SkeletonFrameMessage => ({
  type: "skeleton.frame.v1",
  schema_version: 1,
  frame_time_us: 1,
  root_position_m: [0, 0, 0],
  joints: [{
    joint_id: "head",
    parent_joint_id: "chest",
    position_m: [0, 0, 1],
    world_rotation_wxyz: [1, 0, 0, 0],
    valid: true,
    data_age_ms: 12,
    virtual: false,
    node_id: 2,
  }],
  segments: [],
  missing_nodes: missing,
  stale_nodes: stale,
  synchronization_quality: 1,
});

describe("node telemetry", () => {
  it("shows measured age and quality while marking stale state", () => {
    const telemetry = getNodeTelemetry(1, pose, skeleton([], [1]));
    expect(telemetry.state).toBe("stale");
    expect(telemetry.ageLabel).toBe("5.0 ms");
    expect(telemetry.qualityLabel).toBe("75%");
    expect(telemetry.packetRateLabel).toBe("N/A");
    expect(telemetry.batteryLabel).toBe("N/A");
  });

  it("uses skeleton age when a pose message has not arrived", () => {
    const telemetry = getNodeTelemetry(2, undefined, skeleton());
    expect(telemetry.state).toBe("online");
    expect(telemetry.ageLabel).toBe("12.0 ms");
    expect(telemetry.qualityLabel).toBe("N/A");
  });

  it("does not invent telemetry for a missing node", () => {
    const base = skeleton([3]);
    const frame: SkeletonFrameMessage = {
      ...base,
      joints: [
        ...base.joints,
        {
          joint_id: "left_elbow",
          parent_joint_id: "left_shoulder",
          position_m: [0, 0, 0],
          world_rotation_wxyz: [1, 0, 0, 0],
          valid: false,
          data_age_ms: 0,
          virtual: false,
          node_id: 3,
        },
      ],
    };
    const telemetry = getNodeTelemetry(3, undefined, frame);
    expect(telemetry.state).toBe("missing");
    expect(telemetry.ageLabel).toBe("N/A");
    expect(telemetry.qualityLabel).toBe("N/A");
    expect(telemetry.packetRateLabel).toBe("N/A");
    expect(telemetry.batteryLabel).toBe("N/A");
  });
});
