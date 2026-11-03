# 04 — AI 使用说明

## 使用范围（诚实记录）

本项目在一次本地构建会话中由 AI 辅助完成脚手架、代码、测试、示例生成与文档撰写。具体包括：

- AI 触及的文件：全部代码（`src/`）、测试（`tests/`）、数据（`data/`）、示例生成脚本（`scripts/`）、文档（`docs/`、`README.md`）与配置（`requirements.txt`、`.env.example`、`.gitignore`）。
- AI 未触及/未执行的操作：未推送到 GitHub、未创建 GitHub 仓库、未使用任何真实 API 密钥、未调用任何真实模型 API。

## 人工必须验证的内容

构建者/评审人须自行验证以下事项，AI 的陈述不能代替验证：

1. 运行测试：`python3 -m unittest discover -s tests -v`，确认 13 个测试全部通过；
2. 阅读护栏代码：`src/guards.py`（`assemble_result` 与两个断言函数），确认“已发布”声称与“悄悄改变硬性要求”确实在代码中被拦截，而不是只在文档中承诺；
3. 检查 Trace：打开 `examples/04-slot-conflict/trace.json` 与 `examples/02-missing-info/trace.json`，确认步骤、工具参数、返回摘要与决策依据真实对应，且 M01 的替代时段 19:00 来自工具观察而非模型自创；
4. 复现示例：运行 `python3 scripts/generate_examples.py`，确认 `examples/` 输出可重新生成且与提交内容一致；
5. 检查无密钥：全树 grep 密钥/隐私数据，确认无真实密钥（见 README 验证记录）。

## Mock 边界声明

- 本项目**没有使用真实 LLM 密钥**，所有示例 Trace 均由 `MockLLM`（`src/llm.py`）生成。
- `MockLLM` 读取提示词中的工具观察结果并按代码中的启发式规则选择下一步动作；它的 Trace 只证明 ReAct 循环、工具调用、护栏与幂等逻辑可跑通，**不证明真实模型的决策效果**。
- 真实模型运行时，须配置 `.env`（见 `.env.example`）并使用 `--llm real`；真实运行的 Trace 应另行保存并与 Mock Trace 分开标注，不得混为一谈。

## 实际用时与未完成部分

- 实际用时：一次本地构建会话完成（未按分钟计时，不虚构精确小时数；题目建议投入为 3 小时，本次构建在一个会话内完成核心链路，未超出建议量级的工作量感知）。
- 未完成/未验证部分：
  - 真实模型端到端运行（无密钥，未验证 `--llm real` 的 HTTP 路径）；
  - 人工确认交互步骤（仅以 `pending_confirmation` 标记，未实现确认界面/流程）；
  - 持久化存储与并发处理（单 JSON 文件，无锁）；
  - 详见 `docs/03-evaluation.md`“失败与限制”与 `docs/05-retrospective.md`“下一步”。
