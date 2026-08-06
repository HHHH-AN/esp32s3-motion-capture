import { useEffect, useRef } from "react";
import type { NodePoseMessage, SkeletonFrameMessage } from "../types/messages";
import { MocapScene, type SceneMetrics } from "../three/scene";

interface SkeletonViewportProps {
  readonly pose: NodePoseMessage | null;
  readonly skeleton: SkeletonFrameMessage | null;
  readonly onMetrics: (metrics: SceneMetrics) => void;
}

export const SkeletonViewport = ({ pose, skeleton, onMetrics }: SkeletonViewportProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<MocapScene | null>(null);
  const metricsRef = useRef(onMetrics);
  metricsRef.current = onMetrics;

  useEffect(() => {
    if (!containerRef.current) return;
    const scene = new MocapScene(containerRef.current, (metrics) => metricsRef.current(metrics));
    sceneRef.current = scene;
    return () => {
      sceneRef.current = null;
      scene.dispose();
    };
  }, []);

  useEffect(() => sceneRef.current?.setPose(pose), [pose]);
  useEffect(() => sceneRef.current?.setSkeleton(skeleton), [skeleton]);

  return (
    <div className="viewport-shell">
      <div ref={containerRef} className="viewport-canvas" aria-label="动作捕捉三维视图" />
      <div className="viewport-hint">拖动旋转 · 滚轮缩放 · 右键平移</div>
      {!pose && !skeleton && (
        <div className="viewport-empty">
          <span className="pulse-dot" />
          正在等待姿态数据
        </div>
      )}
    </div>
  );
};
