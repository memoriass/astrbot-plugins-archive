from __future__ import annotations


class SafetyGate:
    HIGH_RISK_TERMS = (
        "删除",
        "清空",
        "格式化",
        "drop table",
        "rm -rf",
        "credential",
        "token",
        "密码",
        "密钥",
        "内网",
    )
    MEDIUM_RISK_TERMS = (
        "shell",
        "命令",
        "执行",
        "重启",
        "restart",
        "deploy",
        "部署",
        "数据库",
        "备份",
        "权限",
        "配置",
    )

    def assess(self, objective: str) -> str:
        text = objective.lower()
        if any(term in text for term in self.HIGH_RISK_TERMS):
            return "high"
        if any(term in text for term in self.MEDIUM_RISK_TERMS):
            return "medium"
        return "normal"

    def initial_status(self, risk_level: str) -> str:
        if risk_level == "high":
            return "waiting_confirm"
        if risk_level == "medium":
            return "risk_review"
        return "open"

    def requires_confirmation(self, risk_level: str) -> bool:
        return risk_level == "high"
