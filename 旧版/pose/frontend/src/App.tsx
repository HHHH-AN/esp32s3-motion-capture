import { useEffect, useMemo, useRef, useState } from "react";
import {
  defaultPoseWebSocketUrl,
  defaultSkeletonWebSocketUrl,
  MocapWebSocketClient,
  type ConnectionState,
  type StreamStats,
} from "./api/wsClient";
import { CalibrationWizard } from "./components/CalibrationWizard";
import { ConnectionPanel } from "./components/ConnectionPanel";
import { DevicePanel } from "./components/DevicePanel";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { NodeStatusList } from "./components/NodeStatusList";
import { PlaybackPanel } from "./components/PlaybackPanel";
import { SkeletonViewport } from "./components/SkeletonViewport";
import { poseStore, usePoseSnapshot } from "./state/poseStore";
import { skeletonStore, useSkeletonSnapshot } from "./state/skeletonStore";
import type { MocapMessage } from "./types/messages";

const INITIAL_CONNECTION: ConnectionState = {
  status: "idle",
  attempt: 0,
  retryInMs: null,
  detail: "等待启动",
};

const INITIAL_STATS: StreamStats = {
  validMessages: 0,
  invalidMessages: 0,
  receivedBytes: 0,
  lastMessageAtMs: null,
  lastProtocolError: null,
};

export const App = () => {
  const poses = usePoseSnapshot();
  const skeleton = useSkeletonSnapshot();
  const poseSocketRef = useRef<MocapWebSocketClient | null>(null);
  const skeletonSocketRef = useRef<MocapWebSocketClient | null>(null);
  const [poseConnection, setPoseConnection] = useState(INITIAL_CONNECTION);
  const [skeletonConnection, setSkeletonConnection] = useState(INITIAL_CONNECTION);
  const [poseStats, setPoseStats] = useState(INITIAL_STATS);
  const [skeletonStats, setSkeletonStats] = useState(INITIAL_STATS);
  const [fps, setFps] = useState(0);
  const poseWsUrl = useMemo(defaultPoseWebSocketUrl, []);
  const skeletonWsUrl = useMemo(defaultSkeletonWebSocketUrl, []);

  useEffect(() => {
    const onMessage = (message: MocapMessage): void => {
      if (message.type === "pose.frame.v1") poseStore.update(message);
      else skeletonStore.update(message);
    };
    const poseClient = new MocapWebSocketClient(poseWsUrl, {
      onMessage,
      onConnectionChange: setPoseConnection,
      onStatsChange: setPoseStats,
    });
    const skeletonClient = new MocapWebSocketClient(skeletonWsUrl, {
      onMessage,
      onConnectionChange: setSkeletonConnection,
      onStatsChange: setSkeletonStats,
    });
    poseSocketRef.current = poseClient;
    skeletonSocketRef.current = skeletonClient;
    poseClient.connect();
    skeletonClient.connect();
    return () => {
      poseSocketRef.current = null;
      skeletonSocketRef.current = null;
      poseClient.disconnect();
      skeletonClient.disconnect();
    };
  }, [poseWsUrl, skeletonWsUrl]);

  const stats = useMemo<StreamStats>(() => {
    const latestMessageAt = Math.max(
      poseStats.lastMessageAtMs ?? -1,
      skeletonStats.lastMessageAtMs ?? -1,
    );
    return {
      validMessages: poseStats.validMessages + skeletonStats.validMessages,
      invalidMessages: poseStats.invalidMessages + skeletonStats.invalidMessages,
      receivedBytes: poseStats.receivedBytes + skeletonStats.receivedBytes,
      lastMessageAtMs: latestMessageAt < 0 ? null : latestMessageAt,
      lastProtocolError: poseStats.lastProtocolError ?? skeletonStats.lastProtocolError,
    };
  }, [poseStats, skeletonStats]);

  const unavailable = new Set([
    ...(skeleton?.missing_nodes ?? []),
    ...(skeleton?.stale_nodes ?? []),
  ]);
  const onlineNodes = [...poses.byNode.values()].filter(
    (pose) => pose.data_age_ms <= 100 && !unavailable.has(pose.node_id),
  ).length;
  const latestAgeMs = poses.latest?.data_age_ms ?? null;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
        <div className="brand-copy">
          <span className="eyebrow">ESP32-S3 · 14 NODE</span>
          <h1>IMU Motion Capture</h1>
        </div>
        <div className="topbar-meta">
          <span className={`live-badge ${poseConnection.status === "connected" && skeletonConnection.status === "connected" ? "is-live" : ""}`}>
            <span />{poseConnection.status === "connected" && skeletonConnection.status === "connected" ? "LIVE" : "OFFLINE"}
          </span>
          <span className="coordinate-label">+X 前 · +Y 左 · +Z 上</span>
        </div>
      </header>

      <main className="dashboard">
        <div className="primary-column">
          <SkeletonViewport
            pose={poses.latest}
            skeleton={skeleton}
            onMetrics={({ fps: nextFps }) => setFps(nextFps)}
          />
          <NodeStatusList poses={poses.byNode} skeleton={skeleton} />
          <PlaybackPanel />
        </div>
        <aside className="sidebar">
          <ConnectionPanel
            title="节点姿态流"
            state={poseConnection}
            url={poseWsUrl}
            onReconnect={() => poseSocketRef.current?.reconnectNow()}
          />
          <ConnectionPanel
            title="骨架流"
            state={skeletonConnection}
            url={skeletonWsUrl}
            onReconnect={() => skeletonSocketRef.current?.reconnectNow()}
          />
          <DiagnosticsPanel
            stats={stats}
            fps={fps}
            latestAgeMs={latestAgeMs}
            synchronizationQuality={skeleton?.synchronization_quality ?? null}
          />
          <DevicePanel />
          <CalibrationWizard onlineNodes={onlineNodes} />
        </aside>
      </main>
      <footer>
        <span>姿态融合、同步与骨架计算均由 Python Bridge 执行</span>
        <span>胸部：虚拟骨段 · 根位置：固定骨盆</span>
      </footer>
    </div>
  );
};
