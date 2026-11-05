# 03 评估记录

## 我怎么跑

先跑离线测试：

```bash
python3 -m unittest discover -s tests -v
```

这次复核用的是 Windows + Python 3.13.5。仓库里最早记录的是 Python 3.12.7 / 3.12.9；项目只用了标准库，没有依赖新的语法特性，31 项测试在 3.13.5 上也全部通过。实际终端输出保存在 `examples/test-results.txt`，不是手写的"测试通过"四个字。

再跑示例：

```bash
python3 scripts/generate_examples.py
```

这个脚本用 CLI 的 `--mock` 真实执行，把 `output.json` 和 `trace.json` 写回 `examples/`。我这次重新生成了一遍，和仓库里的文件逐项比对（忽略 `created_at` 时间戳），没有内容差异，说明示例不是手写摆拍，能重复生成。

## 六个验收点：预期和实际

下表中的"实际"都来自 `examples/` 里的真实 CLI 输出。

| # | 验收点 | 示例 | 预期 | 实际结果 |
|---|---|---|---|---|
| 1 | 正常排期 | `examples/01-normal/`（M04，17:00） | 空闲时段，保存草稿，不待确认 | `status=draft_saved`，建议 17:00，`pending_confirmation=false`，`draft_id=D-77c0c72d6dab` |
| 2 | 信息缺失 | `examples/02-missing-info/`（M02，17:00） | 补查后仍缺失，阻塞，不保存 | `status=blocked`，风险为缺少版权/授权、缺少标题；`draft_saved=false`，`draft_id=null`；Trace 显示 `supplement_info` 返回 `still_missing=[title, license]` 后才阻塞 |
| 3 | 规则风险 | `examples/03-rule-risk/`（M03，17:00） | 阻塞级风险，阻塞，不保存 | `status=blocked`，风险为未授权转载、敏感内容标记；`draft_saved=false` |
| 4 | 时段冲突 | `examples/04-slot-conflict/`（M01，18:00） | 建议 19:00，待确认，仅草稿 | `status=draft_saved`，建议 19:00，`pending_confirmation=true`，`draft_id=D-4de8533c3e0f` |
| 5 | 重复提交 | `examples/05-duplicate/`（M06，20:00，两次） | 同一份草稿，同一 ID | `output_run1.json` 和 `output_run2.json` 的 `draft_id` 都是 `D-55682df65f2c`；第二次 `duplicate=true`；测试 `test_duplicate` 断言存储里只有一条记录 |
| 6 | 保存失败 | `examples/06-save-failure/`（M06，20:00，`--fail-save`） | 明确失败，无 ID | `status=save_failed`，`draft_saved=false`，`draft_id=null`，草稿数为 0 |

补充两个场景：

- `examples/07-changed-schedule/`：第一次建议 19:00 并保存待确认草稿；随后把 19:00 改成被 OTHER 占用，再次提交同一请求。第二次不会覆盖旧草稿，结果是 `blocked`，并返回 `existing_draft`（旧草稿 ID 和 19:00）。`trace.json` 最后一步模型自己写的是 `save_failed`，但工具观察是 `existing_draft_conflict`，护栏把最终结果改成 `blocked`；`output.json` 才是最终结果。
- `examples/08-pending-list/`：`--list-pending` 不调用模型，直接列出待处理素材、缺失字段、草稿和冲突状态。它没有 Agent Trace，因为这里本来就没有 Agent。

## 两条执行路径

题目要求至少两条执行记录，能看出模型根据不同的工具结果调整动作。我选的是冲突路径和缺失信息路径。

### 冲突路径

`examples/04-slot-conflict/trace.json`，6 步：

```text
get_material(M01)
→ check_rules(M01)          无风险
→ query_schedule(18:00)     被占，观察到 19:00 / 20:00 / 21:00 空闲
→ query_schedule(19:00)     单独验证为空闲
→ save_draft(建议 19:00，待确认)
→ finish(draft_saved)
```

关键在于第 3 步到第 4 步：模型没有直接保存 18:00，也没有把"附近空闲"当成"已验证空闲"，而是先单独查了 19:00。这个动作是 `query_schedule` 的返回结果驱动的。

### 缺失信息路径

`examples/02-missing-info/trace.json`，4 步：

```text
get_material(M02)           缺失 title / license
→ supplement_info(M02)      补查后仍缺失
→ check_rules(M02)          两项 block 级风险
→ finish(blocked，不保存)
```

这条路径里没有 `query_schedule`，也没有 `save_draft`。模型看到补查失败和阻塞风险后改变了动作，不是按固定模板继续往下走。

两条路径的工具序列、观察结果和终态都不同。Trace 里每一步都有 `action_input`、`tool_result_summary`、`decision_basis` 和 `next`，足够看出"收到了什么、做了什么、为什么"。

## 真实模型运行

2026-11-05 用 DeepSeek 的 `deepseek-flash` 跑了真实模型。模型调用、工具执行和草稿保存都是真的；业务数据、排期和保存失败故障是本地模拟。每次运行都有 `metadata.json`，记录 API 主机、请求的模型、API 返回的模型名、调用次数和有效响应数，没有密钥。目录索引见 `examples/real-llm/README.md`。

### 第一次并不好看

第一次运行在 `examples/real-llm/20261105T075237956775Z/`。模型在冲突场景里把最终状态写成了 `draft`，工具其实已经保存成功，但输出状态不符合约定。这个记录我没有删，也没有改，留在仓库里。

后来加了"以真实保存观察归一化状态"的逻辑，并补了回归测试，重新跑出 `20261105T075334688087Z/`：冲突场景变成 `draft_saved`、建议 19:00、待确认；缺失信息场景是 `blocked`、不保存。

### 六类验收和变更占用

`20261105T093722468190Z/01-slot-conflict/` 的 7 步里，第 4 步模型直接保存 19:00，被工具以 `guard_rejected` 拒绝，因为 19:00 还没有单独验证；第 5 步它改去 `query_schedule(19:00)`，第 6 步再保存成功。这是真实模型根据工具结果改变动作的直接证据，不是预设流程。

- `20261105T091504252842Z/` 覆盖正常排期、规则风险、重复提交和保存失败：
  - 正常排期：M04 的 17:00 空闲，保存 `D-77c0c72d6dab`，5 次有效响应；
  - 规则风险：M03 命中未授权转载和敏感内容，`blocked`，0 份草稿，3 次有效响应；
  - 重复提交：两次都返回 `D-55682df65f2c`，第二次 `duplicate=true`，两次快照都只有一条草稿，各 5 次有效响应；
  - 保存失败：模型尝试保存，工具返回 `save_failed`，最终 `save_failed`，无草稿 ID，6 次有效响应。
- `20261105T091737242095Z/07-changed-schedule/` 覆盖"更换占用时段并重复提交"：第一次建议 19:00 并保存；第二次 19:00 被占，模型改建议 20:00，工具返回 `existing_draft_conflict`，最终 `blocked` 并返回旧草稿。两次分别 7 次和 5 次有效响应，前后快照都只有同一份旧草稿。
- `20261105T093722468190Z/` 是结果输出护栏调整后的复核：冲突 7 次有效响应、结果 `draft_saved`；缺失信息 4 次有效响应、结果 `blocked`。

这里有一个历史记录的差异要说明：`20261105T091737242095Z/07-changed-schedule/run2/output.json` 里的 `risk_reasons` 还是模型给的字符串（如 `requested_slot_18:00_occupied_by_M00`），因为那次运行早于最终的文本控制改动。当前代码会改用工具观察生成的原因（`已有草稿与当前建议时段不一致`）。历史记录保留原样，不回写；`093722468190Z/` 的记录反映了当前行为。

## 护栏和上限的验证

离线测试里专门覆盖了这些：

- `test_guards_publish_claim`：模型声称 `published` 时被降级，假的 `draft_id` 被清掉；
- `test_guards_hard_requirement_flag`：建议时段改了但没标待确认时，被强制补上；
- `test_guards_blocked_risk_no_draft`：有 block 级风险时，草稿声称被置为 `blocked`；
- `test_step_cap`：永不 `finish` 的桩 LLM 在 `max_steps=3` 时返回 `incomplete`；
- `test_tool_validation`：未知工具和坏参数返回 error 观察，不抛异常；
- `TestSafetyAndState`：不同素材不共享草稿时段、旧草稿冲突不覆盖、写入前风险和确认检查、写入时二次检查时段、真实写入异常、步数上限后保留已保存状态、模型自由文本不透传；
- `tests/test_pending_and_output.py`：待处理状态、草稿与冲突分类、无模型查询、坏存储、模型虚报发布时最终输出不透传。

这些测试都是离线的，不依赖网络和真实密钥。测试结果见 `examples/test-results.txt`。

## 这次复核额外检查了什么

下面这些是提交前这轮复核实际执行过的，命令由 AI 跑，结果记录在这里：

- 用 `python -m src.cli` 实际跑了正常、冲突、缺失、规则风险、保存失败五条命令，退出码都是 0；参数错误才是 2。
- 重新生成 `examples/`，确认输出可复现。
- 扫了一遍仓库里的文本，没有 `sk-` 开头的密钥、`Bearer` 令牌、邮箱或本机绝对路径；`.env` 只在本地，`.gitignore` 已覆盖。
- `data/` 里全部是虚构素材和规则，`M00` 只是 18:00 的占用来历，没有真实内容。
- GitHub 仓库已推送；最终 commit SHA 见提交表（本文件不记录自身 SHA，避免自引用）。

## 失败和限制

1. **Mock 不是模型证据**：七个基础示例用启发式 `MockLLM` 生成，只验证流程。真实模型记录单独放在 `examples/real-llm/`，单次样本也不能代表所有输入和模型。
2. **数据规模小**：6 个素材、13 个整点时段；`query_schedule` 的"附近空闲时段"按整点向后扫，没有处理分钟级粒度和跨日排期。
3. **没有人工确认交互**：`pending_confirmation` 只是结果标记，没有"用户点确认后才继续"的流程。这是范围外的设计边界，不是 bug。
4. **存储不是生产级**：单 JSON 文件，没有并发锁；同时提交两个请求时，冲突检查和写入不是原子的。
5. **真实模型覆盖有限**：六类验收和变更占用都用同一个 DeepSeek 模型跑过，没有换模型、没有重复多次，稳定性不能下结论。
6. **状态靠人工维护**：`work_status` 是数据维护者填的，不会因为保存草稿自动变成"已处理"，也不会从内容自动识别。
7. **历史记录不回写**：早期真实模型记录反映当时的代码和输出；`07` 的 run2 是其中一个例子。当前行为以 `093722468190Z/` 和代码为准。
