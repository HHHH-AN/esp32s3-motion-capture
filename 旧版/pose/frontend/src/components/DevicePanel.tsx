import { useState } from "react";
import { connectDevice, disconnectDevice, scanDevices, type DeviceInfo } from "../api/controlClient";

export const DevicePanel = () => {
  const [devices, setDevices] = useState<readonly DeviceInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("BLE 由本机 Python Bridge 管理");

  const run = async (operation: () => Promise<void>, success: string): Promise<void> => {
    setBusy(true);
    try {
      await operation();
      setMessage(success);
    } catch (error) {
      setMessage(`操作失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const scan = (): void => {
    void run(async () => setDevices(await scanDevices()), "扫描完成");
  };

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">GATEWAY</span>
          <h2>网关设备</h2>
        </div>
        <button className="button button-secondary" type="button" disabled={busy} onClick={scan}>扫描</button>
      </div>
      <p className="muted small">{message}</p>
      <div className="device-list">
        {devices.length === 0 && <div className="empty-row">尚未发现设备</div>}
        {devices.map((device) => (
          <div className="device-row" key={device.id}>
            <div>
              <strong>{device.name || "未命名网关"}</strong>
              <span className="monospace small">{device.id}</span>
            </div>
            <span className="muted">{device.rssi === undefined ? "" : `${device.rssi} dBm`}</span>
            <button
              className="button button-small"
              type="button"
              disabled={busy}
              onClick={() => void run(() => connectDevice(device.id), `已请求连接 ${device.name}`)}
            >连接</button>
          </div>
        ))}
      </div>
      <button
        className="button button-ghost full-width"
        type="button"
        disabled={busy}
        onClick={() => void run(disconnectDevice, "已断开网关")}
      >断开当前设备</button>
    </section>
  );
};
