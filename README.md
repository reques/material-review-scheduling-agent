# 素材审核与发布排期 Agent

考试项目题 1：帮助内容团队找出待处理素材，形成无冲突、可确认的发布排期。**仅保存草稿，绝不真实发布。**

## 环境与安装

- Python 3.12（已验证 `Python 3.12.7` 与 `3.12.9`）。
- **无任何第三方依赖**：仅使用 Python 标准库，`requirements.txt` 已声明“stdlib-only”。无需 `pip install`，无需虚拟环境。

```bash
python3 --version   # 须为 3.12.x
```

Windows PowerShell 中可使用 `python`；以下命令在项目根目录执行，无需激活或提交虚拟环境：

```powershell
python --version
$env:PYTHONUTF8 = '1'
python -m unittest discover -s tests -v
python -m src.cli --list-pending --draft-store "$env:TEMP\material-review-drafts.json"
python -m src.cli --material M01 --slot 18:00 --mock --draft-store "$env:TEMP\material-review-drafts.json" --out output
```

如系统中 `python` 不是 3.12，请使用已安装的 Python 3.12 解释器；例如本机可用 `.\.venv\Scripts\python.exe` 替代 `python`。若之前的草稿影响示例，可指定一个新的 `--draft-store` 路径。

## 查看待处理素材

```bash
python3 -m src.cli --list-pending --draft-store /tmp/drafts.json
```

此入口直接读取本地素材和草稿，不需要模型或密钥，输出 JSON：`pending` 为 `work_status=pending` 的素材；`unclassified` 为状态缺失或不认识的素材，不会静默当成已处理。每项包含缺失字段、草稿以及 `processing_state`：`not_started`、`draft_saved`、`pending_confirmation` 或 `draft_conflict`。草稿冲突检查使用当前本地排期和草稿。

`data/materials.json` 中的 `work_status` 由数据维护者设置：`pending` 为待处理，`completed` 与 `archived` 不进入待处理清单。保存草稿不会自动将素材设为已处理；当前无修改素材状态或人工确认的交互功能。选定素材后，用下面的单素材命令继续审核和排期。示例见 `examples/08-pending-list/`。

## 运行（Mock 模式，无需密钥）

```bash
cd material-review-scheduling-agent

# 时段冲突示例：M01 要求 18:00（被占），建议 19:00，待确认，仅保存草稿
python3 -m src.cli --material M01 --slot 18:00 --mock --draft-store /tmp/drafts.json --out output

# 正常排期：M04 请求空闲时段 17:00
python3 -m src.cli --material M04 --slot 17:00 --mock --draft-store /tmp/drafts.json --out output

# 信息缺失：M02（补查后仍缺失，阻塞）
python3 -m src.cli --material M02 --slot 17:00 --mock --draft-store /tmp/drafts.json --out output

# 规则风险：M03（未授权 + 敏感标记，阻塞）
python3 -m src.cli --material M03 --slot 17:00 --mock --draft-store /tmp/drafts.json --out output

# 保存失败模拟
python3 -m src.cli --material M06 --slot 20:00 --mock --fail-save --draft-store /tmp/drafts.json --out output

# 文件输入（JSON 含 material_id / requested_slot / request_id）
python3 -m src.cli --input examples/01-normal/input.json --mock --draft-store /tmp/drafts.json --out output
```

每次运行在 stdout 打印人类可读摘要，并在 `--out` 目录写入 `output.json`（最终结果）与 `trace.json`（完整执行记录：步骤、工具参数、返回摘要、决策依据）。

### 真实模型模式（需密钥）

```bash
cp .env.example .env   # 填入 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，切勿提交 .env
python3 -m src.cli --material M01 --slot 18:00 --llm real --draft-store /tmp/drafts.json --out output
```

配置完成后，可用 `python3 scripts/run_real_examples.py` 运行时段冲突和信息缺失两条路径。每次运行会在 `examples/real-llm/` 下新建独立目录，保存输入、实际输出、Trace 和模型调用元数据；未完成或未得到有效模型响应时脚本返回非零退出码。该脚本不保存 API 密钥。

2026-11-05 使用 DeepSeek `deepseek-flash` 实际运行了全部六类验收场景，并补充变更占用时段后重复提交的场景。记录与结果见 `docs/03-evaluation.md`。其他场景可分别用 `python3 scripts/run_real_remaining.py` 和 `python3 scripts/run_real_changed_schedule.py` 重新运行。

未配置 `LLM_API_KEY` 且未加 `--mock` 时，CLI 明确报错并指向 `.env.example` 与 `--mock`，退出码为 2。

### 退出码约定

- `0`：Agent 返回了结构化业务结果，包括 `draft_saved`、`blocked`、`save_failed`、`incomplete`——这些是合法业务结果，不是崩溃；
- `2`：参数/用法错误（如缺少素材 ID、无法读取输入文件、无密钥且未指定 `--mock`）。

### 常用参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--material` / `--slot` | 素材 ID / 请求时段（`HH:MM`） | — |
| `--list-pending` | 列出待处理素材与草稿状态，不调用模型 | 关闭 |
| `--input` | JSON 输入文件路径 | — |
| `--mock` / `--llm mock\|real` | Mock 或真实模型 | 无密钥时须 `--mock` |
| `--request-id` | 请求 ID（追踪用） | 空 |
| `--max-steps` | ReAct 步数上限 | `8` |
| `--draft-store` | 草稿存储 JSON 路径 | 当前目录 `.drafts.json` |
| `--fail-save` | 模拟草稿保存失败 | 关闭 |
| `--out` | 输出目录（`output.json` / `trace.json`） | `output` |
| `--trace-out` | Trace 额外写入路径 | — |
| `--data-dir` | 数据目录 | 项目 `data/` |

## 评估入口

```bash
# 单元测试（unittest，无网络，无真实 LLM）：31 个测试
python3 -m unittest discover -s tests -v

# 重新生成 examples/（CLI 真实运行产物，非手写）
python3 scripts/generate_examples.py
# 或
sh scripts/generate_examples.sh
```

## 仓库结构

```text
README.md  requirements.txt  .env.example  .gitignore
src/            # 代码与模型/工具接入：models / llm / tools / guards / agent / cli
tests/          # 可执行测试（unittest）
examples/       # Mock 示例、待处理清单示例及独立的真实模型运行记录
data/           # 合成数据与规则（materials.json / schedule.json / rules.json，虚构 ID）
docs/           # 01-requirements / 02-solution / 03-evaluation / 04-ai-usage / 05-retrospective
scripts/        # 生成 Mock 示例 / 运行真实模型示例
```

设计细节见 `docs/02-solution.md`；逐验收点预期 vs 实际见 `docs/03-evaluation.md`。

## 限制（诚实说明）

- 七组基础示例使用 `MockLLM`，只能验证流程；`examples/real-llm/` 另存真实模型运行记录，单次样本不能代表所有输入与模型的决策质量。业务工具和保存失败故障仍为本地模拟。
- 本项目不提供真实发布功能与人工确认交互；`pending_confirmation` 只是结果标记，需用户确认后方可进入后续发布流程。
- 草稿存储为单 JSON 文件，无并发锁，仅适合单机演示与测试；数据为 6 个虚构素材的小规模合成集。
- 草稿时段也视为占用；同一请求可重用自己的草稿。若已有草稿与重新计算的建议时段不一致，返回 `blocked` 并附 `existing_draft`，由人工处理旧草稿，不自动覆盖。
- 达到步数上限时返回 `incomplete`；若上限前草稿已经保存，仍会如实返回草稿 ID 和保存状态。
- `.env`、本地 IDE 配置和虚拟环境在 `.gitignore` 中；提交前仍需检查暂存区并确认无真实密钥或隐私数据，见 `docs/06-submission-checklist.md`。
