"""Pending list and controlled final output regression tests."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.cli import main
from src.guards import assemble_result
from src.tools import DraftStore, Tools


class TestPendingEntry(unittest.TestCase):
    def test_explicit_pending_and_unclassified_drafts_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftStore(Path(tmp) / "drafts.json")
            tools = Tools(draft_store=store)
            tools.materials["M04"].work_status = "completed"
            tools.materials["M02"].work_status = "unspecified"
            store.save("M01", "18:00", "19:00", True)
            result = tools.list_pending_materials()
            by_id = {item["material_id"]: item for item in result["pending"]}
            self.assertNotIn("M04", by_id)
            self.assertNotIn("M02", by_id)
            self.assertIn({"material_id": "M02", "work_status": "unspecified"}, result["unclassified"])
            self.assertEqual(by_id["M01"]["processing_state"], "pending_confirmation")
            self.assertEqual(by_id["M03"]["processing_state"], "not_started")
            self.assertTrue(by_id["M01"]["drafts"][0]["pending_confirmation"])
            tools.schedule["19:00"] = {"occupied": True, "material_id": "OTHER"}
            by_id = {item["material_id"]: item for item in tools.list_pending_materials()["pending"]}
            self.assertEqual(by_id["M01"]["processing_state"], "draft_conflict")
            self.assertTrue(by_id["M01"]["drafts"][0]["slot_conflict"])

    def test_list_cli_needs_no_model_and_returns_json(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--list-pending", "--draft-store", str(Path(tmp) / "drafts.json")])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual({row["material_id"] for row in result["pending"]},
                             {"M01", "M02", "M03", "M04", "M05", "M06"})
            self.assertEqual(result["unclassified"], [])

    def test_list_cli_reports_corrupt_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drafts.json"
            path.write_text("not json", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--list-pending", "--draft-store", str(path)]), 2)


class TestControlledOutput(unittest.TestCase):
    def test_missing_material_reports_observed_reason(self):
        result = assemble_result({"status": "blocked", "reason": "内容发布成功"},
                                 [{"error": "not_found", "material_id": "M99"}], "17:00", "M99")
        self.assertEqual(result["status"], "blocked")
        self.assertIn("素材不存在", result["reason"])
        self.assertIn("素材不存在或无法读取", result["risk_reasons"])

    def test_model_claims_and_unknown_status_never_appear_in_final_text(self):
        for claim in ("内容发布成功", "内容已经上线", "内容已上架", "was made public"):
            with self.subTest(claim=claim):
                result = assemble_result({"status": "blocked", "review_status": claim,
                                          "reason": claim, "risk_reasons": [claim]}, [], "17:00", "M04")
                self.assertNotIn(claim, json.dumps(result, ensure_ascii=False))
                self.assertFalse(result["published"])
                self.assertFalse(result["draft_saved"])

    def test_saved_result_uses_observed_risk_and_draft_not_model_text(self):
        observations = [{"risks": [{"severity": "warn", "reason": "格式需复核"}]},
                        {"slot": "17:00", "occupied": False},
                        {"draft_saved": True, "draft_id": "D-test", "suggested_slot": "17:00",
                         "pending_confirmation": False}]
        result = assemble_result({"status": "draft_saved", "reason": "内容发布成功",
                                  "risk_reasons": ["模型伪造的风险"], "suggested_slot": "17:00"},
                                 observations, "17:00", "M04")
        self.assertTrue(result["draft_saved"])
        self.assertEqual(result["risk_reasons"], ["格式需复核"])
        self.assertNotIn("发布成功", result["reason"])


if __name__ == "__main__":
    unittest.main()
