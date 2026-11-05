# 素材审核与发布排期 Agent

仓库：<https://github.com/reques/material-review-scheduling-agent>

题 1。帮内容团队找出待处理素材，形成无冲突、可确认的发布排期。

**只保存草稿，不接真实发布。** 系统里没有发布工具，所有结果的 `published` 都是 `false`。

## 评审先看这里

如果只想花几分钟判断这个项目是不是真的能跑：

```powershell
# Windows PowerShell
python -m unittest discover -s tests -v
python -m src.cli --list-pending --draft-store "$env:TEMP\mrsa-drafts.json"
python -m src.cli --material M01 --slot 18:00 --mock --draft-store "$env:TEMP\mrsa-drafts.json" --out "$env:TEMP\mrsa-out"
```

```bash
# macOS / Linux
python3 -m unittest discover -s tests -v
python3 -m src.cli --list-pending --draft-store /tmp/mrsa-drafts.json
python3 -m src.cli --material M01 --slot 18:00 --mock --draft-store /tmp/mrsa-drafts.json --out /tmp/mrsa-out
```

跑 M01 的那条命令应该看到：

- `status=draft_saved`
- `suggested_slot=19:00`（18:00 已被占）
- `pending_confirmation=true`
- `draft_saved=true`，`draft_id` 以 `D-` 开头
- `published=false`

然后建议按这个顺序看：

1. `examples/04-slot-conflict/trace.json`：6 步，能看到 18:00 被占 → 单独验证 19:00 → 保存草稿；
2. `examples/02-missing-info/trace.json`：4 步，补查后仍缺失 → 阻塞，不保存；
3. `examples/real-llm/20261105T093722468190Z/01-slot-conflict/trace.json`：真实模型先保存被拒 → 自己改查 19:00 → 再保存，7 步；
4. `examples/real-llm/`：其余真实模型的运行记录和 `metadata.json`；
5. `docs/03-evaluation.md`：六个验收点的预期和实际；
6. `docs/04-ai-usage.md`：哪些是 AI 做的，哪些判断是我做的。

## 环境

- Python 3.12 及以上。仓库里记录过 3.12.7 / 3.12.9；这次复核在 3.13.5 上跑通 31 项测试。
- **没有第三方依赖**。`requirements.txt` 只声明"stdlib-only"，不需要 `pip install`，也不需要虚拟环境。
- Windows 下 `python` 即可；如果机器上的 `python` 不是 3.12+，用对应的解释器路径替换。

```bash
python3 --version   # 应为 3.12 或更高
```

## 运行

以下命令都在项目根目录执行。

### 查看待处理素材

```bash
python3 -m src.cli --list-pending --draft-store /tmp/drafts.json
```

这个入口不调用模型，直接读 `data/materials.json` 和草稿文件，输出 JSON：

- `pending`：`work_status=pending` 的素材，含缺失字段、草稿、处理状态；
- `unclassified`：状态缺失或不认识的素材，不会被静默当成已处理。

`processing_state` 有四种：`not_started`、`draft_saved`、`pending_confirmation`、`draft_conflict`。草稿冲突检查使用当前排期和其他草稿。保存草稿不会自动把素材改成"已处理"；`work_status` 由数据维护者维护。示例见 `examples/08-pending-list/`。

### 单素材跑一遍（Mock，无需密钥）

```bash
# 时段冲突：M01 要求 18:00（被占），建议 19:00，待确认，仅草稿
python3 -m src.cli --material M01 --slot 18:00 --mock --draft-store /tmp/drafts.json --out output

# 正常排期：M04 请求空闲的 17:00
python3 -m src.cli --material M04 --slot 17:00 --mock --draft-store /tmp/drafts.json --out output

# 信息缺失：M02 补查后仍缺标题和授权，阻塞
python3 -m src.cli --material M02 --slot 17:00 --mock --draft-store /tmp/drafts.json --out output

# 规则风险：M03 未授权转载 + 敏感标记，阻塞
python3 -m src.cli --material M03 --slot 17:00 --mock --draft-store /tmp/drafts.json --out output

# 保存失败模拟
python3 -m src.cli --material M06 --slot 20:00 --mock --fail-save --draft-store /tmp/drafts.json --out output

# 从 JSON 输入文件读参数
python3 -m src.cli --input examples/01-normal/input.json --mock --draft-store /tmp/drafts.json --out output
```

每次运行会在 stdout 打印人类可读摘要，并在 `--out` 目录写 `output.json`（最终结果）和 `trace.json`（步骤、工具参数、返回摘要、下一步动作和简要决策依据）。

### 真实模型（需要密钥）

```bash
cp .env.example .env   # 填入 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
python3 -m src.cli --material M01 --slot 18:00 --llm real --draft-store /tmp/drafts.json --out output
```

`.env` 只在本地，`.gitignore` 已覆盖；不要提交真实密钥。没有配置 `LLM_API_KEY` 又没加 `--mock` 时，CLI 会明确报错并指向 `.env.example`，退出码为 2。

真实模型示例可以重新跑：

```bash
python3 scripts/run_real_examples.py          # 冲突 + 缺失信息
python3 scripts/run_real_remaining.py         # 正常 / 规则风险 / 重复 / 保存失败
python3 scripts/run_real_changed_schedule.py  # 更换占用时段后重复提交
```

每次运行会在 `examples/real-llm/` 下新建独立目录，保存输入、输出、Trace 和不含密钥的 `metadata.json`。脚本不打印、不保存密钥。

2026-11-05 用 DeepSeek `deepseek-flash` 跑过六类验收和变更占用场景，记录见 `examples/real-llm/`。第一次运行的状态没有归一化，记录保留在 `20261105T075237956775Z/`，没有回写；修复后的记录在 `075334688087Z/` 和 `093722468190Z/`。细节见 `docs/03-evaluation.md`。

### 退出码

- `0`：Agent 返回了结构化业务结果，包括 `draft_saved`、`blocked`、`save_failed`、`incomplete`。这些是合法业务结果，不是崩溃。
- `2`：参数或用法错误，比如缺少素材 ID、输入文件读不了、没有密钥又没加 `--mock`。

### 常用参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--material` / `--slot` | 素材 ID / 请求时段（`HH:MM`） | — |
| `--list-pending` | 列出待处理素材和草稿状态，不调用模型 | 关闭 |
| `--input` | JSON 输入文件路径 | — |
| `--mock` / `--llm mock\|real` | Mock 或真实模型 | 无密钥时须 `--mock` |
| `--request-id` | 请求 ID（追踪用） | 空 |
| `--max-steps` | ReAct 步数上限 | `8` |
| `--draft-store` | 草稿存储 JSON 路径 | 当前目录 `.drafts.json` |
| `--fail-save` | 模拟草稿保存失败 | 关闭 |
| `--out` | 输出目录（`output.json` / `trace.json`） | `output` |
| `--trace-out` | Trace 额外写入路径 | — |
| `--data-dir` | 数据目录 | 项目 `data/` |

## 测试和示例

```bash
# 31 个离线测试，不依赖网络和真实密钥
python3 -m unittest discover -s tests -v

# 重新生成 examples/（CLI 真实运行产物，不是手写）
python3 scripts/generate_examples.py
# 或
sh scripts/generate_examples.sh
```

- 本次离线测试的实际输出保存在 `examples/test-results.txt`。
- `examples/README.md` 是示例索引；`examples/real-llm/README.md` 是真实模型记录索引。
- `examples/` 里的输出由脚本生成，不是手写。重新生成后与仓库文件逐项比对（忽略时间戳）没有差异。

## 仓库结构

```text
README.md  requirements.txt  .env.example  .gitignore
src/            # 代码与模型/工具接入
  models.py     # 数据模型
  llm.py        # OpenAI 兼容客户端 + MockLLM
  tools.py      # 素材读取 / 规则检查 / 时段查询 / 补查 / 草稿保存
  guards.py     # 发布声称、硬性时段、风险、保存观察的护栏
  agent.py      # ReAct 循环
  cli.py        # CLI 入口
tests/          # 31 个可执行离线测试
examples/       # Mock 示例、待处理清单、真实模型运行记录、测试结果
data/           # 合成素材 / 排期 / 规则（虚构 ID）
docs/           # 01-requirements / 02-solution / 03-evaluation / 04-ai-usage / 05-retrospective / 06-submission-checklist
scripts/        # 生成示例 / 运行真实模型
```

设计细节见 `docs/02-solution.md`；逐验收点对照见 `docs/03-evaluation.md`；AI 使用和个人贡献见 `docs/04-ai-usage.md`；提交前检查见 `docs/06-submission-checklist.md`。

## 已知限制

- 七个基础示例用 `MockLLM`，只验证流程；真实模型记录在 `examples/real-llm/`，单次样本不能代表所有输入和模型。
- 不提供真实发布，也没有"用户点确认后才继续"的交互；`pending_confirmation` 只是结果标记。
- 草稿存储是单 JSON 文件，没有并发锁，只适合单机演示和测试；数据是 6 个虚构素材的小规模合成集。
- 草稿时段也算占用；同一请求可以重用自己的草稿。已有草稿和重新计算的建议时段不一致时，返回 `blocked` 和 `existing_draft`，由人工处理旧草稿，不自动覆盖。
- 达到步数上限时返回 `incomplete`；如果上限前草稿已经保存，仍会如实返回草稿 ID 和保存状态。
- `.env`、本地 IDE 配置、虚拟环境和临时草稿在 `.gitignore` 里；提交前仍要检查暂存区，见 `docs/06-submission-checklist.md`。
