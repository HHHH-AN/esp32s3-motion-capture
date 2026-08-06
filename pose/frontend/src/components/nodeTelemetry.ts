import type { NodePoseMessage, SkeletonFrameMessage } from "../types/messages";

export type NodeTelemetryState = "online" | "stale" | "missing" | "waiting";

export interface NodeTelemetry {
  readonly state: NodeTelemetryState;
  readonly ageLabel: string;
  readonly qualityLabel: string;
  readonly packetRateLabel: "N/A";
  readonly batteryLabel: "N/A";
}

const skeletonAge = (nodeId: number, skeleton: SkeletonFrameMessage | null): number | null => {
  if (!skeleton) return null;
  const ages = skeleton.joints
    .filter((joint) => joint.node_id === nodeId && Number.isFinite(joint.data_age_ms))
    .map((joint) => joint.data_age_ms);
  return ages.length === 0 ? null : Math.min(...ages);
};

export const getNodeTelemetry = (
  nodeId: number,
  pose: NodePoseMessage | undefined,
  skeleton: SkeletonFrameMessage | null,
): NodeTelemetry => {
  const ageMs = pose?.data_age_ms ?? skeletonAge(nodeId, skeleton);
  const hasValidSkeletonJoint = skeleton?.joints.some(
    (joint) => joint.node_id === nodeId && joint.valid,
  ) ?? false;
  let state: NodeTelemetryState;
  if (skeleton?.missing_nodes.includes(nodeId)) state = "missing";
  else if (skeleton?.stale_nodes.includes(nodeId) || (ageMs !== null && ageMs > 100)) state = "stale";
  else if (pose || hasValidSkeletonJoint) state = "online";
  else state = "waiting";

  return {
    state,
    ageLabel:
      state === "missing" || state === "waiting" || ageMs === null
        ? "N/A"
        : `${ageMs.toFixed(1)} ms`,
    qualityLabel: pose ? `${(pose.quality * 100).toFixed(0)}%` : "N/A",
    packetRateLabel: "N/A",
    batteryLabel: "N/A",
  };
};
