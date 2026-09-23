const apiBase = (): string => import.meta.env.VITE_MOCAP_API_URL ?? "";

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
};

export interface DeviceInfo {
  readonly id: string;
  readonly name: string;
  readonly rssi?: number;
  readonly connected?: boolean;
}

export const scanDevices = (): Promise<readonly DeviceInfo[]> =>
  request<readonly DeviceInfo[]>("/api/devices/scan", { method: "POST" });

export const connectDevice = (id: string): Promise<void> =>
  request<void>("/api/devices/connect", { method: "POST", body: JSON.stringify({ id }) });

export const disconnectDevice = (): Promise<void> =>
  request<void>("/api/devices/disconnect", { method: "POST" });

export const startMountCalibration = (): Promise<void> =>
  request<void>("/api/calibration/mounting", { method: "POST" });

export type PlaybackAction = "record/start" | "record/stop" | "playback/pause" | "playback/resume";

export const sendPlaybackAction = (action: PlaybackAction): Promise<void> =>
  request<void>(`/api/${action}`, { method: "POST" });

export const setPlaybackSpeed = (speed: number): Promise<void> =>
  request<void>("/api/playback/speed", { method: "POST", body: JSON.stringify({ speed }) });
