export type Vector3Tuple = readonly [number, number, number];
export type QuaternionWxyz = readonly [number, number, number, number];

export interface NodePoseMessage {
  readonly type: "pose.frame.v1";
  readonly schema_version: 1;
  readonly node_id: number;
  readonly frame_time_us: number;
  readonly quaternion_wxyz: QuaternionWxyz;
  readonly quality: number;
  readonly data_age_ms: number;
  readonly status_flags: number;
}

export interface SkeletonJoint {
  readonly joint_id: string;
  readonly parent_joint_id: string | null;
  readonly position_m: Vector3Tuple;
  readonly world_rotation_wxyz: QuaternionWxyz;
  readonly valid: boolean;
  readonly data_age_ms: number;
  readonly virtual: boolean;
  readonly node_id?: number;
}

export interface SkeletonSegment {
  readonly segment_id: string;
  readonly start_joint_id: string;
  readonly end_joint_id: string;
  readonly virtual: boolean;
}

export interface SkeletonFrameMessage {
  readonly type: "skeleton.frame.v1";
  readonly schema_version: 1;
  readonly frame_time_us: number;
  readonly root_position_m: Vector3Tuple;
  readonly joints: readonly SkeletonJoint[];
  readonly segments: readonly SkeletonSegment[];
  readonly missing_nodes: readonly number[];
  readonly stale_nodes: readonly number[];
  readonly synchronization_quality: number;
}

export type MocapMessage = NodePoseMessage | SkeletonFrameMessage;

export type ValidationResult =
  | { readonly ok: true; readonly value: MocapMessage }
  | { readonly ok: false; readonly errors: readonly string[] };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const isIntegerInRange = (value: unknown, minimum: number, maximum: number): value is number =>
  Number.isInteger(value) && (value as number) >= minimum && (value as number) <= maximum;

const isVector3 = (value: unknown): value is Vector3Tuple =>
  Array.isArray(value) && value.length === 3 && value.every(isFiniteNumber);

const isQuaternion = (value: unknown): value is QuaternionWxyz => {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(isFiniteNumber)) {
    return false;
  }
  const normSquared = value.reduce((sum, component) => sum + component * component, 0);
  return Math.abs(Math.sqrt(normSquared) - 1) <= 1e-3;
};

const pushUnexpectedKeyErrors = (
  record: Record<string, unknown>,
  allowed: ReadonlySet<string>,
  errors: string[],
  prefix = "",
): void => {
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) errors.push(`${prefix}${key} 是未定义字段`);
  }
};

const POSE_KEYS = new Set([
  "type", "schema_version", "node_id", "frame_time_us", "quaternion_wxyz", "quality", "data_age_ms", "status_flags",
]);
const SKELETON_KEYS = new Set([
  "type", "schema_version", "frame_time_us", "root_position_m", "joints", "segments", "missing_nodes", "stale_nodes", "synchronization_quality",
]);
const JOINT_KEYS = new Set([
  "joint_id", "parent_joint_id", "position_m", "world_rotation_wxyz", "valid", "data_age_ms", "virtual", "node_id",
]);
const SEGMENT_KEYS = new Set([
  "segment_id", "start_joint_id", "end_joint_id", "virtual",
]);

const pushCommonFrameErrors = (record: Record<string, unknown>, errors: string[]): void => {
  if (record.schema_version !== 1) errors.push("schema_version 必须为 1");
  if (!isIntegerInRange(record.frame_time_us, 0, Number.MAX_SAFE_INTEGER)) {
    errors.push("frame_time_us 必须是非负安全整数");
  }
};

const validatePose = (record: Record<string, unknown>): ValidationResult => {
  const errors: string[] = [];
  pushUnexpectedKeyErrors(record, POSE_KEYS, errors);
  pushCommonFrameErrors(record, errors);
  if (!isIntegerInRange(record.node_id, 1, 14)) errors.push("node_id 必须在 1..14");
  if (!isQuaternion(record.quaternion_wxyz)) errors.push("quaternion_wxyz 必须是归一化四元数 [w,x,y,z]，范数误差不超过 1e-3");
  if (!isFiniteNumber(record.quality) || record.quality < 0 || record.quality > 1) {
    errors.push("quality 必须在 0..1");
  }
  if (!isFiniteNumber(record.data_age_ms) || record.data_age_ms < 0) {
    errors.push("data_age_ms 必须是非负数");
  }
  if (!isIntegerInRange(record.status_flags, 0, 0xffff)) {
    errors.push("status_flags 必须是 uint16");
  }
  return errors.length === 0
    ? { ok: true, value: record as unknown as NodePoseMessage }
    : { ok: false, errors };
};

const validateJoint = (value: unknown, index: number, errors: string[]): value is SkeletonJoint => {
  if (!isRecord(value)) {
    errors.push(`joints[${index}] 必须是对象`);
    return false;
  }
  pushUnexpectedKeyErrors(value, JOINT_KEYS, errors, `joints[${index}].`);
  let valid = true;
  const fail = (message: string): void => {
    errors.push(`joints[${index}].${message}`);
    valid = false;
  };
  if (typeof value.joint_id !== "string" || value.joint_id.length === 0) fail("joint_id 必须是非空字符串");
  if (value.parent_joint_id !== null && typeof value.parent_joint_id !== "string") fail("parent_joint_id 必须是字符串或 null");
  if (!isVector3(value.position_m)) fail("position_m 必须是有限三维向量");
  if (!isQuaternion(value.world_rotation_wxyz)) fail("world_rotation_wxyz 必须是归一化四元数");
  if (typeof value.valid !== "boolean") fail("valid 必须是布尔值");
  if (!isFiniteNumber(value.data_age_ms) || value.data_age_ms < 0) fail("data_age_ms 必须是非负数");
  if (typeof value.virtual !== "boolean") fail("virtual 必须是布尔值且不可省略");
  if (value.node_id !== undefined && !isIntegerInRange(value.node_id, 1, 14)) fail("node_id 必须在 1..14");
  return valid;
};

const validateSegment = (value: unknown, index: number, errors: string[]): value is SkeletonSegment => {
  if (!isRecord(value)) {
    errors.push(`segments[${index}] 必须是对象`);
    return false;
  }
  pushUnexpectedKeyErrors(value, SEGMENT_KEYS, errors, `segments[${index}].`);
  let valid = true;
  const requireString = (key: "segment_id" | "start_joint_id" | "end_joint_id"): void => {
    if (typeof value[key] !== "string" || value[key].length === 0) {
      errors.push(`segments[${index}].${key} 必须是非空字符串`);
      valid = false;
    }
  };
  requireString("segment_id");
  requireString("start_joint_id");
  requireString("end_joint_id");
  if (typeof value.virtual !== "boolean") {
    errors.push(`segments[${index}].virtual 必须是布尔值且不可省略`);
    valid = false;
  }
  return valid;
};

const validateSkeleton = (record: Record<string, unknown>): ValidationResult => {
  const errors: string[] = [];
  pushUnexpectedKeyErrors(record, SKELETON_KEYS, errors);
  pushCommonFrameErrors(record, errors);
  if (!isVector3(record.root_position_m)) errors.push("root_position_m 必须是有限三维向量");
  if (!Array.isArray(record.joints)) {
    errors.push("joints 必须是数组");
  } else {
    record.joints.forEach((joint, index) => validateJoint(joint, index, errors));
    const ids = record.joints
      .filter(isRecord)
      .map((joint) => joint.joint_id)
      .filter((id): id is string => typeof id === "string");
    if (new Set(ids).size !== ids.length) errors.push("joint_id 不能重复");
  }
  if (!Array.isArray(record.segments)) {
    errors.push("segments 必须是数组");
  } else {
    record.segments.forEach((segment, index) => validateSegment(segment, index, errors));
  }
  const isNodeArray = (value: unknown): value is number[] =>
    Array.isArray(value) && value.every((nodeId) => isIntegerInRange(nodeId, 1, 14));
  if (!isNodeArray(record.missing_nodes)) errors.push("missing_nodes 必须只包含 1..14");
  else if (new Set(record.missing_nodes).size !== record.missing_nodes.length) errors.push("missing_nodes 不能重复");
  if (!isNodeArray(record.stale_nodes)) errors.push("stale_nodes 必须只包含 1..14");
  else if (new Set(record.stale_nodes).size !== record.stale_nodes.length) errors.push("stale_nodes 不能重复");
  if (!isFiniteNumber(record.synchronization_quality) || record.synchronization_quality < 0 || record.synchronization_quality > 1) {
    errors.push("synchronization_quality 必须在 0..1");
  }
  return errors.length === 0
    ? { ok: true, value: record as unknown as SkeletonFrameMessage }
    : { ok: false, errors };
};

export const validateMocapMessage = (value: unknown): ValidationResult => {
  if (!isRecord(value)) return { ok: false, errors: ["消息必须是 JSON 对象"] };
  if (value.type === "pose.frame.v1") return validatePose(value);
  if (value.type === "skeleton.frame.v1") return validateSkeleton(value);
  return { ok: false, errors: [`不支持的消息类型: ${String(value.type)}`] };
};
