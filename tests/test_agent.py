"""测试：全部使用 unittest + MockLLM/桩 LLM，无网络、无真实密钥。"""

import json
import tempfile
import unittest
from pathlib import Path

from src.agent import run
from src.guards import assemble_result, assert_hard_requirement_not_silently_changed, assert_no_publish_claim
from src.llm import MockLLM, extract_json_object, LLMError
from src.models import AgentRequest
from src.tools import DraftStore, Tools


def make_tools(tmpdir, fail_save=False):
    store = DraftStore(Path(tmpdir) / "drafts.json", fail_save=fail_save)
    return Tools(draft_store=store), store


def run_case(material_id, slot, tmpdir, fail_save=False, llm=None):
    tools, store = make_tools(tmpdir, fail_save=fail_save)
    result, trace = run(AgentRequest(material_id, slot), llm or MockLLM(), tools, max_steps=8)
    return result, trace, store


class TestAgentPaths(unittest.TestCase):
    def test_agent_normal(self):
        """正常排期：M04 请求空闲时段 17:00，保存草稿，不待确认，不声称已发布。"""
        with tempfile.TemporaryDirectory() as tmp:
            result, trace, store = run_case("M04", "17:00", tmp)
            self.assertEqual(result["status"], "draft_saved")
            self.assertEqual(result["suggested_slot"], "17:00")
            self.assertFalse(result["pending_confirmation"])
            self.assertTrue(result["draft_saved"])
            self.assertIsNotNone(result["draft_id"])
            self.assertFalse(result["published"])
            self.assertEqual([s["action"] for s in trace],
                             ["get_material", "check_rules", "query_schedule", "save_draft", "finish"])

    def test_missing_info(self):
        """信息缺失：M02 补查后仍缺失（标题+授权），阻塞，不保存草稿。"""
        with tempfile.TemporaryDirectory() as tmp:
            result, trace, store = run_case("M02", "17:00", tmp)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["draft_saved"])
            self.assertIsNone(result["draft_id"])
            actions = [s["action"] for s in trace]
            self.assertIn("supplement_info", actions)
            self.assertNotIn("save_draft", actions)
            self.assertTrue(any("缺少版权" in r or "标题" in r for r in result["risk_reasons"]))

    def test_missing_info_supplement_resolves(self):
        """补查分支：M05 缺失免责声明，补查返回声明后继续并保存草稿。"""
        with tempfile.TemporaryDirectory() as tmp:
            result, trace, store = run_case("M05", "17:00", tmp)
            self.assertEqual(result["status"], "draft_saved")
            self.assertTrue(result["draft_saved"])
            self.assertIn("supplement_info", [s["action"] for s in trace])

    def test_rule_risk(self):
        """规则风险：M03 未授权+敏感标记，阻塞，不保存草稿，不查询排期后保存。"""
        with tempfile.TemporaryDirectory() as tmp:
            result, trace, store = run_case("M03", "17:00", tmp)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["draft_saved"])
            self.assertNotIn("save_draft", [s["action"] for s in trace])
            self.assertEqual(len(result["risk_reasons"]), 2)

    def test_slot_conflict(self):
        """时段冲突：M01 请求 18:00（被占），建议观察到的 19:00，待确认，仅草稿。"""
        with tempfile.TemporaryDirectory() as tmp:
            result, trace, store = run_case("M01", "18:00", tmp)
            self.assertEqual(result["status"], "draft_saved")
            self.assertEqual(result["requested_slot"], "18:00")
            self.assertEqual(result["suggested_slot"], "19:00")
            self.assertTrue(result["pending_confirmation"])
            self.assertTrue(result["draft_saved"])
            self.assertFalse(result["published"])
            # Trace 必须显示：18:00 被占 -> 19:00 被验证为空闲 -> 保存草稿。
            summaries = " ".join(s["tool_result_summary"] for s in trace)
            self.assertIn('"slot": "18:00"', summaries)
            self.assertIn('"occupied": true', summaries)
            self.assertIn('"slot": "19:00"', summaries)
            self.assertIn('"occupied": false', summaries)

    def test_duplicate(self):
        """重复提交：同一请求两次，只产生一份草稿，同一 draft_id，第二次 duplicate=true。"""
        with tempfile.TemporaryDirectory() as tmp:
            tools, store = make_tools(tmp)
            r1, _ = run(AgentRequest("M06", "20:00"), MockLLM(), tools, max_steps=8)
            r2, _ = run(AgentRequest("M06", "20:00"), MockLLM(), tools, max_steps=8)
            self.assertEqual(r1["draft_id"], r2["draft_id"])
            self.assertTrue(r2["duplicate"])
            self.assertEqual(store.count(), 1)

    def test_save_failure(self):
        """保存失败：失败存储下明确返回 save_failed，无 draft_id，不声称已保存。"""
        with tempfile.TemporaryDirectory() as tmp:
            result, trace, store = run_case("M06", "20:00", tmp, fail_save=True)
            self.assertEqual(result["status"], "save_failed")
            self.assertFalse(result["draft_saved"])
            self.assertIsNone(result["draft_id"])
            self.assertEqual(store.count(), 0)

    def test_step_cap(self):
        """步数上限：永不 finish 的桩 LLM -> incomplete，明确原因，不声称草稿。"""
        class NeverFinishes:
            def decide(self, prompt):
                return {"thought": "stub", "action": "get_material",
                        "action_input": {"material_id": "M04"}}

        with tempfile.TemporaryDirectory() as tmp:
            tools, store = make_tools(tmp)
            result, trace = run(AgentRequest("M04", "17:00"), NeverFinishes(), tools, max_steps=3)
            self.assertEqual(result["status"], "incomplete")
            self.assertFalse(result["draft_saved"])
            self.assertIsNone(result["draft_id"])
            self.assertIn("步数上限", result["reason"])
            self.assertEqual(len(trace), 3)


class TestGuards(unittest.TestCase):
    def test_guards_publish_claim(self):
        """护栏：模型声称 published 时必须被降级/拒绝，永不透传。"""
        payload = {"status": "published", "review_status": "published", "published": True,
                   "suggested_slot": "17:00", "pending_confirmation": False,
                   "draft_saved": True, "draft_id": "D-fake", "risk_reasons": []}
        observations = [{"slot": "17:00", "occupied": False}]
        result = assemble_result(payload, observations, "17:00", "M04")
        self.assertNotEqual(result["status"], "published")
        self.assertFalse(result["published"])
        self.assertTrue(result["guard_corrections"])
        # 无真实 save_draft 观察时，不得保留虚假 draft_id。
        self.assertIsNone(result["draft_id"])

    def test_guards_hard_requirement_flag(self):
        corrections = assert_hard_requirement_not_silently_changed(
            {"suggested_slot": "19:00", "pending_confirmation": False}, "18:00")
        self.assertTrue(corrections)
        self.assertFalse(assert_no_publish_claim({"status": "draft_saved"}))
        # assemble_result 应强制 pending_confirmation=true。
        payload = {"status": "draft_saved", "suggested_slot": "19:00",
                   "pending_confirmation": False, "draft_saved": True,
                   "risk_reasons": []}
        observations = [{"slot": "18:00", "occupied": True, "nearby_free_slots": ["19:00"]},
                        {"slot": "19:00", "occupied": False},
                        {"draft_saved": True, "draft_id": "D-x", "suggested_slot": "19:00",
                         "pending_confirmation": False}]
        result = assemble_result(payload, observations, "18:00", "M01")
        self.assertTrue(result["pending_confirmation"])
        self.assertTrue(result["guard_corrections"])

    def test_guards_blocked_risk_no_draft(self):
        payload = {"status": "draft_saved", "suggested_slot": "17:00",
                   "draft_saved": True, "draft_id": "D-x", "risk_reasons": []}
        observations = [{"risks": [{"rule_id": "R01", "severity": "block", "reason": "缺少版权"}]},
                        {"slot": "17:00", "occupied": False}]
        result = assemble_result(payload, observations, "17:00", "M03")
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["draft_saved"])
        self.assertIsNone(result["draft_id"])


class TestToolValidation(unittest.TestCase):
    def test_tool_validation(self):
        """未知工具/错误参数返回 error 观察，不抛异常；Agent 循环可继续。"""
        with tempfile.TemporaryDirectory() as tmp:
            tools, _ = make_tools(tmp)
            unknown = tools.dispatch("no_such_tool", {})
            self.assertIn("error", unknown)
            bad = tools.dispatch("get_material", {})
            self.assertIn("error", bad)
            bad_slot = tools.dispatch("query_schedule", {"slot": "not-a-time"})
            self.assertIn("error", bad_slot)
            not_found = tools.dispatch("get_material", {"material_id": "M99"})
            self.assertEqual(not_found["error"], "not_found")

    def test_llm_json_extraction(self):
        obj = extract_json_object('说明文字 {"action": "finish", "thought": "x"} 尾巴')
        self.assertEqual(obj["action"], "finish")
        with self.assertRaises(LLMError):
            extract_json_object("没有 JSON")


if __name__ == "__main__":
    unittest.main()
