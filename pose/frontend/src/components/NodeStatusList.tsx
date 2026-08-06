import type { NodePoseMessage, SkeletonFrameMessage } from "../types/messages";
import { NODE_LABELS, WEARABLE_NODE_IDS } from "../types/nodeLayout";
import { getNodeTelemetry, type NodeTelemetryState } from "./nodeTelemetry";

interface NodeStatusListProps {
  readonly poses: ReadonlyMap<number, NodePoseMessage>;
  readonly skeleton: SkeletonFrameMessage | null;
}

const STATE_LABEL: Record<NodeTelemetryState, string> = {
  online: "在线",
  stale: "延迟",
  missing: "缺失",
  waiting: "等待",
};

export const NodeStatusList = ({ poses, skeleton }: NodeStatusListProps) => (
  <section className="panel node-panel">
    <div className="panel-heading">
      <div>
        <span className="eyebrow">14 WEARABLE NODES</span>
        <h2>佩戴节点</h2>
      </div>
      <span className="muted small">胸段为虚拟骨段</span>
    </div>
    <div className="node-grid">
      {WEARABLE_NODE_IDS.map((nodeId) => {
        const pose = poses.get(nodeId);
        const telemetry = getNodeTelemetry(nodeId, pose, skeleton);
        return (
          <article className={`node-card node-${telemetry.state}`} key={nodeId}>
            <div className="node-card-heading">
              <span className="node-id">{String(nodeId).padStart(2, "0")}</span>
              <strong>{NODE_LABELS[nodeId]}</strong>
              <span className="node-state">{STATE_LABEL[telemetry.state]}</span>
            </div>
            <dl className="node-metrics">
              <div><dt>数据年龄</dt><dd>{telemetry.ageLabel}</dd></div>
              <div><dt>姿态质量</dt><dd>{telemetry.qualityLabel}</dd></div>
              <div><dt>包率</dt><dd>{telemetry.packetRateLabel}</dd></div>
              <div><dt>电量</dt><dd>{telemetry.batteryLabel}</dd></div>
            </dl>
          </article>
        );
      })}
    </div>
  </section>
);
