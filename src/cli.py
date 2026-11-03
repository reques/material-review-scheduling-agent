"""CLI：python3 -m src.cli --material M01 --slot 18:00 --mock

退出码约定（见 README）：Agent 返回结构化业务结果（draft_saved /
blocked / save_failed / incomplete）时退出码为 0，这些是合法的业务
结果，不是崩溃；仅参数/用法错误退出码为 2。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .agent import run
from .llm import LLMError, MockLLM, OpenAICompatibleClient
from .models import AgentRequest
from .tools import DraftStore, Tools


def _load_dotenv() -> None:
    """读取当前目录 .env（若存在），仅补全未设置的环境变量。标准库实现，无 dotenv 依赖。"""
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="素材审核与发布排期 Agent（仅保存草稿，不真实发布）")
    p.add_argument("--material", help="素材 ID，如 M01")
    p.add_argument("--slot", help="请求发布时间，如 18:00")
    p.add_argument("--input", dest="input_path", help="JSON 输入文件，含 material_id / requested_slot / request_id")
    p.add_argument("--mock", action="store_true", help="使用离线 MockLLM（不需密钥，仅验证流程）")
    p.add_argument("--llm", choices=["mock", "real"], default=None,
                   help="选择模型后端；默认：--mock 时为 mock，否则无密钥时报错")
    p.add_argument("--request-id", default="", help="请求 ID（用于追踪）")
    p.add_argument("--max-steps", type=int, default=8, help="ReAct 步数上限，默认 8")
    p.add_argument("--draft-store", default=None, help="草稿存储 JSON 路径，默认当前目录 .drafts.json")
    p.add_argument("--fail-save", action="store_true", help="模拟草稿保存失败")
    p.add_argument("--out", default="output", help="输出目录，写入 output.json 与 trace.json")
    p.add_argument("--trace-out", default=None, help="Trace 额外写入路径（可选）")
    p.add_argument("--data-dir", default=None, help="数据目录，默认项目 data/")
    return p


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_dotenv()

    material_id = args.material
    slot = args.slot
    request_id = args.request_id
    if args.input_path:
        try:
            data = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"错误：无法读取输入文件：{exc}", file=sys.stderr)
            return 2
        material_id = data.get("material_id", material_id)
        slot = data.get("requested_slot", slot)
        request_id = data.get("request_id", request_id)
    if not material_id or not slot:
        print("错误：须提供 --material 与 --slot，或 --input JSON 文件。", file=sys.stderr)
        return 2
    if args.max_steps < 1:
        print("错误：--max-steps 须 >= 1。", file=sys.stderr)
        return 2

    use_mock = args.mock or args.llm == "mock"
    if use_mock:
        llm = MockLLM()
    elif args.llm == "real":
        try:
            llm = OpenAICompatibleClient()
        except LLMError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2
    else:
        # 未指定 --mock/--llm 且无密钥：明确报错，指向 .env.example 与 --mock。
        if not os.environ.get("LLM_API_KEY"):
            print("错误：未配置 LLM_API_KEY。请使用 --mock 离线运行，或按 .env.example 配置密钥后使用 --llm real。",
                  file=sys.stderr)
            return 2
        try:
            llm = OpenAICompatibleClient()
        except LLMError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 2

    draft_path = Path(args.draft_store) if args.draft_store else Path.cwd() / ".drafts.json"
    tools = Tools(data_dir=args.data_dir, draft_store=DraftStore(draft_path, fail_save=args.fail_save))
    request = AgentRequest(material_id=material_id, requested_slot=slot, request_id=request_id)
    result, trace = run(request, llm, tools, max_steps=args.max_steps)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "output.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.trace_out:
        Path(args.trace_out).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    # 人类可读摘要（stdout）；完整结果在 output.json / trace.json。
    print(f"素材：{result['material_id']}  请求时段：{result['requested_slot']}")
    print(f"状态：{result['status']}（审核：{result['review_status']}）")
    if result.get("risk_reasons"):
        print("风险原因：" + "; ".join(result["risk_reasons"]))
    print(f"建议时段：{result.get('suggested_slot')}")
    print(f"待确认：{result.get('pending_confirmation')}  草稿已保存：{result.get('draft_saved')}  草稿 ID：{result.get('draft_id')}")
    if result.get("duplicate"):
        print("重复提交：返回已有草稿，未新建记录。")
    print("已发布：False（本工具仅保存草稿，绝不真实发布）")
    if result.get("reason"):
        print(f"说明：{result['reason']}")
    print(f"输出：{out_dir / 'output.json'}  Trace：{out_dir / 'trace.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
