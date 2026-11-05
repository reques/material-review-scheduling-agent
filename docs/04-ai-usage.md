# 04 — AI 使用说明

## 使用范围（诚实记录）

本项目使用 AI 辅助完成脚手架、代码、测试、示例生成与文档撰写。具体包括：

- AI 触及的文件：全部代码（`src/`）、测试（`tests/`）、数据（`data/`）、示例生成脚本（`scripts/`）、文档（`docs/`、`README.md`）与配置（`requirements.txt`、`.env.example`、`.gitignore`）。
- 用户在本地 `.env` 中配置真实模型参数；AI 使用该配置运行了真实模型示例并记录结果，未在对话或示例中保存密钥。项目后续根据用户指示同步到其现有 GitHub 仓库。
- 候选人其他个人贡献及其实际验证：尚待候选人按真实情况补充，不能由 AI 代为推断或编造。

## 人工必须验证的内容

构建者/评审人须自行验证以下事项，AI 的陈述不能代替验证：

1. 运行测试：`python3 -m unittest discover -s tests -v`，确认 31 个测试全部通过（Windows 使用 `python`，见 README）；
2. 阅读 `src/tools.py` 的保存前校验与 `src/guards.py` 的结果核对，确认风险、冲突、确认边界和保存状态的处理；
3. 检查 Trace：打开 `examples/04-slot-conflict/trace.json` 与 `examples/02-missing-info/trace.json`，确认步骤、工具参数、返回摘要与决策依据真实对应，且 M01 的替代时段 19:00 来自工具观察而非模型自创；
4. 复现示例：运行 `python3 scripts/generate_examples.py`，确认 `examples/` 输出可重新生成且与提交内容一致；
5. 检查拟提交文件不包含密钥及本机配置；`.env` 本身包含本地密钥，不应对外提交，也不要将其内容输出到日志。具体步骤见 `docs/06-submission-checklist.md`。

## Mock 边界声明

- 七组基础示例由 `MockLLM`（`src/llm.py`）生成；2026-11-05 的真实模型 Trace 单独保存于 `examples/real-llm/`。
- `MockLLM` 读取提示词中的工具观察结果并按代码中的启发式规则选择下一步动作；它的 Trace 只证明 ReAct 循环、工具调用、护栏与幂等逻辑可跑通，**不证明真实模型的决策效果**。
- 真实模型运行时，须配置 `.env`（见 `.env.example`）并使用 `--llm real`；真实运行的 Trace 应另行保存并与 Mock Trace 分开标注，不得混为一谈。

## 实际用时与未完成部分

- 实际用时：未按分钟计时，无法准确统计；题目建议投入为 3 小时。
- 未完成/未验证部分：
  - 真实模型虽已覆盖六类验收点及排期变化重复提交，但每类只做了有限次数的运行，不能代表实际场景的稳定性；
  - 人工确认交互步骤（仅以 `pending_confirmation` 标记，未实现确认界面/流程）；
  - 持久化存储与并发处理（单 JSON 文件，无锁）；
  - 详见 `docs/03-evaluation.md`“失败与限制”与 `docs/05-retrospective.md`“下一步”。
