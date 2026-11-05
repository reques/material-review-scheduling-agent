"""重新生成 examples/：用 CLI（--mock）真实运行，输出即实际输出，不手写。

用法：python3 scripts/generate_examples.py
草稿存储使用临时目录，不污染仓库 data/；重复提交示例两次运行共用同一临时存储。
"""

from __future__ import annotations

import json
import shutil
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


def run_cli(material_id: str, slot: str, draft_store: Path, out_dir: Path, fail_save: bool,
            data_dir: Path | None = None) -> None:
    cmd = [sys.executable, "-m", "src.cli", "--material", material_id, "--slot", slot,
           "--mock", "--draft-store", str(draft_store), "--out", str(out_dir)]
    if fail_save:
        cmd.append("--fail-save")
    if data_dir is not None:
        cmd.extend(["--data-dir", str(data_dir)])
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

        # 旧草稿所建议的时段后来被占：第二次请求不能静默覆盖旧草稿。
        out_dir = EXAMPLES / "07-changed-schedule"
        out_dir.mkdir(parents=True, exist_ok=True)
        data_dir = tmp_path / "changed-data"
        shutil.copytree(ROOT / "data", data_dir)
        draft_store = tmp_path / "changed-drafts.json"
        (out_dir / "input.json").write_text(json.dumps({"material_id": "M01", "requested_slot": "18:00",
            "between_runs": "将已有排期中的 19:00 改为被 OTHER 占用"}, ensure_ascii=False, indent=2), encoding="utf-8")
        run_cli("M01", "18:00", draft_store, out_dir, False, data_dir)
        for name in ("output", "trace"):
            shutil.copyfile(out_dir / f"{name}.json", out_dir / f"{name}_run1.json")
        schedule_path = data_dir / "schedule.json"
        schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
        schedule["slots"]["19:00"] = {"material_id": "OTHER", "occupied": True}
        schedule_path.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
        run_cli("M01", "18:00", draft_store, out_dir, False, data_dir)
        shutil.copyfile(draft_store, out_dir / "drafts_after_run2.json")
        print("07-changed-schedule: 保留旧草稿并报告冲突")

        # 此入口是本地筛选，不调用模型，因此只有输入与输出，没有 Agent Trace。
        out_dir = EXAMPLES / "08-pending-list"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "input.json").write_text(
            json.dumps({"operation": "list_pending"}, ensure_ascii=False, indent=2), encoding="utf-8")
        cmd = [sys.executable, "-m", "src.cli", "--list-pending", "--draft-store",
               str(tmp_path / "pending-list-drafts.json")]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode:
            raise SystemExit(f"待处理素材入口失败：{result.stderr}")
        (out_dir / "output.json").write_text(
            json.dumps(json.loads(result.stdout), ensure_ascii=False, indent=2), encoding="utf-8")
        print("08-pending-list: 已生成待处理素材清单")


if __name__ == "__main__":
    main()
