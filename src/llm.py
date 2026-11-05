"""LLM 接口：真实客户端（OpenAI 兼容 HTTP，urllib）与离线 Mock。

边界声明（诚实标注）：
- MockLLM 只验证流程：它读取提示词中的工具观察结果，用启发式规则
  选择下一步动作，**不证明真实模型的决策质量**。
- 真实客户端需要 LLM_API_KEY 等环境变量；无密钥时不得冒充真实模型。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMError(Exception):
    """LLM 调用或输出解析失败。Agent 循环会把它转为观察结果并重试（在步数上限内），而不是崩溃。"""


def extract_json_object(text: str) -> dict:
    """从模型回复中提取第一个 JSON 对象。

    允许回复前后有少量说明文字；找不到可解析的 JSON 对象时抛 LLMError。
    """
    if not text or not text.strip():
        raise LLMError("empty LLM response")
    start = text.find("{")
    if start == -1:
        raise LLMError("no JSON object in LLM response")
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise LLMError(f"unparseable LLM JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise LLMError("LLM response JSON is not an object")
    return obj


class LLMClient:
    """LLM 决策接口：decide(prompt) -> {"thought": ..., "action": ..., "action_input": ...}。"""

    def decide(self, prompt: str) -> dict:  # pragma: no cover - 由子类实现
        raise NotImplementedError


class OpenAICompatibleClient(LLMClient):
    """OpenAI 兼容的 /chat/completions 客户端（标准库 urllib，无第三方依赖）。"""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: int = 30):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", "deepseek-chat")
        self.timeout = timeout
        self.call_attempts = 0
        self.response_models: list[str] = []
        if not self.base_url:
            raise LLMError("LLM_BASE_URL 未配置，见 .env.example；或使用 --mock 离线模式")
        if not self.api_key:
            raise LLMError("LLM_API_KEY 未配置，见 .env.example；或使用 --mock 离线模式")

    def decide(self, prompt: str) -> dict:
        self.call_attempts += 1
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": (
                    "你是素材审核与发布排期 Agent。你只能返回一个 JSON 对象，"
                    "形如 {\"thought\": \"简短决策依据\", \"action\": \"工具名或 finish\", "
                    "\"action_input\": {...}}。不得声称已发布；只能保存草稿。"
                )},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMError(f"LLM HTTP error {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected LLM response shape: {str(payload)[:300]}") from exc
        obj = extract_json_object(content)
        if "action" not in obj:
            raise LLMError("LLM JSON missing 'action'")
        self.response_models.append(str(payload.get("model") or "未返回模型名称"))
        return obj


class MockLLM(LLMClient):
    """离线 Mock：仅用于验证流程的占位实现。

    它解析提示词中已有的 Action/Observation 历史，按观察结果选择下一步：
    缺失信息 -> 补查；阻塞风险 -> 结束（不保存草稿）；时段被占 -> 查询
    观察到的空闲时段并验证；时段空闲 -> 保存草稿。
    这些是写在代码里的启发式规则，不是真实模型的决策证据。
    """

    def decide(self, prompt: str) -> dict:
        import re

        # 从提示词中提取任务信息。
        m_id = re.search(r"Material ID:\s*(\S+)", prompt)
        m_slot = re.search(r"Requested slot:\s*(\S+)", prompt)
        material_id = m_id.group(1) if m_id else ""
        requested_slot = m_slot.group(1) if m_slot else ""

        # 解析历史：每一步的 Action 与 Observation（JSON）。
        actions: list[str] = []
        observations: list[dict] = []
        for line in prompt.splitlines():
            line = line.strip()
            if line.startswith("Action:"):
                actions.append(line[len("Action:"):].strip().split()[0])
            elif line.startswith("Observation:"):
                raw = line[len("Observation:"):].strip()
                try:
                    observations.append(json.loads(raw))
                except json.JSONDecodeError:
                    observations.append({"_unparsed": raw})

        def obs_for(action_name: str) -> dict | None:
            for act, obs in zip(actions, observations):
                if act == action_name:
                    return obs
            return None

        def last_obs() -> dict:
            return observations[-1] if observations else {}

        # 1. 先读素材。
        if "get_material" not in actions:
            return {"thought": "需要先读取素材元数据，确认是否存在与缺失字段。",
                    "action": "get_material", "action_input": {"material_id": material_id}}
        material_obs = obs_for("get_material") or {}
        if material_obs.get("error") == "not_found":
            return {"thought": "素材不存在，无法继续审核，结束并报告信息缺失。",
                    "action": "finish", "action_input": {
                        "status": "blocked", "review_status": "blocked",
                        "risk_reasons": ["素材不存在：信息缺失"],
                        "suggested_slot": None, "pending_confirmation": False,
                        "draft_saved": False, "draft_id": None,
                        "reason": "素材不存在，信息缺失"}}
        missing = material_obs.get("missing_fields") or []

        # 2. 有缺失字段时先补查，补查结果会改变下一步。
        if missing and "supplement_info" not in actions:
            return {"thought": f"素材缺失字段 {missing}，先补查再判断是否可继续。",
                    "action": "supplement_info", "action_input": {"material_id": material_id}}

        # 3. 规则检查。
        if "check_rules" not in actions:
            return {"thought": "读取与补查完成，执行规则检查以识别阻塞风险。",
                    "action": "check_rules", "action_input": {"material_id": material_id}}
        rules_obs = obs_for("check_rules") or {}
        risks = rules_obs.get("risks") or []
        blockers = [r for r in risks if r.get("severity") == "block"]
        if blockers:
            reasons = [r.get("reason", "") for r in blockers]
            return {"thought": "存在阻塞级规则风险，不得保存草稿，直接结束并报告阻塞。",
                    "action": "finish", "action_input": {
                        "status": "blocked", "review_status": "blocked",
                        "risk_reasons": reasons,
                        "suggested_slot": None, "pending_confirmation": False,
                        "draft_saved": False, "draft_id": None,
                        "reason": "阻塞级规则风险：" + "; ".join(reasons)}}
        warn_reasons = [r.get("reason", "") for r in risks if r.get("severity") == "warn"]

        # 3b. 已保存过草稿：直接按保存结果结束，不再重复保存。
        if "save_draft" in actions:
            draft_obs = last_obs()
            if draft_obs.get("error"):
                return {"thought": "保存草稿失败，必须明确返回 save_failed，不得声称已保存。",
                        "action": "finish", "action_input": {
                            "status": "save_failed", "review_status": "needs_confirmation",
                            "risk_reasons": warn_reasons,
                            "suggested_slot": None,
                            "pending_confirmation": False,
                            "draft_saved": False, "draft_id": None,
                            "reason": "保存草稿失败：" + str(draft_obs.get("error"))}}
            suggested_early = draft_obs.get("suggested_slot") or requested_slot
            return {"thought": "草稿已保存，汇总审核状态、风险与待确认项后结束。",
                    "action": "finish", "action_input": {
                        "status": "draft_saved", "review_status": "draft_saved",
                        "risk_reasons": warn_reasons,
                        "suggested_slot": suggested_early,
                        "pending_confirmation": bool(draft_obs.get("pending_confirmation", suggested_early != requested_slot)),
                        "draft_saved": True, "draft_id": draft_obs.get("draft_id"),
                        "duplicate": bool(draft_obs.get("duplicate", False)),
                        "reason": "草稿已保存，待确认后方可发布" if suggested_early != requested_slot else "草稿已保存"}}

        # 4. 查询请求时段。
        requested_obs = None
        for act, obs in zip(actions, observations):
            if act == "query_schedule" and obs.get("slot") == requested_slot:
                requested_obs = obs
        if requested_obs is None:
            return {"thought": "规则无阻塞风险，查询请求时段是否被占用。",
                    "action": "query_schedule", "action_input": {"slot": requested_slot}}

        if requested_obs.get("error"):
            return {"thought": "排期查询失败，无法安全保存草稿。", "action": "finish",
                    "action_input": {"status": "blocked", "review_status": "blocked",
                                     "risk_reasons": ["排期查询失败"], "draft_saved": False,
                                     "reason": "排期查询失败：" + str(requested_obs["error"])}}

        # 5. 时段被占：从观察到的空闲时段中选一个并先验证它确实空闲。
        #    只要已验证过一个空闲替代时段，就保存草稿，不再逐个验证其余时段。
        if requested_obs.get("occupied"):
            free_slots = requested_obs.get("nearby_free_slots") or []
            verified_free: list[str] = []
            for act, obs in zip(actions, observations):
                if act == "query_schedule" and obs.get("occupied") is False and obs.get("slot") != requested_slot:
                    verified_free.append(obs.get("slot"))
            if verified_free:
                alt = verified_free[0]
                return {"thought": f"已验证替代时段 {alt} 空闲，保存草稿并标记待确认（改变了硬性时间要求，需用户同意）。",
                        "action": "save_draft", "action_input": {
                            "material_id": material_id, "requested_slot": requested_slot,
                            "suggested_slot": alt, "pending_confirmation": True}}
            for candidate in free_slots:
                if candidate != requested_slot:
                    return {"thought": f"请求时段 {requested_slot} 被占用，观察到的空闲时段有 {free_slots}，先验证 {candidate} 是否空闲。",
                            "action": "query_schedule", "action_input": {"slot": candidate}}
            return {"thought": "请求时段被占用且未观察到可用替代时段，结束并报告冲突。",
                    "action": "finish", "action_input": {
                        "status": "blocked", "review_status": "blocked",
                        "risk_reasons": [f"请求时段 {requested_slot} 被占用且无可用替代时段"],
                        "suggested_slot": None, "pending_confirmation": False,
                        "draft_saved": False, "draft_id": None,
                        "reason": "时段冲突且无可用替代时段"}}

        # 6. 请求时段空闲：直接保存草稿。
        if "save_draft" not in actions:
            return {"thought": "请求时段空闲，保存草稿（仅草稿，不发布）。",
                    "action": "save_draft", "action_input": {
                        "material_id": material_id, "requested_slot": requested_slot,
                        "suggested_slot": requested_slot, "pending_confirmation": False}}

        # 7. 保存后：按保存结果结束。
        draft_obs = last_obs()
        if draft_obs.get("error"):
            return {"thought": "保存草稿失败，必须明确返回 save_failed，不得声称已保存。",
                    "action": "finish", "action_input": {
                        "status": "save_failed", "review_status": "needs_confirmation",
                        "risk_reasons": warn_reasons,
                        "suggested_slot": requested_slot if not requested_obs.get("occupied") else None,
                        "pending_confirmation": False,
                        "draft_saved": False, "draft_id": None,
                        "reason": "保存草稿失败：" + str(draft_obs.get("error"))}}
        suggested = draft_obs.get("suggested_slot") or requested_slot
        return {"thought": "草稿已保存，汇总审核状态、风险与待确认项后结束。",
                "action": "finish", "action_input": {
                    "status": "draft_saved", "review_status": "draft_saved",
                    "risk_reasons": warn_reasons,
                    "suggested_slot": suggested,
                    "pending_confirmation": bool(draft_obs.get("pending_confirmation", suggested != requested_slot)),
                    "draft_saved": True, "draft_id": draft_obs.get("draft_id"),
                    "duplicate": bool(draft_obs.get("duplicate", False)),
                    "reason": "草稿已保存，待确认后方可发布" if suggested != requested_slot else "草稿已保存"}}
