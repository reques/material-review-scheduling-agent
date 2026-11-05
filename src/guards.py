"""硬性护栏：全部在代码中强制执行，位于模型决策之外。

护栏不替代模型决策，只否决/纠正越权结果：
- 绝不声称已发布（published 一律降级/拒绝）；
- 改变硬性发布时间要求时，必须 pending_confirmation=true；
- 阻塞风险下不得保存草稿；
- 建议时段必须经 query_schedule 观察为空闲；
- 保存失败必须明确返回 save_failed。
"""

from __future__ import annotations

import re

_PUBLISH_CLAIM = re.compile(
    r"已(?:经)?(?:真实)?(?:发布|上线|上架|播出)|(?:发布|上线|上架|播出)(?:已)?(?:成功|完成|完毕|了)|"
    r"\b(?:published|launched|posted|went\s+live|successfully\s+published)\b", re.IGNORECASE)


def assert_no_publish_claim(payload: dict) -> list:
    """检查模型终态是否声称已发布；返回纠正记录（空表示无问题）。"""
    corrections = []
    claimed = payload.get("published") is True or any(
        _PUBLISH_CLAIM.search(str(payload.get(key, "")))
        for key in ("status", "review_status", "reason", "risk_reasons"))
    if claimed:
        corrections.append("publish claim rejected: 仅可保存草稿，不得声称已发布")
    return corrections


def assert_hard_requirement_not_silently_changed(payload: dict, requested_slot: str) -> list:
    """建议时段 != 请求时段时，必须标记待确认；否则返回纠正记录。"""
    corrections = []
    suggested = payload.get("suggested_slot")
    if suggested and suggested != requested_slot and not payload.get("pending_confirmation"):
        corrections.append(
            "hard requirement changed without confirmation flag: "
            f"建议时段 {suggested} != 请求时段 {requested_slot}，已强制 pending_confirmation=true")
    return corrections


def assemble_result(finish_payload: dict, observations: list, requested_slot: str,
                    material_id: str) -> dict:
    """把模型 finish 负载与工具观察交叉核对，组装最终结果。

    observations: 按顺序的工具观察 dict 列表（仅真实工具返回）。
    """
    payload = dict(finish_payload or {})
    corrections: list[str] = []

    # 观察汇总
    block_reasons: list[str] = []
    observed_risks: list[str] = []
    observed_free: set[str] = set()
    draft_obs: dict | None = None
    save_failed = False
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        for risk in obs.get("risks") or []:
            reason = str(risk.get("reason", ""))
            if reason:
                observed_risks.append(reason if not _PUBLISH_CLAIM.search(reason) else "规则检查发现风险，请查看运行记录")
            if risk.get("severity") == "block":
                block_reasons.append(reason if not _PUBLISH_CLAIM.search(reason) else "规则检查发现阻塞风险，请查看运行记录")
        if "occupied" in obs and "slot" in obs and obs.get("occupied") is False:
            observed_free.add(obs["slot"])
        if obs.get("draft_saved"):
            draft_obs = obs
        if obs.get("error") == "save_failed":
            save_failed = True

    corrections.extend(assert_no_publish_claim(payload))
    claimed_published = bool(corrections) and any("publish claim" in c for c in corrections)

    suggested = payload.get("suggested_slot")
    # 最终结果不透传模型编造的自由文本；规则风险以工具观察为准。
    risk_reasons = observed_risks
    pending = bool(payload.get("pending_confirmation", False))
    draft_saved = bool(payload.get("draft_saved", False))
    draft_id = payload.get("draft_id")
    status = payload.get("status", "draft_saved")
    if status in ("draft", "saved", "success") and draft_obs:
        status = "draft_saved"
        corrections.append("normalized model status: 使用保存工具观察统一为 draft_saved")
    if status not in ("draft_saved", "blocked", "save_failed", "incomplete", "published"):
        status = "incomplete"
        corrections.append("unknown model status: 置为 incomplete")

    # 1. 已发布声称：降级为“有草稿则 draft_saved，否则 blocked”，永不透传 published。
    if claimed_published:
        if draft_obs:
            status = "draft_saved"
        else:
            status = "blocked"
            draft_saved = False
            draft_id = None

    # 2. 阻塞风险：不得保存草稿。
    if block_reasons:
        if draft_saved or draft_obs:
            corrections.append("blocked by rule risk: 阻塞风险下草稿结果无效，已置为 blocked")
        status = "blocked"
        draft_saved = False
        draft_id = None
        risk_reasons = block_reasons

    # 3. 保存失败和已有草稿冲突由工具观察决定，不能由模型掩盖。
    if save_failed and not draft_obs:
        status = "save_failed"
        draft_saved = False
        draft_id = None

    conflict_obs = next((o for o in reversed(observations)
                         if isinstance(o, dict) and o.get("error") == "existing_draft_conflict"), None)
    rejected_obs = next((o for o in reversed(observations)
                         if isinstance(o, dict) and o.get("error") == "guard_rejected"), None)
    not_found = any(isinstance(o, dict) and o.get("error") == "not_found"
                    and o.get("material_id") == material_id for o in observations)
    requested_occupied = any(isinstance(o, dict) and o.get("slot") == requested_slot
                             and o.get("occupied") is True for o in observations)
    if conflict_obs and not draft_obs:
        status = "blocked"
        if not risk_reasons:
            risk_reasons = ["已有草稿与当前建议时段不一致"]
    elif rejected_obs and not draft_obs and not save_failed:
        status = "blocked"
    if not_found and not draft_obs:
        status = "blocked"
        risk_reasons = ["素材不存在或无法读取"]
    elif status == "blocked" and requested_occupied and not risk_reasons:
        risk_reasons = ["请求时段已被占用"]

    # 4. 建议时段必须被观察为空闲（请求时段本身被占时，替代时段需单独验证过）。
    if status == "draft_saved" and suggested and suggested not in observed_free:
        corrections.append(
            f"suggested slot {suggested} was not observed free via query_schedule; 结果置为 incomplete")
        status = "incomplete"
        draft_saved = False
        draft_id = None

    # 5. 草稿声称必须有真实的 save_draft 观察作证。
    if status == "draft_saved" and not draft_obs:
        corrections.append("no save_draft observation: 草稿声称无工具记录，置为 incomplete")
        status = "incomplete"
        draft_saved = False
        draft_id = None

    # 6. 硬性要求变更必须待确认。
    if suggested and suggested != requested_slot and not pending:
        corrections.extend(assert_hard_requirement_not_silently_changed(payload, requested_slot))
        pending = True

    if draft_obs:
        # 保存是已经发生的副作用，即使后续未完成也必须如实报告。
        draft_id = draft_obs.get("draft_id")
        draft_saved = True
        suggested = draft_obs.get("suggested_slot")
        pending = bool(draft_obs.get("pending_confirmation", False))
    else:
        # 无论模型给出何种终态，都不能虚构保存成功或草稿 ID。
        draft_saved = False
        draft_id = None
    # 工具记录也不得悄悄抹掉待确认标记：时段被改就必须待确认。
    if suggested and suggested != requested_slot and status == "draft_saved" and not pending:
        corrections.extend(assert_hard_requirement_not_silently_changed(
            {"suggested_slot": suggested, "pending_confirmation": False}, requested_slot))
        pending = True
    duplicate = bool(draft_obs.get("duplicate", False)) if draft_obs else False

    review_status = payload.get("review_status") or status
    if review_status not in ("passed", "approved", "blocked", "rejected", "needs_confirmation",
                              "draft_saved", "incomplete", "save_failed"):
        review_status = status
    if status == "blocked":
        review_status = "blocked"
    elif status == "save_failed":
        review_status = payload.get("review_status") or "needs_confirmation"
    elif status == "incomplete":
        review_status = "incomplete"
    elif claimed_published:
        review_status = "draft_saved" if status == "draft_saved" else "blocked"

    # 输出说明由工具观察与状态生成。模型原始说法仍在 Trace 中供审计。
    if conflict_obs and not draft_obs:
        reason = "已有草稿的时段与当前建议不同，请先人工处理已有草稿。"
    elif save_failed and not draft_obs:
        reason = "保存草稿失败，请检查存储后重试。"
    elif rejected_obs and not draft_obs:
        reason = "草稿未保存：" + str(rejected_obs.get("detail", "保存条件未满足"))
    elif status == "draft_saved" and draft_obs:
        reason = "草稿已保存，建议时段需要用户确认。" if pending else "草稿已保存。"
    elif status == "incomplete":
        prefix = "达到步数上限，任务未完成。" if str(payload.get("reason", "")).startswith("达到步数上限") else "任务未完成。"
        reason = prefix + ("草稿已保存，请核查后续处理。" if draft_obs else "未观察到草稿保存成功。")
    elif draft_obs:
        reason = "处理未正常结束，但草稿实际已保存，请核查草稿及后续处理。"
    elif block_reasons:
        reason = "素材存在阻塞级规则风险，请处理后重新提交。"
    elif not_found:
        reason = "素材不存在或无法读取，请核对素材 ID。"
    elif status == "blocked" and requested_occupied:
        reason = "请求时段已被占用，无法形成有效排期。"
    else:
        reason = "无法完成审核或排期，请查看运行记录并处理。"

    return {
        "material_id": material_id,
        "requested_slot": requested_slot,
        "suggested_slot": suggested if draft_saved or status in ("draft_saved", "save_failed", "blocked") else None,
        "status": status,
        "review_status": review_status,
        "risk_reasons": risk_reasons,
        "pending_confirmation": pending if draft_saved or status == "save_failed" else False,
        "draft_saved": draft_saved,
        "draft_id": draft_id,
        "duplicate": duplicate,
        "published": False,
        "reason": reason,
        "guard_corrections": corrections,
        **({"existing_draft": conflict_obs["existing_draft"]} if conflict_obs else {}),
    }
