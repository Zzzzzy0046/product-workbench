"use strict";

const statusNames = {
  prepared: "待执行",
  queued: "等待执行",
  running: "生成中",
  completed: "待评审",
  failed: "执行失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
const kinds = {
  upload: "原始资料",
  knowledge: "方法知识",
  deliverable: "待评审草稿",
  accepted: "已确认交付物",
};
const workflowNames = { fast: "快速迭代", full: "完整研究" };
const productVersionTypeNames = {
  "new-product": "新品",
  feature: "功能",
  experience: "体验",
  monetization: "商业化",
  bugfix: "Bugfix",
};
const productVersionStatusNames = {
  planning: "规划中",
  developing: "开发中",
  testing: "测试中",
  released: "已上线",
  reviewed: "已复盘",
  archived: "已归档",
};
const scrapeStatusNames = {
  queued: "等待采集",
  running: "采集中",
  ready: "待确认入库",
  completed: "已完成",
  empty: "无评论",
  failed: "采集失败",
  cancelled: "已取消",
};
const imageSuffixes = new Set(["png", "jpg", "jpeg", "webp"]);
const platformLabels = {
  "Android-first": "Android",
  "iOS-first": "iOS",
  "双端": "双平台",
  Android: "Android",
  iOS: "iOS",
  "双平台": "双平台",
};
const normalizePlatform = (value) =>
  ({ Android: "Android-first", iOS: "iOS-first", "双平台": "双端" }[
    String(value || "")
  ] || String(value || ""));
const platformSelect = (value) => {
  const current = normalizePlatform(value);
  const options = [
    ["", "未指定"],
    ["Android-first", "Android"],
    ["iOS-first", "iOS"],
    ["双端", "双平台"],
  ];
  if (current && !options.some(([option]) => option === current)) {
    options.push([current, String(value)]);
  }
  return options
    .map(
      ([option, label]) =>
        `<option value="${E(option)}" ${option === current ? "selected" : ""}>${E(label)}</option>`,
    )
    .join("");
};
const conditionNames = {
  open: "未开始",
  in_progress: "进行中",
  waiting_evidence: "待证据",
  closed: "已关闭",
  waived: "已豁免",
};
const blockNames = {
  development: "阻塞开发",
  "internal-test": "阻塞内部测试",
  "external-release": "阻塞外部发布",
  "non-blocking": "不阻塞",
};
const versionSourceNames = {
  generated: "模型生成",
  imported: "手工导入",
  manual: "正文编辑",
  restore: "版本恢复",
  legacy: "历史交付物",
  migration: "系统整理",
};
const commentActionNames = {
  add: "新增",
  modify: "修改",
  delete: "删除",
  compress: "压缩",
  preserve: "保留",
};
const commentBlockNames = {
  heading: "标题",
  paragraph: "段落",
  blockquote: "引用",
  table: "表格",
  code: "代码块",
};
