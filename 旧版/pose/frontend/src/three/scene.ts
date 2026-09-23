import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { NodePoseMessage, SkeletonFrameMessage } from "../types/messages";
import { SkeletonFrameInterpolator } from "./frameInterpolator";
import { ImuCube } from "./imuCube";
import { SkeletonRig } from "./skeletonRig";

export interface SceneMetrics {
  readonly fps: number;
}

export class MocapScene {
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(45, 1, 0.01, 50);
  private readonly renderer: THREE.WebGLRenderer;
  private readonly controls: OrbitControls;
  private readonly imuCube = new ImuCube();
  private readonly skeletonRig = new SkeletonRig();
  private readonly interpolator = new SkeletonFrameInterpolator(35);
  private readonly resizeObserver: ResizeObserver | null;
  private animationId = 0;
  private frameCount = 0;
  private fpsWindowStart = performance.now();
  private hasSkeleton = false;
  private hasPose = false;

  constructor(
    private readonly container: HTMLElement,
    private readonly onMetrics?: (metrics: SceneMetrics) => void,
  ) {
    this.scene.background = new THREE.Color(0x081119);
    this.scene.fog = new THREE.Fog(0x081119, 7, 18);
    this.camera.position.set(3.1, 2.2, 4.2);
    this.camera.lookAt(0, 1, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.container.replaceChildren(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 1, 0);
    this.controls.minDistance = 1.2;
    this.controls.maxDistance = 12;

    this.scene.add(new THREE.HemisphereLight(0xb9e5ff, 0x16202b, 1.7));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
    keyLight.position.set(3, 6, 2);
    keyLight.castShadow = true;
    this.scene.add(keyLight);
    const grid = new THREE.GridHelper(10, 20, 0x2d5265, 0x172d39);
    this.scene.add(grid);
    this.scene.add(this.imuCube.group, this.skeletonRig.group);
    this.skeletonRig.setVisible(false);

    this.resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => this.resize());
    this.resizeObserver?.observe(this.container);
    window.addEventListener("resize", this.resize);
    this.resize();
    this.animate();
  }

  setPose(pose: NodePoseMessage | null): void {
    this.hasPose = pose !== null;
    if (pose) this.imuCube.applyPose(pose);
    this.imuCube.setVisible(!this.hasSkeleton && this.hasPose);
  }

  setSkeleton(frame: SkeletonFrameMessage | null): void {
    this.hasSkeleton = frame !== null;
    this.skeletonRig.setVisible(this.hasSkeleton);
    if (frame) this.interpolator.push(frame, performance.now());
    else this.interpolator.clear();
    this.imuCube.setVisible(!this.hasSkeleton && this.hasPose);
  }

  dispose(): void {
    cancelAnimationFrame(this.animationId);
    this.resizeObserver?.disconnect();
    window.removeEventListener("resize", this.resize);
    this.controls.dispose();
    this.imuCube.dispose();
    this.skeletonRig.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  private readonly resize = (): void => {
    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  };

  private readonly animate = (): void => {
    this.animationId = requestAnimationFrame(this.animate);
    const now = performance.now();
    if (this.hasSkeleton) {
      const interpolated = this.interpolator.sample(now);
      if (interpolated) this.skeletonRig.applyFrame(interpolated);
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.frameCount += 1;
    const elapsed = now - this.fpsWindowStart;
    if (elapsed >= 1000) {
      this.onMetrics?.({ fps: (this.frameCount * 1000) / elapsed });
      this.frameCount = 0;
      this.fpsWindowStart = now;
    }
  };
}
