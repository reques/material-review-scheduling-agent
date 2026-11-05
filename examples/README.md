# 示例索引

`examples/` 里的 `01`–`07` 由 `python3 scripts/generate_examples.py` 用 CLI（`--mock`）真实运行生成，不是手写。每个目录含 `input.json`、`output.json`、`trace.json`；`05-duplicate` 另含两次运行的输出和第一次 Trace，`trace.json` 是第二次运行的 Trace；`07-changed-schedule` 含两次运行和最终草稿快照。

`08-pending-list` 是无需模型的本地清单，只有输入和输出，没有 Agent Trace。

| 目录 | 场景 | 关键结果 |
|---|---|---|
| `01-normal/` | M04，17:00（空闲） | `draft_saved`，建议 17:00，`pending_confirmation=false` |
| `02-missing-info/` | M02，17:00（缺标题+授权，补查仍缺失） | `blocked`，不保存草稿 |
| `03-rule-risk/` | M03，17:00（未授权+敏感） | `blocked`，不保存草稿 |
| `04-slot-conflict/` | M01，18:00（被占）→ 19:00 | `draft_saved`，建议 19:00，`pending_confirmation=true`，仅草稿 |
| `05-duplicate/` | M06，20:00，提交两次 | 同一 `draft_id`，第二次 `duplicate=true`，只一份草稿 |
| `06-save-failure/` | M06，20:00，模拟保存失败 | `save_failed`，无 `draft_id` |
| `07-changed-schedule/` | M01 第一次建议 19:00；随后 19:00 被占，再次提交 | `blocked`，`existing_draft` 指明旧草稿，旧草稿保留 |
| `08-pending-list/` | 无草稿的待处理素材清单 | 返回素材状态与缺失字段；不调用模型，无 Agent Trace |

`test-results.txt` 是本次 `python -m unittest discover -s tests -v` 的终端输出，31 项通过。

`real-llm/` 是真实模型运行记录，索引见 `real-llm/README.md`。其中：

- `20261105T075237956775Z/` 是第一次真实运行，状态写成 `draft`，保留作失败记录；
- `20261105T075334688087Z/` 是修正状态后的冲突和缺失信息；
- `20261105T091504252842Z/` 覆盖正常、规则风险、重复提交、保存失败；
- `20261105T091737242095Z/07-changed-schedule/` 覆盖更换占用时段后重复提交；
- `20261105T093722468190Z/` 是输出护栏调整后的冲突和缺失信息复核。

## 一个容易被误读的地方

`07-changed-schedule/trace.json` 的最后一步，模型自己写的 `status` 是 `save_failed`；但工具实际返回的是 `existing_draft_conflict`，`src/guards.py::assemble_result` 会把最终结果改成 `blocked`，并带回 `existing_draft`。所以 `output.json` 是 `blocked`，不是 `save_failed`。

这不是 Trace 写错了，而是护栏在纠正模型的结果。`output.json` 才是最终结果，Trace 保留模型的原始说法，方便对照。

逐验收点对照见 `docs/03-evaluation.md`。
