# 示例索引

以下输出均由 `python3 scripts/generate_examples.py` 用 CLI（`--mock`）真实运行生成，非手写。每个目录含 `input.json`、`output.json`、`trace.json`；`05-duplicate` 另含两次运行的输出（`output_run1.json` / `output_run2.json`）与第一次 Trace（`trace_run1.json`），`trace.json` 为第二次运行的 Trace。

| 目录 | 场景 | 关键结果 |
|---|---|---|
| `01-normal/` | M04，17:00（空闲） | `draft_saved`，建议 17:00，`pending_confirmation=false` |
| `02-missing-info/` | M02，17:00（缺标题+授权，补查仍缺失） | `blocked`，不保存草稿 |
| `03-rule-risk/` | M03，17:00（未授权+敏感） | `blocked`，不保存草稿 |
| `04-slot-conflict/` | M01，18:00（被占）→ 19:00 | `draft_saved`，建议 19:00，`pending_confirmation=true`，仅草稿 |
| `05-duplicate/` | M06，20:00，提交两次 | 同一 `draft_id`，第二次 `duplicate=true`，只一份草稿 |
| `06-save-failure/` | M06，20:00，模拟保存失败 | `save_failed`，无 `draft_id` |

逐验收点对照见 `docs/03-evaluation.md`。
