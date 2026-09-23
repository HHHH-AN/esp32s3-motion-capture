import { useState } from "react";
import { sendPlaybackAction, setPlaybackSpeed } from "../api/controlClient";

export const PlaybackPanel = () => {
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [message, setMessage] = useState("实时模式");

  const run = async (operation: () => Promise<void>, success: string): Promise<boolean> => {
    try {
      await operation();
      setMessage(success);
      return true;
    } catch (error) {
      setMessage(`操作失败：${error instanceof Error ? error.message : String(error)}`);
      return false;
    }
  };

  const toggleRecord = async (): Promise<void> => {
    const next = !recording;
    if (await run(() => sendPlaybackAction(next ? "record/start" : "record/stop"), next ? "正在录制原始数据" : "录制已保存")) {
      setRecording(next);
    }
  };

  const togglePause = async (): Promise<void> => {
    const next = !paused;
    if (await run(() => sendPlaybackAction(next ? "playback/pause" : "playback/resume"), next ? "回放已暂停" : "回放继续")) {
      setPaused(next);
    }
  };

  const changeSpeed = (value: number): void => {
    setSpeed(value);
    void run(() => setPlaybackSpeed(value), `回放速度 ${value}×`);
  };

  return (
    <section className="panel playback-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SESSION</span>
          <h2>录制与回放</h2>
        </div>
        <span className={recording ? "recording-indicator" : "muted small"}>{recording ? "● REC" : message}</span>
      </div>
      <div className="timeline-unavailable">
        <input className="timeline" aria-label="回放位置（不可用）" type="range" min="0" max="100" value="0" disabled readOnly />
        <span>Seek N/A · 后端尚未定义跳转契约</span>
      </div>
      <div className="playback-controls">
        <button className="button button-secondary" type="button" onClick={() => void toggleRecord()}>
          {recording ? "停止录制" : "开始录制"}
        </button>
        <button className="button" type="button" onClick={() => void togglePause()}>{paused ? "继续" : "暂停"}</button>
        <label>
          倍速
          <select value={speed} onChange={(event) => changeSpeed(Number(event.target.value))}>
            <option value={0.25}>0.25×</option>
            <option value={0.5}>0.5×</option>
            <option value={1}>1×</option>
            <option value={2}>2×</option>
            <option value={4}>4×</option>
          </select>
        </label>
      </div>
    </section>
  );
};
