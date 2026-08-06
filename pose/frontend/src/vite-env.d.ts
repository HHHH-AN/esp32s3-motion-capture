/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MOCAP_POSE_WS_URL?: string;
  readonly VITE_MOCAP_SKELETON_WS_URL?: string;
  readonly VITE_MOCAP_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
