import type { StreamStats } from "../api/wsClient";

interface DiagnosticsPanelProps {
  readonly stats: StreamStats;
  readonly fps: number;
  readonly latestAgeMs: number | null;
  readonly synchronizationQuality: number | null;
}

const formatBytes = (bytes: number): string =>
  bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KiB`;

export const DiagnosticsPanel = ({
  stats,
  fps,
  latestAgeMs,
  synchronizationQuality,
}: DiagnosticsPanelProps) => (
  <section className="panel">
    <div className="panel-heading">
      <div>
        <span className="eyebrow">RUNTIME</span>
        <h2>运行诊断</h2>
      </div>
      <span className={fps >= 55 ? "metric-ok" : "metric-warn"}>{fps.toFixed(0)} FPS</span>
    </div>
    <div className="metrics-grid">
      <div><span>合法消息</span><strong>{stats.validMessages}</strong></div>
      <div><span>非法消息</span><strong>{stats.invalidMessages}</strong></div>
      <div><span>已接收</span><strong>{formatBytes(stats.receivedBytes)}</strong></div>
      <div><span>数据年龄</span><strong>{latestAgeMs === null ? "—" : `${latestAgeMs.toFixed(0)} ms`}</strong></div>
      <div><span>同步质量</span><strong>{synchronizationQuality === null ? "—" : `${(synchronizationQuality * 100).toFixed(0)}%`}</strong></div>
      <div><span>目标帧率</span><strong>60 FPS</strong></div>
    </div>
    {stats.lastProtocolError && <p className="error-text">协议错误：{stats.lastProtocolError}</p>}
  </section>
);
