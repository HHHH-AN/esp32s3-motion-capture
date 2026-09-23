export const NODE_LABELS: Readonly<Record<number, string>> = {
  1: "骨盆",
  2: "头部",
  3: "左上臂",
  4: "右上臂",
  5: "左前臂",
  6: "右前臂",
  7: "左手",
  8: "右手",
  9: "左大腿",
  10: "右大腿",
  11: "左小腿",
  12: "右小腿",
  13: "左脚",
  14: "右脚",
};

export const WEARABLE_NODE_IDS = Object.freeze(
  Array.from({ length: 14 }, (_, index) => index + 1),
);
