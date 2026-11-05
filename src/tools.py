"""业务工具：素材读取、规则检查、时段查询、补查、草稿保存。

工具均为本地函数/Mock，不调用真实外部服务。每个工具都有 JSON Schema，
模型看到的正是这份 Schema；执行前按 Schema 校验参数，未知工具或
参数错误返回观察错误（error 字段），循环继续，不崩溃。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .models import Material

TOOL_SCHEMAS = {
    "get_material": {
        "description": "读取素材元数据；不存在时返回 not_found。",
        "parameters": {
            "type": "object",
            "properties": {"material_id": {"type": "string"}},
            "required": ["material_id"],
        },
    },
    "check_rules": {
        "description": "按 data/rules.json 对素材执行规则检查，返回风险列表。",
        "parameters": {
            "type": "object",
            "properties": {"material_id": {"type": "string"}},
            "required": ["material_id"],
        },
    },
    "query_schedule": {
        "description": "查询某时段是否被占用；被占时返回附近空闲时段。",
        "parameters": {
            "type": "object",
            "properties": {"slot": {"type": "string", "description": "HH:MM 格式"}},
            "required": ["slot"],
        },
    },
    "supplement_info": {
        "description": "补查素材缺失信息；部分素材补查后仍缺失。",
        "parameters": {
            "type": "object",
            "properties": {"material_id": {"type": "string"}},
            "required": ["material_id"],
        },
    },
    "save_draft": {
        "description": "仅保存发布草稿，绝不真实发布。幂等：同一 material_id + requested_slot 只产生一份草稿。",
        "parameters": {
            "type": "object",
            "properties": {
                "material_id": {"type": "string"},
                "requested_slot": {"type": "string"},
                "suggested_slot": {"type": "string"},
                "pending_confirmation": {"type": "boolean"},
            },
            "required": ["material_id", "requested_slot", "suggested_slot"],
        },
    },
}

_SLOT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class DraftStore:
    """草稿存储：JSON 文件。幂等键 = material_id + "|" + requested_slot。

    draft_id 由幂等键的 sha256 前 12 位确定，因此重复提交返回同一 draft_id
    且不产生第二条记录。fail_save=True 模拟保存失败：不写文件、不返回 draft_id。
    """

    def __init__(self, path: Path | str, fail_save: bool = False):
        self.path = Path(path)
        self.fail_save = fail_save

    def _read_all(self) -> list:
        data = _load_json(self.path, [])
        if not isinstance(data, list):
            raise ValueError("草稿存储格式错误：应为数组")
        return data

    def _write_all(self, records: list) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(records, ensure_ascii=False, indent=2)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             delete=False) as output:
                temporary = output.name
                output.write(content)
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def count(self) -> int:
        return len(self._read_all())

    def save(self, material_id: str, requested_slot: str, suggested_slot: str,
             pending_confirmation: bool) -> dict:
        if self.fail_save:
            return {"error": "save_failed", "draft_saved": False,
                    "detail": "草稿存储写入失败（模拟故障）"}
        key = f"{material_id}|{requested_slot}"
        idempotency_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        records = self._read_all()
        for rec in records:
            if rec.get("idempotency_key") == idempotency_key:
                return {"draft_id": rec["draft_id"], "draft_saved": True,
                        "duplicate": True, "material_id": material_id,
                        "requested_slot": requested_slot,
                        "suggested_slot": rec["suggested_slot"],
                        "pending_confirmation": rec["pending_confirmation"],
                        "status": "draft"}
        draft_id = "D-" + idempotency_key[:12]
        record = {
            "draft_id": draft_id,
            "material_id": material_id,
            "requested_slot": requested_slot,
            "suggested_slot": suggested_slot,
            "status": "draft",
            "pending_confirmation": bool(pending_confirmation),
            "idempotency_key": idempotency_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        records.append(record)
        self._write_all(records)
        return {"draft_id": draft_id, "draft_saved": True, "duplicate": False,
                "material_id": material_id, "requested_slot": requested_slot,
                "suggested_slot": suggested_slot,
                "pending_confirmation": bool(pending_confirmation), "status": "draft"}


class Tools:
    def __init__(self, data_dir: Path | str | None = None, draft_store: DraftStore | None = None):
        base = Path(__file__).resolve().parent.parent
        self.data_dir = Path(data_dir) if data_dir else base / "data"
        raw_materials = _load_json(self.data_dir / "materials.json", {})
        items = raw_materials.get("materials", []) if isinstance(raw_materials, dict) else raw_materials
        self.materials: dict[str, Material] = {}
        for item in items:
            mat = Material(
                id=item.get("id", ""), work_status=item.get("work_status", "unspecified"), title=item.get("title", ""),
                type=item.get("type", ""), duration_seconds=item.get("duration_seconds", 0),
                format=item.get("format", ""), license=item.get("license", ""),
                owner=item.get("owner", ""), sensitive_flags=item.get("sensitive_flags", []),
                disclaimer=item.get("disclaimer", ""), supplement=item.get("supplement", {}),
            )
            self.materials[mat.id] = mat
        raw_rules = _load_json(self.data_dir / "rules.json", {})
        self.rules = raw_rules.get("rules", []) if isinstance(raw_rules, dict) else raw_rules
        raw_schedule = _load_json(self.data_dir / "schedule.json", {})
        self.schedule = raw_schedule.get("slots", {}) if isinstance(raw_schedule, dict) else {}
        self.draft_store = draft_store or DraftStore(Path.cwd() / ".drafts.json")
        self.request = None
        self.observations = []

    def begin_request(self, request):
        self.request = request
        self.observations = []

    def _own_draft(self, record):
        return bool(self.request and record.get("material_id") == self.request.material_id
                    and record.get("requested_slot") == self.request.requested_slot)

    # -- 校验 ---------------------------------------------------------
    def _validate(self, name: str, args: dict) -> str | None:
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            return f"unknown_tool: {name}"
        if not isinstance(args, dict):
            return "invalid_params: action_input 必须是对象"
        for req in schema["parameters"].get("required", []):
            if req not in args:
                return f"invalid_params: 缺少必需参数 {req}"
        for key, value in args.items():
            if key not in schema["parameters"]["properties"]:
                return f"invalid_params: 未知参数 {key}"
            expected = schema["parameters"]["properties"].get(key, {}).get("type")
            if expected == "string" and not isinstance(value, str):
                return f"invalid_params: 参数 {key} 应为字符串"
            if expected == "boolean" and not isinstance(value, bool):
                return f"invalid_params: 参数 {key} 应为布尔值"
        return None

    def dispatch(self, name: str, args: dict) -> dict:
        err = self._validate(name, args)
        if err:
            if err.startswith("unknown_tool"):
                return {"error": err, "tool": name}
            return {"error": err, "tool": name}
        handler = {
            "get_material": self.get_material,
            "check_rules": self.check_rules,
            "query_schedule": self.query_schedule,
            "supplement_info": self.supplement_info,
            "save_draft": self.save_draft,
        }[name]
        try:
            result = handler(**args)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            error = "save_failed" if name == "save_draft" else "tool_failed"
            result = {"error": error, "tool": name, "detail": str(exc)}
        self.observations.append((name, args, result))
        return result

    # -- 工具实现 ------------------------------------------------------
    def list_pending_materials(self) -> dict:
        """列出明确标记为 pending 的素材；未识别状态单独列出。"""
        records = self.draft_store._read_all()
        pending, unclassified = [], []
        for material in self.materials.values():
            if material.work_status not in ("pending", "completed", "archived"):
                unclassified.append({"material_id": material.id, "work_status": material.work_status})
                continue
            if material.work_status != "pending":
                continue
            drafts = []
            for rec in records:
                if rec.get("material_id") != material.id:
                    continue
                slot = rec.get("suggested_slot")
                entry = self.schedule.get(slot) or {}
                conflict = bool(entry.get("occupied")) or any(
                    other is not rec and other.get("suggested_slot") == slot for other in records)
                drafts.append({"draft_id": rec.get("draft_id"), "suggested_slot": slot,
                               "pending_confirmation": bool(rec.get("pending_confirmation")),
                               "slot_conflict": conflict})
            state = ("draft_conflict" if any(d["slot_conflict"] for d in drafts)
                     else "pending_confirmation" if any(d["pending_confirmation"] for d in drafts)
                     else "draft_saved" if drafts else "not_started")
            pending.append({"material_id": material.id, "title": material.title,
                            "work_status": material.work_status, "processing_state": state,
                            "missing_fields": material.missing_fields(), "drafts": drafts})
        return {"pending": pending, "unclassified": unclassified}

    def get_material(self, material_id: str) -> dict:
        mat = self.materials.get(material_id)
        if mat is None:
            return {"error": "not_found", "material_id": material_id, "missing_fields": ["title", "license", "disclaimer"]}
        return {
            "id": mat.id, "title": mat.title, "type": mat.type,
            "duration_seconds": mat.duration_seconds, "format": mat.format,
            "copyright_license": mat.license, "license": mat.license,
            "owner": mat.owner, "sensitive_flags": mat.sensitive_flags,
            "disclaimer": mat.disclaimer, "missing_fields": mat.missing_fields(),
        }

    def check_rules(self, material_id: str) -> dict:
        mat = self.materials.get(material_id)
        if mat is None:
            return {"error": "not_found", "material_id": material_id, "risks": []}
        risks = []
        for rule in self.rules:
            check = rule.get("check")
            hit = False
            if check == "missing_license" and not mat.license:
                hit = True
            elif check == "unlicensed" and mat.license in ("未授权转载", "无授权"):
                hit = True
            elif check == "sensitive_content" and mat.sensitive_flags:
                hit = True
            elif check == "missing_disclaimer" and not mat.disclaimer:
                hit = True
            elif check == "format_mismatch" and mat.type == "video" and mat.format != "mp4":
                hit = True
            elif check == "missing_title" and not mat.title:
                hit = True
            if hit:
                risks.append({"rule_id": rule.get("rule_id"), "severity": rule.get("severity"),
                              "reason": rule.get("reason")})
        return {"material_id": material_id, "risks": risks,
                "missing_fields": mat.missing_fields()}

    def query_schedule(self, slot: str) -> dict:
        if not _SLOT_RE.match(slot):
            return {"error": "invalid_params: slot 应为 HH:MM 格式", "slot": slot}
        records = self.draft_store._read_all()
        def occupant_for(candidate):
            entry = self.schedule.get(candidate)
            if entry and entry.get("occupied"):
                return entry.get("material_id") or "已有排期"
            for record in records:
                if record.get("suggested_slot") == candidate and not self._own_draft(record):
                    return record.get("material_id") or "已有草稿"
            return None

        occupant = occupant_for(slot)
        occupied = occupant is not None
        # 附近空闲时段：从请求时段之后逐小时扫描，最多 3 个（供模型从观察数据中选择）。
        hour, minute = int(slot[:2]), int(slot[3:])
        free_slots = []
        for step in range(1, 13):
            h = hour + step
            if h > 23:
                break
            candidate = f"{h:02d}:{minute:02d}"
            if occupant_for(candidate) is None:
                free_slots.append(candidate)
            if len(free_slots) >= 3:
                break
        return {"slot": slot, "occupied": occupied, "occupant_material_id": occupant,
                "nearby_free_slots": free_slots}

    def supplement_info(self, material_id: str) -> dict:
        mat = self.materials.get(material_id)
        if mat is None:
            return {"error": "not_found", "material_id": material_id, "still_missing": ["title", "license", "disclaimer"]}
        supplemented = dict(mat.supplement or {})
        # 补查成功时，把补回的字段写回内存中的素材记录，供后续规则检查使用。
        # M05 的 disclaimer 由此补回；M02 的 supplement 为空，仍缺失。
        if supplemented.get("disclaimer") and not mat.disclaimer:
            mat.disclaimer = supplemented["disclaimer"]
        if supplemented.get("title") and not mat.title:
            mat.title = supplemented["title"]
        if supplemented.get("license") and not mat.license:
            mat.license = supplemented["license"]
        still_missing = mat.missing_fields()
        return {"material_id": material_id, "supplemented_fields": supplemented,
                "still_missing": still_missing, "resolved": not still_missing}

    def save_draft(self, material_id: str, requested_slot: str, suggested_slot: str,
                   pending_confirmation: bool = False) -> dict:
        # 检查写入前提，不能依赖模型的自述或事后的结果护栏。
        if not self.request or (material_id, requested_slot) != (self.request.material_id, self.request.requested_slot):
            return {"error": "guard_rejected", "detail": "素材或请求时段与当前请求不一致"}
        if not _SLOT_RE.fullmatch(requested_slot) or not _SLOT_RE.fullmatch(suggested_slot):
            return {"error": "guard_rejected", "detail": "时段格式无效"}
        if suggested_slot != requested_slot and not pending_confirmation:
            return {"error": "guard_rejected", "detail": "改变请求时段必须标记待确认"}
        material_read = any(name == "get_material" and args.get("material_id") == material_id
                            and not result.get("error") for name, args, result in self.observations)
        rules_checked = any(name == "check_rules" and args.get("material_id") == material_id
                            and not result.get("error") for name, args, result in self.observations)
        if not material_read or not rules_checked:
            return {"error": "guard_rejected", "detail": "保存前须读取素材并检查规则"}
        risks = self.check_rules(material_id)
        if risks.get("error") or any(r.get("severity") == "block" for r in risks.get("risks", [])):
            return {"error": "guard_rejected", "detail": "素材不存在或存在阻塞级规则风险"}
        records = self.draft_store._read_all()
        existing = next((r for r in records if self._own_draft(r)), None)
        if existing and existing.get("suggested_slot") != suggested_slot:
            return {"error": "existing_draft_conflict", "detail": "已有草稿的时段与当前建议不同，需人工处理",
                    "existing_draft": {k: existing.get(k) for k in ("draft_id", "suggested_slot", "pending_confirmation")}}
        observed_free = any(name == "query_schedule" and args.get("slot") == suggested_slot
                            and result.get("occupied") is False and not result.get("error")
                            for name, args, result in self.observations)
        if not observed_free or self.query_schedule(suggested_slot).get("occupied"):
            return {"error": "guard_rejected", "detail": "建议时段未验证为空闲或已被占用"}
        return self.draft_store.save(material_id, requested_slot, suggested_slot,
                                     bool(pending_confirmation))
