import { describe, expect, it } from "vitest";
import { SkeletonRig } from "../three/skeletonRig";
import type { SkeletonFrameMessage } from "../types/messages";

describe("SkeletonRig", () => {
  it("renders absolute joint positions without adding root_position_m twice", () => {
    const frame: SkeletonFrameMessage = {
      type: "skeleton.frame.v1",
      schema_version: 1,
      frame_time_us: 1,
      root_position_m: [1, 0, 0],
      joints: [{
        joint_id: "pelvis",
        parent_joint_id: null,
        position_m: [1, 0, 0],
        world_rotation_wxyz: [1, 0, 0, 0],
        valid: true,
        data_age_ms: 0,
        virtual: false,
        node_id: 1,
      }],
      segments: [],
      missing_nodes: [],
      stale_nodes: [],
      synchronization_quality: 1,
    };
    const rig = new SkeletonRig();
    rig.applyFrame(frame);
    const pelvis = rig.group.getObjectByName("joint:pelvis");
    expect(rig.group.position.toArray()).toEqual([0, 0, 0]);
    expect(pelvis?.position.x).toBeCloseTo(0);
    expect(pelvis?.position.y).toBeCloseTo(0);
    expect(pelvis?.position.z).toBeCloseTo(-1);
    rig.dispose();
  });
});
