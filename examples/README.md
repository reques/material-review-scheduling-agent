# 示例索引

下表前七组输出由 `python3 scripts/generate_examples.py` 用 CLI（`--mock`）运行生成，非手写。每个目录含 `input.json`、`output.json`、`trace.json`；`05-duplicate` 另含两次运行的输出与第一次 Trace，`trace.json` 为第二次运行的 Trace。第八组是无需模型的本地清单。

| 目录 | 场景 | 关键结果 |
|---|---|---|
| `01-normal/` | M04，17:00（空闲） | `draft_saved`，建议 17:00，`pending_confirmation=false` |
| `02-missing-info/` | M02，17:00（缺标题+授权，补查仍缺失） | `blocked`，不保存草稿 |
| `03-rule-risk/` | M03，17:00（未授权+敏感） | `blocked`，不保存草稿 |
| `04-slot-conflict/` | M01，18:00（被占）→ 19:00 | `draft_saved`，建议 19:00，`pending_confirmation=true`，仅草稿 |
| `05-duplicate/` | M06，20:00，提交两次 | 同一 `draft_id`，第二次 `duplicate=true`，只一份草稿 |
| `06-save-failure/` | M06，20:00，模拟保存失败 | `save_failed`，无 `draft_id` |
| `07-changed-schedule/` | M01 第一次建议 19:00；随后 19:00 被占，再次提交 | `blocked`，`existing_draft` 指明旧草稿，旧草稿保留；两次 Trace 和最终草稿文件均在目录内 |
| `08-pending-list/` | 无草稿的待处理素材清单 | 返回素材状态与缺失字段；本地筛选不调用模型，无 Agent Trace |

`real-llm/20261105T075334688087Z/` 单独保存 DeepSeek `deepseek-flash` 两条真实模型运行的输入、输出、Trace 和元数据。`20261105T075237956775Z/` 是修正状态兼容问题前的首次运行记录，未覆盖。

`real-llm/20261105T091504252842Z/` 保存正常排期、规则风险、重复提交两次和模拟保存失败的真实模型运行；`real-llm/20261105T091737242095Z/07-changed-schedule/` 保存改变时段占用后的重复提交。各次运行附草稿快照及调用元数据，故障和业务数据均为本地模拟。

`real-llm/20261105T093722468190Z/` 是结果输出护栏调整后再次执行的冲突与信息缺失真实模型记录。

逐验收点对照见 `docs/03-evaluation.md`。
