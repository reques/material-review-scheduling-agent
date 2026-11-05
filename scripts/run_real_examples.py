"""Run two real-model cases and preserve honest, separate execution records.

Requires .env or process environment; never reads, prints or writes the API key
into the records. Each case uses a fresh temporary draft store.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent import run
from src.cli import _load_dotenv
from src.llm import LLMError, OpenAICompatibleClient
from src.models import AgentRequest
from src.tools import DraftStore, Tools


def write_json(path: Path, value) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2)
    secret = os.environ.get("LLM_API_KEY", "")
    if secret:
        data = data.replace(secret, "[REDACTED]")
    path.write_text(data, encoding="utf-8")


def main() -> int:
    _load_dotenv()
    try:
        # Validate configuration before creating any result directory.
        llm = OpenAICompatibleClient(timeout=60)
    except LLMError as exc:
        print(f"模型配置不完整：{exc}", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_root = ROOT / "examples" / "real-llm" / stamp
    output_root.mkdir(parents=True, exist_ok=False)
    cases = [("01-slot-conflict", "M01", "18:00"), ("02-missing-info", "M02", "17:00")]
    completed = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, material, slot in cases:
            case_dir = output_root / name
            case_dir.mkdir()
            request = AgentRequest(material, slot)
            write_json(case_dir / "input.json", {"material_id": material, "requested_slot": slot})
            attempts_before = llm.call_attempts
            responses_before = len(llm.response_models)
            tools = Tools(draft_store=DraftStore(Path(tmp) / f"{name}.json"))
            result, trace = run(request, llm, tools, max_steps=10)
            valid_responses = len(llm.response_models) - responses_before
            write_json(case_dir / "output.json", result)
            write_json(case_dir / "trace.json", trace)
            write_json(case_dir / "metadata.json", {
                "mode": "real", "started_by": "scripts/run_real_examples.py",
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "api_host": urlsplit(llm.base_url).hostname,
                "model_requested": llm.model,
                "models_reported_by_api": llm.response_models[responses_before:],
                "model_call_attempts": llm.call_attempts - attempts_before,
                "valid_model_responses": valid_responses,
                "max_steps": 10,
            })
            print(f"{name}: {result['status']}; trace: {case_dir / 'trace.json'}")
            completed.append((result, trace, valid_responses))
    print(f"记录目录：{output_root}")
    if any(count == 0 or result["status"] == "incomplete" for result, _, count in completed):
        print("至少一个案例未获得有效模型结果或未完成；请检查已保存的记录。", file=sys.stderr)
        return 1
    if [item["action"] for item in completed[0][1]] == [item["action"] for item in completed[1][1]]:
        print("两条路径的动作序列相同；请检查是否满足评估要求。", file=sys.stderr)
        return 1
    first, second = completed[0][0], completed[1][0]
    if not (first["status"] == "draft_saved" and first["draft_saved"]
            and first["suggested_slot"] != first["requested_slot"] and first["pending_confirmation"]
            and second["status"] == "blocked" and not second["draft_saved"]):
        print("真实模型运行结果未通过两条场景的业务验收；请检查记录。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
