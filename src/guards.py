"""硬性护栏：全部在代码中强制执行，位于模型决策之外。

护栏不替代模型决策，只否决/纠正越权结果：
- 绝不声称已发布（published 一律降级/拒绝）；
- 改变硬性发布时间要求时，必须 pending_confirmation=true；
- 阻塞风险下不得保存草稿；
- 建议时段必须经 query_schedule 观察为空闲；
- 保存失败必须明确返回 save_failed。
"""

from __future__ import annotations


def assert_no_publish_claim(payload: dict) -> list:
    """检查模型终态是否声称已发布；返回纠正记录（空表示无问题）。"""
    corrections = []
    text = str(payload).lower()
    claimed = payload.get("status") == "published" or payload.get("review_status") == "published" \
        or payload.get("published") is True or "已发布" in str(payload.get("status", "")) \
        or "已发布" in str(payload.get("review_status", ""))
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
    observed_free: set[str] = set()
    draft_obs: dict | None = None
    save_failed = False
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        for risk in obs.get("risks") or []:
            if risk.get("severity") == "block":
                block_reasons.append(risk.get("reason", ""))
        if "occupied" in obs and "slot" in obs and obs.get("occupied") is False:
            observed_free.add(obs["slot"])
        if obs.get("draft_saved"):
            draft_obs = obs
        if obs.get("error") == "save_failed":
            save_failed = True

    corrections.extend(assert_no_publish_claim(payload))
    claimed_published = bool(corrections) and any("publish claim" in c for c in corrections)

    suggested = payload.get("suggested_slot")
    risk_reasons = payload.get("risk_reasons") or block_reasons
    pending = bool(payload.get("pending_confirmation", False))
    draft_saved = bool(payload.get("draft_saved", False))
    draft_id = payload.get("draft_id")
    status = payload.get("status", "draft_saved")

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

    # 3. 保存失败：明确返回 save_failed，无 draft_id。
    if save_failed and not draft_obs:
        status = "save_failed"
        draft_saved = False
        draft_id = None

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
        # 以工具返回为准：draft_id / duplicate 不由模型空口决定。
        draft_id = draft_obs.get("draft_id") if status == "draft_saved" else None
        draft_saved = status == "draft_saved"
        pending = bool(draft_obs.get("pending_confirmation", False)) or pending
    # 工具记录也不得悄悄抹掉待确认标记：时段被改就必须待确认。
    if suggested and suggested != requested_slot and status == "draft_saved" and not pending:
        corrections.extend(assert_hard_requirement_not_silently_changed(
            {"suggested_slot": suggested, "pending_confirmation": False}, requested_slot))
        pending = True
    duplicate = bool(draft_obs.get("duplicate", False)) if draft_obs else bool(payload.get("duplicate", False))

    review_status = payload.get("review_status") or status
    if status == "blocked":
        review_status = "blocked"
    elif status == "save_failed":
        review_status = payload.get("review_status") or "needs_confirmation"
    elif claimed_published:
        review_status = "draft_saved" if status == "draft_saved" else "blocked"

    return {
        "material_id": material_id,
        "requested_slot": requested_slot,
        "suggested_slot": suggested if status in ("draft_saved", "save_failed") else (suggested if status == "blocked" else None),
        "status": status,
        "review_status": review_status,
        "risk_reasons": risk_reasons,
        "pending_confirmation": pending if status == "draft_saved" else (pending if status == "save_failed" else False),
        "draft_saved": draft_saved,
        "draft_id": draft_id,
        "duplicate": duplicate,
        "published": False,
        "reason": payload.get("reason", ""),
        "guard_corrections": corrections,
    }
