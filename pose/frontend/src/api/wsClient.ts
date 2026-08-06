import { validateMocapMessage, type MocapMessage } from "../types/messages";

export type ConnectionStatus = "idle" | "connecting" | "connected" | "reconnecting" | "disconnected";

export interface ConnectionState {
  readonly status: ConnectionStatus;
  readonly attempt: number;
  readonly retryInMs: number | null;
  readonly detail: string;
}

export interface StreamStats {
  readonly validMessages: number;
  readonly invalidMessages: number;
  readonly receivedBytes: number;
  readonly lastMessageAtMs: number | null;
  readonly lastProtocolError: string | null;
}

export interface WebSocketClientHandlers {
  readonly onMessage: (message: MocapMessage) => void;
  readonly onConnectionChange?: (state: ConnectionState) => void;
  readonly onStatsChange?: (stats: StreamStats) => void;
}

export interface WebSocketClientOptions {
  readonly reconnectBaseMs?: number;
  readonly reconnectMaxMs?: number;
  readonly webSocketFactory?: (url: string) => WebSocket;
}

const INITIAL_STATS: StreamStats = {
  validMessages: 0,
  invalidMessages: 0,
  receivedBytes: 0,
  lastMessageAtMs: null,
  lastProtocolError: null,
};

const defaultChannelUrl = (path: "/ws/pose" | "/ws/skeleton"): string => {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
};

export const defaultPoseWebSocketUrl = (): string =>
  import.meta.env.VITE_MOCAP_POSE_WS_URL ?? defaultChannelUrl("/ws/pose");

export const defaultSkeletonWebSocketUrl = (): string =>
  import.meta.env.VITE_MOCAP_SKELETON_WS_URL ?? defaultChannelUrl("/ws/skeleton");

export class MocapWebSocketClient {
  private socket: WebSocket | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private attempt = 0;
  private stats: StreamStats = INITIAL_STATS;
  private statsTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly reconnectBaseMs: number;
  private readonly reconnectMaxMs: number;
  private readonly webSocketFactory: (url: string) => WebSocket;

  constructor(
    readonly url: string,
    private readonly handlers: WebSocketClientHandlers,
    options: WebSocketClientOptions = {},
  ) {
    this.reconnectBaseMs = options.reconnectBaseMs ?? 500;
    this.reconnectMaxMs = options.reconnectMaxMs ?? 10_000;
    this.webSocketFactory = options.webSocketFactory ?? ((target) => new WebSocket(target));
  }

  connect(): void {
    if (this.running) return;
    this.running = true;
    this.attempt = 0;
    this.open(false);
  }

  disconnect(): void {
    this.running = false;
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.statsTimer !== null) {
      clearTimeout(this.statsTimer);
      this.statsTimer = null;
    }
    const socket = this.socket;
    this.socket = null;
    if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, "client shutdown");
    this.emitConnection("disconnected", null, "已手动断开");
  }

  reconnectNow(): void {
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.running = true;
    const socket = this.socket;
    this.socket = null;
    if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, "manual reconnect");
    this.open(this.attempt > 0);
  }

  getStats(): StreamStats {
    return this.stats;
  }

  private open(reconnecting: boolean): void {
    if (!this.running) return;
    this.emitConnection(reconnecting ? "reconnecting" : "connecting", null, `连接 ${this.url}`);
    let socket: WebSocket;
    try {
      socket = this.webSocketFactory(this.url);
    } catch (error) {
      this.scheduleReconnect(error instanceof Error ? error.message : String(error));
      return;
    }
    this.socket = socket;
    socket.binaryType = "arraybuffer";
    socket.onopen = () => {
      if (this.socket !== socket) return;
      this.attempt = 0;
      this.emitConnection("connected", null, "实时数据已连接");
    };
    socket.onmessage = (event) => {
      if (this.socket !== socket) return;
      void this.consume(event.data);
    };
    socket.onerror = () => {
      if (this.socket === socket) this.emitConnection("reconnecting", null, "WebSocket 发生错误");
    };
    socket.onclose = (event) => {
      if (this.socket !== socket) return;
      this.socket = null;
      if (this.running) this.scheduleReconnect(`连接关闭 (${event.code})`);
    };
  }

  private scheduleReconnect(detail: string): void {
    if (!this.running || this.retryTimer !== null) return;
    this.attempt += 1;
    const delay = Math.min(this.reconnectMaxMs, this.reconnectBaseMs * 2 ** (this.attempt - 1));
    this.emitConnection("reconnecting", delay, detail);
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.open(true);
    }, delay);
  }

  private async consume(data: unknown): Promise<void> {
    let text: string;
    if (typeof data === "string") {
      text = data;
    } else if (data instanceof ArrayBuffer) {
      text = new TextDecoder().decode(data);
    } else if (typeof Blob !== "undefined" && data instanceof Blob) {
      text = await data.text();
    } else {
      this.recordInvalid("WebSocket 数据不是文本、ArrayBuffer 或 Blob", 0);
      return;
    }

    let decoded: unknown;
    try {
      decoded = JSON.parse(text);
    } catch {
      this.recordInvalid("收到无效 JSON", text.length);
      return;
    }
    const result = validateMocapMessage(decoded);
    if (!result.ok) {
      this.recordInvalid(result.errors.join("；"), text.length);
      return;
    }
    this.stats = {
      ...this.stats,
      validMessages: this.stats.validMessages + 1,
      receivedBytes: this.stats.receivedBytes + text.length,
      lastMessageAtMs: Date.now(),
      lastProtocolError: null,
    };
    this.scheduleStatsEmission();
    this.handlers.onMessage(result.value);
  }

  private recordInvalid(error: string, bytes: number): void {
    this.stats = {
      ...this.stats,
      invalidMessages: this.stats.invalidMessages + 1,
      receivedBytes: this.stats.receivedBytes + bytes,
      lastMessageAtMs: Date.now(),
      lastProtocolError: error,
    };
    this.scheduleStatsEmission();
  }

  private scheduleStatsEmission(): void {
    if (this.statsTimer !== null) return;
    this.statsTimer = setTimeout(() => {
      this.statsTimer = null;
      this.handlers.onStatsChange?.(this.stats);
    }, 100);
  }

  private emitConnection(status: ConnectionStatus, retryInMs: number | null, detail: string): void {
    this.handlers.onConnectionChange?.({ status, attempt: this.attempt, retryInMs, detail });
  }
}
