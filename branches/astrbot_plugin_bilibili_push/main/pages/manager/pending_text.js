const WORKFLOW_TITLES = {
  add_subscription: "待确认订阅",
  remove_subscription: "待确认取消",
};

const KIND_TITLES = {
  up_candidates: "待选择 UP 主",
  confirm_subscription: "待确认订阅",
};

const WORKFLOW_DETAILS = {
  add_subscription: "确认后会新增订阅",
  remove_subscription: "确认后会取消订阅",
};

const KIND_DETAILS = {
  up_candidates: "请选择正确的 UP 主",
  confirm_subscription: "确认后继续处理订阅",
};

export function pendingTitle(task = {}) {
  return WORKFLOW_TITLES[task.workflow] || KIND_TITLES[task.kind] || "待处理事项";
}

export function pendingSummary(task = {}) {
  const detail = WORKFLOW_DETAILS[task.workflow] || KIND_DETAILS[task.kind] || "需要你确认后继续";
  const count = Number(task.candidate_count || 0);
  return count > 0 ? `${detail}，${count} 个候选项` : detail;
}

export function pendingCandidateText(task = {}) {
  return `${Number(task.candidate_count || 0)} 个`;
}
