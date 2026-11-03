# 素材审核与发布排期 Agent

考试项目题 1：帮助内容团队找出待处理素材，形成无冲突、可确认的发布排期。**仅保存草稿，绝不真实发布。**

## 环境与安装

- Python 3.12（已验证 `Python 3.12.3`）。
- **无任何第三方依赖**：仅使用 Python 标准库，`requirements.txt` 已声明“stdlib-only”。无需 `pip install`，无需虚拟环境。

```bash
python3 --version   # 须为 3.12.x
```

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

### 真实模型模式（需密钥，未在本机构建中验证）

```bash
cp .env.example .env   # 填入 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，切勿提交 .env
python3 -m src.cli --material M01 --slot 18:00 --llm real --draft-store /tmp/drafts.json --out output
```

未配置 `LLM_API_KEY` 且未加 `--mock` 时，CLI 明确报错并指向 `.env.example` 与 `--mock`，退出码为 2。

### 退出码约定

- `0`：Agent 返回了结构化业务结果，包括 `draft_saved`、`blocked`、`save_failed`、`incomplete`——这些是合法业务结果，不是崩溃；
- `2`：参数/用法错误（如缺少素材 ID、无法读取输入文件、无密钥且未指定 `--mock`）。

### 常用参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--material` / `--slot` | 素材 ID / 请求时段（`HH:MM`） | — |
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
# 单元测试（unittest，无网络，无真实 LLM）：13 个测试
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
examples/       # 输入、实际输出、Trace（6 个示例，覆盖全部 6 个验收点）
data/           # 合成数据与规则（materials.json / schedule.json / rules.json，虚构 ID）
docs/           # 01-requirements / 02-solution / 03-evaluation / 04-ai-usage / 05-retrospective
scripts/        # generate_examples.py / .sh（复现 examples/）
```

设计细节见 `docs/02-solution.md`；逐验收点预期 vs 实际见 `docs/03-evaluation.md`。

## 限制（诚实说明）

- 全部示例 Trace 由离线 `MockLLM` 生成，仅验证流程，**不证明真实模型决策质量**；真实模型运行尚未验证（无密钥），见 `docs/03-evaluation.md` 与 `docs/04-ai-usage.md`。
- 本项目不提供真实发布功能与人工确认交互；`pending_confirmation` 只是结果标记，需用户确认后方可进入后续发布流程。
- 草稿存储为单 JSON 文件，无并发锁，仅适合单机演示与测试；数据为 6 个虚构素材的小规模合成集。
- 无真实密钥、无隐私数据提交到本仓库；`.env` 已在 `.gitignore` 中。
