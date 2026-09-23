import { useSyncExternalStore } from "react";
import type { NodePoseMessage } from "../types/messages";

export interface PoseSnapshot {
  readonly byNode: ReadonlyMap<number, NodePoseMessage>;
  readonly latest: NodePoseMessage | null;
}

class PoseStore {
  private snapshot: PoseSnapshot = { byNode: new Map(), latest: null };
  private readonly listeners = new Set<() => void>();
  private notificationPending = false;

  getSnapshot = (): PoseSnapshot => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  update(pose: NodePoseMessage): void {
    const byNode = new Map(this.snapshot.byNode);
    byNode.set(pose.node_id, pose);
    this.snapshot = { byNode, latest: pose };
    this.scheduleNotification();
  }

  clear(): void {
    this.snapshot = { byNode: new Map(), latest: null };
    this.scheduleNotification();
  }

  private scheduleNotification(): void {
    if (this.notificationPending) return;
    this.notificationPending = true;
    const notify = (): void => {
      this.notificationPending = false;
      this.listeners.forEach((listener) => listener());
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(notify);
    else queueMicrotask(notify);
  }
}

export const poseStore = new PoseStore();
export const usePoseSnapshot = (): PoseSnapshot =>
  useSyncExternalStore(poseStore.subscribe, poseStore.getSnapshot, poseStore.getSnapshot);
