"""数据模型：全部为 dataclass，便于测试与序列化。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Material:
    id: str
    title: str = ""
    type: str = ""
    duration_seconds: int = 0
    format: str = ""
    license: str = ""
    owner: str = ""
    sensitive_flags: list = field(default_factory=list)
    disclaimer: str = ""
    supplement: dict = field(default_factory=dict)

    def missing_fields(self) -> list:
        """返回缺失的关键字段名。空字符串视为缺失。"""
        missing = []
        if not self.title:
            missing.append("title")
        if not self.license:
            missing.append("license")
        if not self.disclaimer:
            missing.append("disclaimer")
        return missing


@dataclass
class Risk:
    rule_id: str
    severity: str  # "block" 或 "warn"
    reason: str


@dataclass
class DraftRecord:
    draft_id: str
    material_id: str
    requested_slot: str
    suggested_slot: str
    status: str = "draft"
    pending_confirmation: bool = False
    idempotency_key: str = ""
    created_at: str = ""


@dataclass
class AgentRequest:
    material_id: str
    requested_slot: str
    request_id: str = ""
