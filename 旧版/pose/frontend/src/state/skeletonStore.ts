import { useSyncExternalStore } from "react";
import type { SkeletonFrameMessage } from "../types/messages";

class SkeletonStore {
  private snapshot: SkeletonFrameMessage | null = null;
  private readonly listeners = new Set<() => void>();

  getSnapshot = (): SkeletonFrameMessage | null => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  update(frame: SkeletonFrameMessage): void {
    this.snapshot = frame;
    this.listeners.forEach((listener) => listener());
  }

  clear(): void {
    this.snapshot = null;
    this.listeners.forEach((listener) => listener());
  }
}

export const skeletonStore = new SkeletonStore();
export const useSkeletonSnapshot = (): SkeletonFrameMessage | null =>
  useSyncExternalStore(skeletonStore.subscribe, skeletonStore.getSnapshot, skeletonStore.getSnapshot);
