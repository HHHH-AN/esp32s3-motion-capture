import { describe, expect, it } from "vitest";
import { validateMocapMessage } from "../types/messages";

describe("validateMocapMessage", () => {
  it("accepts the frozen pose.frame.v1 contract", () => {
    const result = validateMocapMessage({
      type: "pose.frame.v1",
      schema_version: 1,
      node_id: 1,
      frame_time_us: 123_456,
      quaternion_wxyz: [1, 0, 0, 0],
      quality: 0.98,
      data_age_ms: 4.2,
      status_flags: 0,
    });
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.value.type).toBe("pose.frame.v1");
  });

  it("rejects gateway id 0 as a wearable pose", () => {
    const result = validateMocapMessage({
      type: "pose.frame.v1",
      schema_version: 1,
      node_id: 0,
      frame_time_us: 1,
      quaternion_wxyz: [1, 0, 0, 0],
      quality: 1,
      data_age_ms: 0,
      status_flags: 0,
    });
    expect(result.ok).toBe(false);
  });

  it("accepts an explicitly virtual chest segment", () => {
    const result = validateMocapMessage({
      type: "skeleton.frame.v1",
      schema_version: 1,
      frame_time_us: 123_456,
      root_position_m: [0, 0, 0],
      joints: [
        {
          joint_id: "pelvis",
          parent_joint_id: null,
          position_m: [0, 0, 0],
          world_rotation_wxyz: [1, 0, 0, 0],
          valid: true,
          data_age_ms: 2,
          virtual: false,
          node_id: 1,
        },
        {
          joint_id: "chest",
          parent_joint_id: "pelvis",
          position_m: [0, 0, 0.48],
          world_rotation_wxyz: [1, 0, 0, 0],
          valid: true,
          data_age_ms: 2,
          virtual: true,
        },
      ],
      segments: [
        {
          segment_id: "chest",
          start_joint_id: "pelvis",
          end_joint_id: "chest",
          virtual: true,
        },
      ],
      missing_nodes: [],
      stale_nodes: [],
      synchronization_quality: 0.96,
    });
    expect(result.ok).toBe(true);
  });

  it("reports duplicate joint ids", () => {
    const joint = {
      joint_id: "pelvis",
      parent_joint_id: null,
      position_m: [0, 0, 0],
      world_rotation_wxyz: [1, 0, 0, 0],
      valid: true,
      data_age_ms: 0,
      virtual: false,
    };
    const result = validateMocapMessage({
      type: "skeleton.frame.v1",
      schema_version: 1,
      frame_time_us: 10,
      root_position_m: [0, 0, 0],
      joints: [joint, joint],
      segments: [],
      missing_nodes: [],
      stale_nodes: [],
      synchronization_quality: 1,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.join(" ")).toContain("joint_id 不能重复");
  });

  it("enforces the contract's uint16 flags and closed object shape", () => {
    const result = validateMocapMessage({
      type: "pose.frame.v1",
      schema_version: 1,
      node_id: 1,
      frame_time_us: 1,
      quaternion_wxyz: [1, 0, 0, 0],
      quality: 1,
      data_age_ms: 0,
      status_flags: 65_536,
      unexpected: true,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.join(" ")).toContain("uint16");
      expect(result.errors.join(" ")).toContain("未定义字段");
    }
  });

  it("requires virtual on every joint and segment", () => {
    const result = validateMocapMessage({
      type: "skeleton.frame.v1",
      schema_version: 1,
      frame_time_us: 1,
      root_position_m: [0, 0, 0],
      joints: [{
        joint_id: "pelvis",
        parent_joint_id: null,
        position_m: [0, 0, 0],
        world_rotation_wxyz: [1, 0, 0, 0],
        valid: true,
        data_age_ms: 0,
      }],
      segments: [],
      missing_nodes: [],
      stale_nodes: [],
      synchronization_quality: 1,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.join(" ")).toContain("virtual");
  });
});
