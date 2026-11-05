"""Run the changed-occupancy duplicate scenario with a real model twice."""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from run_real_examples import ROOT, write_json
from src.agent import run
from src.cli import _load_dotenv
from src.llm import LLMError, OpenAICompatibleClient
from src.models import AgentRequest
from src.tools import DraftStore, Tools


def main() -> int:
    _load_dotenv()
    try:
        llm = OpenAICompatibleClient(timeout=60)
    except LLMError as exc:
        print(f"模型配置不完整：{exc}", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_root = ROOT / "examples" / "real-llm" / stamp / "07-changed-schedule"
    output_root.mkdir(parents=True, exist_ok=False)
    runs = []
    with tempfile.TemporaryDirectory() as temporary:
        store = DraftStore(Path(temporary) / "drafts.json")
        request = AgentRequest("M01", "18:00")
        changed_slot = None
        for index in (1, 2):
            if index == 2 and not changed_slot:
                print("首次运行未生成有效草稿，无法进行变更占用场景；已保留首次记录。", file=sys.stderr)
                return 1
            run_dir = output_root / f"run{index}"
            run_dir.mkdir()
            tools = Tools(draft_store=store)
            if changed_slot:
                tools.schedule[changed_slot] = {"occupied": True, "material_id": "OTHER"}
            write_json(run_dir / "input.json", {"material_id": "M01", "requested_slot": "18:00",
                       "changed_occupied_slot": changed_slot, "occupant_after_change": "OTHER" if changed_slot else None})
            attempts_before, responses_before = llm.call_attempts, len(llm.response_models)
            result, trace = run(request, llm, tools, max_steps=10)
            records = store._read_all()
            responses = llm.response_models[responses_before:]
            write_json(run_dir / "output.json", result)
            write_json(run_dir / "trace.json", trace)
            write_json(run_dir / "drafts_after.json", records)
            write_json(run_dir / "metadata.json", {
                "mode": "real", "started_by": "scripts/run_real_changed_schedule.py",
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "api_host": urlsplit(llm.base_url).hostname, "model_requested": llm.model,
                "models_reported_by_api": responses, "model_call_attempts": llm.call_attempts - attempts_before,
                "valid_model_responses": len(responses), "max_steps": 10,
                "schedule_change": {"slot": changed_slot, "occupied_by": "OTHER"} if changed_slot else None,
            })
            runs.append((result, records, len(responses)))
            print(f"run{index}: {result['status']}, responses={len(responses)}", flush=True)
            if index == 1 and result.get("draft_saved") and len(records) == 1:
                changed_slot = records[0].get("suggested_slot")

    first, second = runs
    old = second[0].get("existing_draft") or {}
    checks = {
        "first_draft_saved": first[0]["status"] == "draft_saved" and bool(changed_slot),
        "old_draft_preserved": len(first[1]) == len(second[1]) == 1
                               and first[1][0] == second[1][0],
        "stale_draft_reported": second[0]["status"] == "blocked" and not second[0]["draft_saved"]
                                and old.get("draft_id") == first[0].get("draft_id")
                                and old.get("suggested_slot") == changed_slot,
        "real_responses_and_no_publish": all(count > 0 and not result["published"]
                                              for result, _, count in runs),
    }
    write_json(output_root / "acceptance.json", {"checks": checks, "all_passed": all(checks.values())})
    print(f"记录目录：{output_root}")
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
