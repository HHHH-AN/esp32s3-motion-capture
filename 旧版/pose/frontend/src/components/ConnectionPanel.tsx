import type { ConnectionState } from "../api/wsClient";

interface ConnectionPanelProps {
  readonly title: string;
  readonly state: ConnectionState;
  readonly url: string;
  readonly onReconnect: () => void;
}

const LABELS: Record<ConnectionState["status"], string> = {
  idle: "未启动",
  connecting: "连接中",
  connected: "已连接",
  reconnecting: "正在重连",
  disconnected: "已断开",
};

export const ConnectionPanel = ({ title, state, url, onReconnect }: ConnectionPanelProps) => (
  <section className="panel compact-panel">
    <div className="panel-heading">
      <div>
        <span className="eyebrow">PYTHON BRIDGE</span>
        <h2>{title}</h2>
      </div>
      <span className={`status-pill status-${state.status}`}>
        <span className="status-dot" />{LABELS[state.status]}
      </span>
    </div>
    <p className="monospace truncate" title={url}>{url}</p>
    <p className="muted small">
      {state.detail}
      {state.retryInMs !== null ? `，${(state.retryInMs / 1000).toFixed(1)} 秒后重试` : ""}
    </p>
    <button className="button button-secondary" type="button" onClick={onReconnect}>立即重连</button>
  </section>
);
