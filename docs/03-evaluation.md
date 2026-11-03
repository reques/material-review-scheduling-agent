# 03 — 评估

## 评估入口

```bash
python3 -m unittest discover -s tests -v
python3 scripts/generate_examples.py   # 或 sh scripts/generate_examples.sh，重新生成 examples/
```

测试 13 个，全部通过（实际运行结果见仓库根 README 的验证记录）。

## 逐验收点：预期 vs 实际

下表中的“实际”均为 Mock 模式下 CLI 真实运行的 `examples/` 输出（由 `scripts/generate_examples.py` 生成，非手写）。所有输出的 `published` 均为 `false`。

| 验收点 | 示例 | 预期 | 实际结果 |
|---|---|---|---|
| 1 正常排期 | `examples/01-normal/`（M04，17:00） | 空闲时段，保存草稿，不待确认 | `status=draft_saved`，`suggested_slot=17:00`，`pending_confirmation=false`，`draft_id=D-77c0c72d6dab`，`duplicate=false` |
| 2 信息缺失 | `examples/02-missing-info/`（M02，17:00） | 补查后仍缺失，阻塞，不保存 | `status=blocked`，风险：缺少版权/授权信息、缺少标题；`draft_saved=false`，`draft_id=null`；Trace 显示 `supplement_info` 返回 `still_missing=[title, license]` 后才阻塞 |
| 3 规则风险 | `examples/03-rule-risk/`（M03，17:00） | 阻塞级风险，阻塞，不保存 | `status=blocked`，风险：未授权转载、敏感内容标记；`draft_saved=false` |
| 4 时段冲突 | `examples/04-slot-conflict/`（M01，18:00） | 建议 19:00，待确认，仅草稿 | `status=draft_saved`，`suggested_slot=19:00`，`pending_confirmation=true`，`draft_id=D-4de8533c3e0f`；Trace：`query_schedule 18:00 occupied=true` → `query_schedule 19:00 occupied=false` → `save_draft` → `finish` |
| 5 重复提交 | `examples/05-duplicate/`（M06，20:00，两次） | 只产生一份草稿，同一 ID | `output_run1.json` 与 `output_run2.json` 的 `draft_id` 均为 `D-55682df65f2c`；第二次 `duplicate=true`；同一存储内只有一条记录（测试 `test_duplicate` 断言 `store.count()==1`） |
| 6 保存失败 | `examples/06-save-failure/`（M06，20:00，`--fail-save`） | 明确返回失败，无 ID | `status=save_failed`，`draft_saved=false`，`draft_id=null`，`reason=保存草稿失败：save_failed` |

补充路径（非题目六点之外，体现分支差异）：M05（缺免责声明，补查返回声明）在 `tests/test_agent.py::test_missing_info_supplement_resolves` 中验证——补查成功后继续并保存草稿，与 M02“补查后仍缺失→阻塞”形成对照。

## 两条 visibly 不同的执行路径

- **冲突路径**（`examples/04-slot-conflict/trace.json`，6 步）：`get_material → check_rules（无风险）→ query_schedule 18:00（被占，观察到 19:00/20:00/21:00 空闲）→ query_schedule 19:00（验证空闲）→ save_draft（建议 19:00，待确认）→ finish`。模型根据“被占”观察改变了动作：没有直接保存请求时段，而是先验证替代时段。
- **缺失信息路径**（`examples/02-missing-info/trace.json`，4 步）：`get_material（缺失 title/license）→ supplement_info（仍缺失）→ check_rules（阻塞风险）→ finish（blocked，不保存）`。模型根据“补查失败”观察改变了动作：没有查询排期、没有保存草稿。

两条路径的工具序列、观察结果与终态均不同，且差异完全由工具返回驱动（见各 Trace 的 `tool_result_summary` 与 `decision_basis`）。

## 护栏与上限的验证

- `test_guards_publish_claim`：声称 `published` 的模型负载被降级，`draft_id` 被清除（无真实保存观察），`guard_corrections` 有记录。
- `test_guards_hard_requirement_flag`：建议时段被改而未标记待确认时，护栏强制 `pending_confirmation=true`。
- `test_guards_blocked_risk_no_draft`：阻塞风险观察下，草稿声称被置为 `blocked`。
- `test_step_cap`：永不 finish 的桩 LLM 在 `max_steps=3` 时返回 `incomplete`，不声称草稿。
- `test_tool_validation`：未知工具/坏参数返回 error 观察，不抛异常。

## 失败与限制（诚实记录）

1. **Mock 边界（最重要）**：全部 `examples/` Trace 由 `MockLLM` 生成，其决策是读取提示词历史的启发式规则，仅证明“循环、工具、护栏、幂等”流程可跑通，**不证明真实模型在同样提示词下会做出同样决策**。未进行真实模型运行（本次构建未使用任何真实密钥），因此没有真实模型 Trace；下一步须用真实密钥跑同一批示例并对比（见 `docs/05-retrospective.md`）。
2. **数据规模**：合成数据只有 6 个素材、13 个时段；`query_schedule` 的“附近空闲时段”按整点向后扫描，未处理分钟级粒度与跨日排期。
3. **无人工确认环节**：`pending_confirmation` 只是结果标记，本项目没有实现“用户点确认后才发布”的交互步骤；真实发布动作本身也不存在，这是设计上的安全边界，不是待修复的 bug。
4. **存储**：草稿存储为单 JSON 文件，无并发锁；仅适合单机演示与测试。
5. **真实 LLM 客户端未做端到端验证**：`OpenAICompatibleClient` 的代码已写并可做 JSON 解析单元测试覆盖的解析函数，但因无密钥，未实际调用任何真实 API；`--llm real` 路径的 HTTP 行为未经验证，使用前须先以真实密钥试跑。
