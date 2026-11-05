# 03 — 评估

## 评估入口

```bash
python3 -m unittest discover -s tests -v
python3 scripts/generate_examples.py   # 或 sh scripts/generate_examples.sh，重新生成 examples/
```

测试 31 个，均为离线测试；其中模型 HTTP 客户端测试使用模拟响应，不代表真实模型运行。Windows 命令见 README，使用上述命令可重新运行。

## 逐验收点：预期 vs 实际

下表中的“实际”均为 Mock 模式下 CLI 真实运行的 `examples/` 输出（由 `scripts/generate_examples.py` 生成，非手写）。所有输出的 `published` 均为 `false`。

| 验收点 | 示例 | 预期 | 实际结果 |
|---|---|---|---|
| 1 正常排期 | `examples/01-normal/`（M04，17:00） | 空闲时段，保存草稿，不待确认 | `status=draft_saved`，`suggested_slot=17:00`，`pending_confirmation=false`，`draft_id=D-77c0c72d6dab`，`duplicate=false` |
| 2 信息缺失 | `examples/02-missing-info/`（M02，17:00） | 补查后仍缺失，阻塞，不保存 | `status=blocked`，风险：缺少版权/授权信息、缺少标题；`draft_saved=false`，`draft_id=null`；Trace 显示 `supplement_info` 返回 `still_missing=[title, license]` 后才阻塞 |
| 3 规则风险 | `examples/03-rule-risk/`（M03，17:00） | 阻塞级风险，阻塞，不保存 | `status=blocked`，风险：未授权转载、敏感内容标记；`draft_saved=false` |
| 4 时段冲突 | `examples/04-slot-conflict/`（M01，18:00） | 建议 19:00，待确认，仅草稿 | `status=draft_saved`，`suggested_slot=19:00`，`pending_confirmation=true`，`draft_id=D-4de8533c3e0f`；Trace：`query_schedule 18:00 occupied=true` → `query_schedule 19:00 occupied=false` → `save_draft` → `finish` |
| 5 重复提交 | `examples/05-duplicate/`（M06，20:00，两次） | 只产生一份草稿，同一 ID | `output_run1.json` 与 `output_run2.json` 的 `draft_id` 均为 `D-55682df65f2c`；第二次 `duplicate=true`；同一存储内只有一条记录（测试 `test_duplicate` 断言 `store.count()==1`） |
| 6 保存失败 | `examples/06-save-failure/`（M06，20:00，`--fail-save`） | 明确返回失败，无 ID | `status=save_failed`，`draft_saved=false`，`draft_id=null`，原因提示检查存储后重试 |

补充路径（非题目六点之外，体现分支差异）：M05（缺免责声明，补查返回声明）在 `tests/test_agent.py::test_missing_info_supplement_resolves` 中验证——补查成功后继续并保存草稿，与 M02“补查后仍缺失→阻塞”形成对照。

## 两条不同的 Mock 执行路径

- **冲突路径**（`examples/04-slot-conflict/trace.json`，6 步）：`get_material → check_rules（无风险）→ query_schedule 18:00（被占，观察到 19:00/20:00/21:00 空闲）→ query_schedule 19:00（验证空闲）→ save_draft（建议 19:00，待确认）→ finish`。模型根据“被占”观察改变了动作：没有直接保存请求时段，而是先验证替代时段。
- **缺失信息路径**（`examples/02-missing-info/trace.json`，4 步）：`get_material（缺失 title/license）→ supplement_info（仍缺失）→ check_rules（阻塞风险）→ finish（blocked，不保存）`。模型根据“补查失败”观察改变了动作：没有查询排期、没有保存草稿。

两条路径的工具序列、观察结果与终态均不同，且差异完全由工具返回驱动（见各 Trace 的 `tool_result_summary` 与 `decision_basis`）。

## 真实模型运行：2026-11-05

使用 DeepSeek API 返回的 `deepseek-flash`，每条路径单独使用临时草稿存储。运行目录为 `examples/real-llm/20261105T075334688087Z/`；每个子目录都包含输入、实际输出、Trace 和不含密钥的调用元数据。

- **时段冲突**：`01-slot-conflict/trace.json` 记录 7 次有效模型响应。模型在看到 18:00 被占后，先尝试保存 19:00，但被工具拒绝：19:00 尚未单独验证。模型观察拒绝结果后查询 19:00，确认空闲，再保存待确认草稿。`output.json` 为 `draft_saved`、`suggested_slot=19:00`、`pending_confirmation=true`、`published=false`。
- **信息缺失**：`02-missing-info/trace.json` 记录 4 次有效模型响应。模型读取 M02 后补查 title 和 license，补查未解决；规则检查返回两项阻塞风险，模型结束并阻塞，`draft_saved=false`。

首次真实运行记录在 `examples/real-llm/20261105T075237956775Z/`：模型给出 `status=draft`，工具实际保存成功，但当时输出状态未统一，说明文字也不恰当。随后增加基于保存观察的状态归一化和回归测试，重新运行得到上述结果；首次记录保留供评审。

发布状态输出与待处理清单改进后，重新执行了冲突和缺失信息两条真实模型路径，记录位于 `examples/real-llm/20261105T093722468190Z/`：分别为 `draft_saved`（19:00 待确认）和 `blocked`（缺少标题及授权），分别有 7 次和 4 次有效模型响应。其他历史真实记录反映运行当时的代码和输出，不会回写。

其他四类验收场景的真实模型运行位于 `examples/real-llm/20261105T091504252842Z/`；每次调用分别记录输入、输出、Trace、模型元数据及执行后草稿快照。除重复提交的两次运行共用存储外，每个场景使用独立临时草稿存储：

| 验收场景 | 路径 | 实际结果 |
|---|---|---|
| 正常排期 | `03-normal/run1/` | M04 的 17:00 空闲，保存草稿 `D-77c0c72d6dab`，不待确认；5 次有效模型响应。 |
| 规则风险 | `04-rule-risk/run1/` | M03 命中未授权转载和敏感内容两项阻塞风险；`blocked`，草稿数为 0；3 次有效模型响应。 |
| 重复提交 | `05-duplicate/run1/` 和 `run2/` | 两次返回同一草稿 `D-55682df65f2c`，第二次 `duplicate=true`，两次快照均只有一条草稿；各 5 次有效模型响应。 |
| 保存失败 | `06-save-failure/run1/` | 本地存储工具注入模拟写入失败，模型尝试两次保存后报告失败；最终 `save_failed`，无草稿 ID，草稿数为 0；6 次有效模型响应。 |

另外，题目特别要求检查“更换占用时段并重复提交”：`examples/real-llm/20261105T091737242095Z/07-changed-schedule/` 的第一次运行建议 19:00 并保存待确认草稿；第二次将 19:00 设为被占用，模型请求改到 20:00，工具发现旧草稿冲突，最终 `blocked` 并返回旧草稿信息；前后快照均只保留同一份旧草稿，等待人工处理。两次分别有 7 次和 5 次有效模型响应。这里的排期变更及所有业务数据均为本地模拟，不是真实发布服务。

## 护栏与上限的验证

- `test_guards_publish_claim`：声称 `published` 的模型负载被降级，`draft_id` 被清除（无真实保存观察），`guard_corrections` 有记录。
- `test_guards_hard_requirement_flag`：建议时段被改而未标记待确认时，护栏强制 `pending_confirmation=true`。
- `test_guards_blocked_risk_no_draft`：阻塞风险观察下，草稿声称被置为 `blocked`。
- `test_step_cap`：永不 finish 的桩 LLM 在 `max_steps=3` 时返回 `incomplete`，不声称草稿。
- `test_tool_validation`：未知工具/坏参数返回 error 观察，不抛异常。
- `TestSafetyAndState`：验证不同草稿的时段冲突、写入前风险与确认检查、时段再次检查、真实写入异常、步数上限后的保存状态和发布声称过滤。
- `examples/07-changed-schedule/`：首次建议 19:00，随后将 19:00 设为被占并再次提交；结果明确报告旧草稿冲突，保留原草稿供人工处理。
- `tests/test_pending_and_output.py`：验证待处理状态、草稿与冲突分类、无模型查询、异常存储，以及模型虚报发布时最终输出不透传自由文本。待处理清单示例见 `examples/08-pending-list/`；该入口不调用模型，没有 Agent Trace。

## 失败与限制（诚实记录）

1. **Mock 边界**：七组基础示例由启发式 `MockLLM` 生成，仅验证流程；真实模型运行记录单独放在 `examples/real-llm/`。这些单次样本不能证明模型在所有输入和后端上的表现。
2. **数据规模**：合成数据只有 6 个素材、13 个时段；`query_schedule` 的“附近空闲时段”按整点向后扫描，未处理分钟级粒度与跨日排期。
3. **无人工确认环节**：`pending_confirmation` 只是结果标记，本项目没有实现“用户点确认后才发布”的交互步骤；真实发布动作本身也不存在，这是设计上的安全边界，不是待修复的 bug。
4. **存储**：草稿存储为单 JSON 文件，无并发锁；仅适合单机演示与测试。
5. **真实模型覆盖范围**：六类验收场景和变更占用后重复提交均已用一个 DeepSeek 模型各运行；模型判断为真实调用，业务工具、数据和保存故障为本地模拟，不能推广到其他模型或所有实际故障。
6. **状态维护**：待处理清单依据数据维护者填写的 `work_status`，不会从素材内容自动识别是否已完成，也不会自动更新该字段。
