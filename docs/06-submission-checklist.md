# 06 提交前检查

本次检查日期：2026-11-05。检查的是当前项目目录（`material-review-scheduling-agent`）。

## 结论先说

**仓库内容已达到提交标准，代码和文档已推送到 GitHub。**

仓库地址：<https://github.com/reques/material-review-scheduling-agent>

具体说：代码、测试、数据、示例、六类验收记录、真实模型记录、docs/01–05、依赖文件和 `.env.example` 都在，31 项离线测试通过，示例可重新生成。题号是 1，URL 已填；**最终 commit SHA** 以提交表单为准（本文档不写自身 SHA，避免自引用）。

## 逐项对照

| 题目要求 | 仓库里的证据 | 状态 |
|---|---|---|
| README：环境、安装、运行、评审入口 | `README.md`，含 Windows/macOS 命令和"评审先看这里" | 有 |
| `src/` 代码与模型/工具接入 | `src/models.py`、`llm.py`、`tools.py`、`guards.py`、`agent.py`、`cli.py` | 有 |
| `tests/` 可执行测试 | 31 项，`python -m unittest discover -s tests -v` 全过；输出在 `examples/test-results.txt` | 有 |
| `examples/` 输入、实际输出、Trace | `01`–`08`；`08` 是本地清单，无 Agent Trace；`real-llm/` 下 5 组真实运行记录 | 有 |
| `data/` 合成资料和规则 | `materials.json`、`schedule.json`、`rules.json`，全部虚构 | 有 |
| `docs/01-requirements.md` | 用户、目标、范围、六条验收标准 | 有 |
| `docs/02-solution.md` | 调用流程、动态决策、技术取舍 | 有 |
| `docs/03-evaluation.md` | 预期 vs 实际、真实模型、失败和限制 | 有 |
| `docs/04-ai-usage.md` | AI 使用范围、个人贡献、验证分工、实际用时 | 有 |
| `docs/05-retrospective.md` | 最难的问题、踩坑、学习、下一步 | 有 |
| 依赖文件 | `requirements.txt`，声明 stdlib-only，无第三方依赖 | 有 |
| `.env.example` | `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`，无真实密钥 | 有 |
| 至少 3 组输入/输出/运行记录，覆盖正常、信息不足、工具失败 | `01-normal`、`02-missing-info`、`06-save-failure`，另有 03/04/05/07/08 | 有 |
| 覆盖所选题目全部验收点 | 六类验收 + 变更占用重复提交，见 `docs/03-evaluation.md` | 有 |
| 至少两条执行路径，体现模型按工具结果调整 | `04-slot-conflict`（6 步）和 `02-missing-info`（4 步）；真实模型另有记录 | 有 |
| 步数/工具调用上限，超限明确未完成 | `--max-steps` 默认 8；`test_step_cap` 验证 `incomplete` | 有 |
| 不提交真实密钥或隐私数据 | 扫过 `sk-`、`Bearer`、邮箱、本机路径；`.env` 在 `.gitignore` 中 | 有，但见下面提醒 |
| 题号、GitHub URL、最终 commit SHA | 题号是 1；URL 已填；SHA 在提交表里填写 | URL 有，SHA 待填 |
| 私有仓库给评审账号读权限 | 取决于最终仓库设置 | **待确认** |

## 还需要补的一项

**最终 commit SHA**：仓库已经推送到 `main`。在仓库最新 commit 上执行：

```bash
git rev-parse HEAD
```

或者在 GitHub 的 commit 页面复制完整 40 位 SHA，填到提交表里。不要在提交后又改文件却不重新提交，否则 SHA 会对不上。

本机这个源目录没有 `.git`，但 GitHub 仓库已经是最终内容。要查看历史或取 SHA，可以重新 clone 一份；不要在这个源目录里 `git init` 后强推覆盖已有历史。

## 提交前不要带上的东西

本机根目录有一个 `.env`，里面是真实模型配置。它已经在 `.gitignore` 里，但打包、压缩、拖拽上传都可能绕过 `.gitignore`。提交前确认这些不在暂存区和最终压缩包里：

- `.env`、其他本地密钥文件；
- `.venv/`；
- `.idea/`；
- `.drafts.json`、`drafts.json`；
- `output/`；
- `__pycache__/`、`*.pyc`。

`.env.example` 要保留，里面不能有真实密钥。

## 提交前建议跑一遍

在克隆目录执行：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/generate_examples.py
git status --short
git diff --cached --name-only
```

确认：

- 31 项测试全过；
- `examples/` 重新生成后没有意外差异；
- 暂存的只有代码、测试、数据、文档、示例和配置；
- 没有 `.env`、密钥、临时草稿、IDE 配置或虚拟环境。

## 最后核对

- README 里的命令能在干净环境执行，不需要 `pip install`；
- `docs/03-evaluation.md` 里的示例路径都存在；
- `examples/real-llm/` 的 `metadata.json` 不含密钥，只有 `api_host`、模型名和调用次数；
- 提交表里填的是：**题号 1、GitHub URL、最终 commit SHA**；
- 仓库当前是公开的，评审可以直接打开；如果之后改成私有，记得给指定评审账号读权限。

## 提交表（填好后随邮件/表单提交）

```text
题号：1
GitHub URL：https://github.com/reques/material-review-scheduling-agent
最终 commit SHA：
```

`git rev-parse HEAD` 的输出是 40 位十六进制；不要只填前 7 位。SHA 不写进本文件，因为文件内容会改变 commit 本身，写进去就对不上了；以提交表单里填的值为准。
