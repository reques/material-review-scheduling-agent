"""Run the four remaining acceptance scenarios against the configured real model.

Each scenario has an isolated temporary store, except the duplicate case whose
two requests intentionally share one store. Stored observations are synthetic.
"""
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
    output_root = ROOT / "examples" / "real-llm" / stamp
    output_root.mkdir(parents=True, exist_ok=False)
    cases = [
        ("03-normal", "M04", "17:00", False, 1),
        ("04-rule-risk", "M03", "17:00", False, 1),
        ("05-duplicate", "M06", "20:00", False, 2),
        ("06-save-failure", "M06", "20:00", True, 1),
    ]
    results = {}
    with tempfile.TemporaryDirectory() as temporary:
        for name, material, slot, fail_save, repeat in cases:
            case_dir = output_root / name
            case_dir.mkdir()
            store = DraftStore(Path(temporary) / f"{name}.json", fail_save=fail_save)
            case_runs = []
            for index in range(1, repeat + 1):
                run_dir = case_dir / f"run{index}"
                run_dir.mkdir()
                request = AgentRequest(material, slot)
                write_json(run_dir / "input.json", {"material_id": material, "requested_slot": slot,
                                                     "simulate_save_failure": fail_save})
                attempts_before, responses_before = llm.call_attempts, len(llm.response_models)
                result, trace = run(request, llm, Tools(draft_store=store), max_steps=10)
                responses = llm.response_models[responses_before:]
                records = store._read_all()
                write_json(run_dir / "output.json", result)
                write_json(run_dir / "trace.json", trace)
                write_json(run_dir / "drafts_after.json", records)
                write_json(run_dir / "metadata.json", {
                    "mode": "real", "started_by": "scripts/run_real_remaining.py",
                    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                    "api_host": urlsplit(llm.base_url).hostname, "model_requested": llm.model,
                    "models_reported_by_api": responses,
                    "model_call_attempts": llm.call_attempts - attempts_before,
                    "valid_model_responses": len(responses), "max_steps": 10,
                    "simulate_save_failure": fail_save,
                })
                case_runs.append((result, trace, records, len(responses)))
                print(f"{name}/run{index}: {result['status']}, responses={len(responses)}", flush=True)
            results[name] = case_runs

    normal, risk = results["03-normal"][0], results["04-rule-risk"][0]
    first, second = results["05-duplicate"]
    failure = results["06-save-failure"][0]
    checks = {
        "normal": (normal[0]["status"] == "draft_saved" and normal[0]["draft_saved"]
                   and normal[0]["suggested_slot"] == "17:00" and not normal[0]["pending_confirmation"]
                   and len(normal[2]) == 1),
        "risk": (risk[0]["status"] == "blocked" and not risk[0]["draft_saved"]
                 and bool(risk[0]["risk_reasons"]) and len(risk[2]) == 0),
        "duplicate": (first[0]["status"] == second[0]["status"] == "draft_saved"
                      and first[0]["draft_id"] is not None and first[0]["draft_id"] == second[0]["draft_id"]
                      and second[0]["duplicate"] and len(first[2]) == len(second[2]) == 1),
        "save_failure": (failure[0]["status"] == "save_failed" and not failure[0]["draft_saved"]
                         and failure[0]["draft_id"] is None and len(failure[2]) == 0
                         and any(s["action"] == "save_draft" and '"save_failed"' in s["tool_result_summary"]
                                 for s in failure[1])),
        "all_real_responses": all(r[3] > 0 for runs in results.values() for r in runs),
        "no_publish": all(not r[0]["published"] for runs in results.values() for r in runs),
    }
    write_json(output_root / "acceptance.json", {"checks": checks, "all_passed": all(checks.values())})
    print(f"记录目录：{output_root}", flush=True)
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
