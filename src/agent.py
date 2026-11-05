"""ReAct 循环：每一步的决策都来自一次 LLM 调用。

流程：渲染提示词（系统指令 + 工具 Schema + 任务 + 历史）-> llm.decide()
-> 校验动作 -> 执行工具 -> 把观察结果写回历史 -> 下一步再调用模型。
保存工具在写入前检查安全条件；结果护栏在 finish / 步数上限时核对观察。
"""

from __future__ import annotations

import json

from .guards import assemble_result
from .llm import LLMError
from .models import AgentRequest
from .tools import TOOL_SCHEMAS, Tools


def render_prompt(request: AgentRequest, history: list) -> str:
    schema_lines = []
    for name, schema in TOOL_SCHEMAS.items():
        schema_lines.append(f"- {name}{json.dumps(schema['parameters'], ensure_ascii=False)}: {schema['description']}")
    lines = [
        "你是素材审核与发布排期 Agent。只保存草稿，绝不真实发布，也绝不声称已发布。",
        "未经用户同意，不得擅自改变硬性发布时间要求；如建议不同时段，必须标记待确认。",
        "每步只返回一个 JSON 对象：{\"thought\": \"简短决策依据\", \"action\": \"工具名或 finish\", \"action_input\": {...}}。",
        "action 为 finish 时，action_input 须包含 status、review_status、risk_reasons、",
        "suggested_slot、pending_confirmation、draft_saved、draft_id、reason。",
        "可用工具：",
        *schema_lines,
        f"Material ID: {request.material_id}",
        f"Requested slot: {request.requested_slot}",
        f"Request ID: {request.request_id or ''}",
        "History:",
    ]
    if not history:
        lines.append("(无历史)")
    for i, item in enumerate(history, 1):
        lines.append(f"Action: {item['action']} {json.dumps(item.get('action_input', {}), ensure_ascii=False)}")
        lines.append(f"Observation: {json.dumps(item.get('observation', {}), ensure_ascii=False)}")
    lines.append("请根据以上历史与观察结果，返回下一步的 JSON 决策。")
    return "\n".join(lines)


def _summarize(observation: dict) -> str:
    """Trace 用的工具返回摘要：JSON 截断，保证可序列化。"""
    text = json.dumps(observation, ensure_ascii=False)
    return text if len(text) <= 300 else text[:297] + "..."


def run(request: AgentRequest, llm, tools: Tools, max_steps: int = 8):
    """执行一次 ReAct 循环，返回 (result, trace)。trace 可 JSON 序列化。"""
    history: list[dict] = []
    observations: list[dict] = []
    trace: list[dict] = []
    tools.begin_request(request)

    for step in range(1, max_steps + 1):
        prompt = render_prompt(request, history)
        try:
            decision = llm.decide(prompt)
        except Exception as exc:  # LLMError 等：转为观察，步数上限内重试，不崩溃
            obs = {"error": "llm_error", "detail": str(exc)}
            history.append({"action": "llm_error", "action_input": {}, "observation": obs})
            trace.append({"step": step, "action": "llm_error", "action_input": {},
                          "tool_result_summary": _summarize(obs),
                          "decision_basis": "", "next": "retry within step cap"})
            continue
        if not isinstance(decision, dict) or not isinstance(decision.get("action"), str):
            obs = {"error": "invalid_decision", "detail": "模型决策缺少 action 字段"}
            history.append({"action": "invalid_decision", "action_input": {}, "observation": obs})
            trace.append({"step": step, "action": "invalid_decision", "action_input": {},
                          "tool_result_summary": _summarize(obs),
                          "decision_basis": "", "next": "retry within step cap"})
            continue

        thought = str(decision.get("thought", ""))[:200]
        action = decision["action"]
        action_input = decision.get("action_input") or {}

        if action == "finish":
            result = assemble_result(action_input if isinstance(action_input, dict) else {}, observations,
                                     request.requested_slot, request.material_id)
            trace.append({"step": step, "action": "finish", "action_input": action_input,
                          "tool_result_summary": "",
                          "decision_basis": thought, "next": "done"})
            return result, trace

        # 工具执行：未知工具/参数错误由 Tools.dispatch 返回 error 观察，循环继续。
        observation = tools.dispatch(action, action_input if isinstance(action_input, dict) else {})
        observations.append(observation)
        history.append({"action": action, "action_input": action_input, "observation": observation})
        trace.append({"step": step, "action": action, "action_input": action_input,
                      "tool_result_summary": _summarize(observation),
                      "decision_basis": thought, "next": "model decides next step from observation"})

    # 未完成与副作用分别报告：最后一步可能已经保存草稿。
    saved = next((obs for obs in reversed(observations) if obs.get("draft_saved")), None)
    result = assemble_result({"status": "incomplete", "review_status": "incomplete",
                              "reason": f"达到步数上限（max_steps={max_steps}）仍未完成；"
                                        + ("草稿已保存" if saved else "未观察到草稿保存成功")},
                             observations, request.requested_slot, request.material_id)
    result["guard_corrections"].append(f"step cap reached at max_steps={max_steps}")
    return result, trace
