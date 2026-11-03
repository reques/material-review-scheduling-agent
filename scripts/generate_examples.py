"""重新生成 examples/：用 CLI（--mock）真实运行，输出即实际输出，不手写。

用法：python3 scripts/generate_examples.py
草稿存储使用临时目录，不污染仓库 data/；重复提交示例两次运行共用同一临时存储。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

CASES = [
    # (目录, 素材, 时段, 是否模拟保存失败)
    ("01-normal", "M04", "17:00", False),
    ("02-missing-info", "M02", "17:00", False),
    ("03-rule-risk", "M03", "17:00", False),
    ("04-slot-conflict", "M01", "18:00", False),
    ("05-duplicate", "M06", "20:00", False),
    ("06-save-failure", "M06", "20:00", True),
]


def run_cli(material_id: str, slot: str, draft_store: Path, out_dir: Path, fail_save: bool) -> None:
    cmd = [sys.executable, "-m", "src.cli", "--material", material_id, "--slot", slot,
           "--mock", "--draft-store", str(draft_store), "--out", str(out_dir)]
    if fail_save:
        cmd.append("--fail-save")
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"CLI 失败 {material_id} {slot}:\n{result.stdout}\n{result.stderr}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for dirname, material_id, slot, fail_save in CASES:
            out_dir = EXAMPLES / dirname
            out_dir.mkdir(parents=True, exist_ok=True)
            input_data = {"material_id": material_id, "requested_slot": slot}
            if fail_save:
                input_data["fail_save"] = True
            (out_dir / "input.json").write_text(
                json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8")
            draft_store = tmp_path / f"{dirname}.json"
            if dirname == "05-duplicate":
                # 两次提交共用同一存储：第一次与第二次的输出都保留。
                run_cli(material_id, slot, draft_store, out_dir, fail_save)
                (out_dir / "output_run1.json").write_text(
                    (out_dir / "output.json").read_text(encoding="utf-8"), encoding="utf-8")
                (out_dir / "trace_run1.json").write_text(
                    (out_dir / "trace.json").read_text(encoding="utf-8"), encoding="utf-8")
                run_cli(material_id, slot, draft_store, out_dir, fail_save)
                (out_dir / "output_run2.json").write_text(
                    (out_dir / "output.json").read_text(encoding="utf-8"), encoding="utf-8")
                # trace.json 保留第二次运行的 Trace（其中 duplicate=true）。
            else:
                run_cli(material_id, slot, draft_store, out_dir, fail_save)
            print(f"{dirname}: {material_id} {slot} -> {(out_dir / 'output.json').read_text(encoding='utf-8')[:120]}")


if __name__ == "__main__":
    main()
