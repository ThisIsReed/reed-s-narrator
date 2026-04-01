# 前端第一期只读模型边界

## 目的
前端第一期只依赖 CLI 输出的稳定只读模型，不直接解析 demo 文本，不直接绑定 SQLite 表结构。

## 允许依赖的四类数据

### 1. 运行列表
- 来源：`narrator run --json`
- 用途：展示一次正式运行的结果摘要。
- 稳定字段：
  - `command`
  - `db`
  - `max_ticks`
  - `checkpoint_interval`
  - `ticks_run`
  - `final_tick`
  - `final_granularity`
  - `checkpoint_ticks`
  - `snapshot_ticks`
  - `last_event_ids`
  - `last_active_character_ids`

### 2. Tick 列表
- 来源：`narrator replay --json list --source <checkpoint|snapshot>` 或 `narrator inspect --json ticks --source <checkpoint|snapshot>`
- 用途：驱动回放时间线、tick 选择器和回放列表。
- 稳定字段：
  - `command`
  - `db`
  - `source`
  - `ticks`
  - `count`

### 3. Tick 审计
- 来源：`narrator inspect --json audit --tick <n>`
- 用途：展示单个 tick 的阶段审计、事件列表和主动角色列表。
- 稳定字段：
  - `command`
  - `db`
  - `tick`
  - `audit.tick`
  - `audit.event_ids`
  - `audit.action_character_ids`
  - `audit.pending_propagation`
  - `audit.stages`

### 4. 叙事摘要
- 来源：`narrator narrate --json --rules-only --from-tick <a> --to-tick <b>`
- 用途：展示回合摘要和叙事回放正文。
- 稳定字段：
  - `command`
  - `db`
  - `source`
  - `ticks`
  - `rules_only`
  - `entries[].tick`
  - `entries[].title`
  - `entries[].summary_text`
  - `entries[].source_refs`
  - `entries[].mentioned_character_ids`
  - `entries[].mentioned_event_ids`

## 当前不建议前端依赖的内容
- `demo.py` 的富文本输出。
- SQLite 原始表名、字段名和 join 关系。
- 任何未通过 `--json` 暴露的 CLI 文本格式。
- LLM 模式下可能变化的叙述风格字段。

## 联调原则
- 前端第一期只做只读能力，不写回世界状态。
- 如果需要新增读模型，优先扩展 CLI JSON 契约，而不是让前端绕过 CLI 直接查库。
- 若 JSON schema 发生变化，必须先更新 [`TODO.md`](./TODO.md) 与 [`changelog.md`](./changelog.md)。
