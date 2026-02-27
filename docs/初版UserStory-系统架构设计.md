# 初版 User Story（用于系统架构设计）

## 范围与目标
本阶段仅建设“无玩家介入”的故事演化系统，围绕 `Narrator（叙述者）-角色Agent-世界状态` 形成可持续演化闭环；强调信息隔离、物候硬约束、成本可控和可重放。

## 关键角色
- `Narrator`：唯一调度与裁定权威（时间粒度、信息分发、执行许可、fallback裁定、存档）。
- `Agent LLM Layer`：生成角色行动意图与叙述文本，不直接改写世界状态。
- `规则结算器（半确定性）`：由 Narrator 裁定是否放行；放行后用确定性机制打包上下文并交给无状态 `DM Agent` 出结果。
- `DM Agent（无状态）`：基于输入上下文单次产出结算结果，不持有会话状态。
- `Persistence`：记录时间线、行动、结算、拒绝重试与 fallback 标记。

## User Stories（初版）

| ID | User Story | 验收标准（Given/When/Then） |
|---|---|---|
| US-01 | 作为叙述者，我希望每轮先决定叙事粒度（年/月/日/即时）并说明理由，以便在效率与细节之间动态平衡。 | Given 新一轮开始；When Narrator 选定粒度；Then 必须写入“粒度+理由+当前tick区间”。 |
| US-02 | 作为系统设计者，我希望底层以 `Global Tick` 推进时间，以便不同粒度叙事不撕裂时间线。 | Given 任意粒度轮次；When 轮次结算完成；Then 世界时间以 tick 单调推进且可回放一致。 |
| US-03 | 作为角色Agent，我希望只接收自己可见信息，以便满足信息隔离。 | Given 事件涉及多角色；When Narrator 分发上下文；Then 角色仅收到授权事实与可推断线索。 |
| US-04 | 作为系统运营者，我希望角色按 `ACTIVE/PASSIVE/DORMANT` 三态执行，以便控制 LLM 调用成本。 | Given 每tick角色筛选；When 进入执行阶段；Then 仅 `ACTIVE` 触发 LLM，其他状态走规则更新或纯时间推进。 |
| US-05 | 作为叙述者，我希望先裁定角色意图是否允许执行，以便拦截明显不合理或严重背离故事机制的动作。 | Given Agent 产出意图；When Narrator 审核；Then 结果必须为 `APPROVED` 或 `REJECTED` 且记录原因码。 |
| US-06 | 作为结算系统，我希望在 `APPROVED` 后通过确定性机制打包上下文并调用无状态 DM Agent，以便获得可审计、可复算的执行结果。 | Given 意图已放行；When 触发结算；Then 输入包包含角色状态、世界状态、规则快照、随机种子，DM Agent 返回结构化结果。 |
| US-07 | 作为鲁棒性机制，我希望在 `REJECTED` 时由 Agent LLM Layer 直接重试，以便尽量得到可执行动作。 | Given 当前意图被拒绝；When 未达到最大重试次数；Then 系统发起重试并保留每次拒绝原因与版本链路。 |
| US-08 | 作为叙述者，我希望在多次拒绝后生成 fallback 行动及结果，并在数据库标记 fallback，以便流程不中断且后续可追溯。 | Given 达到重试上限仍拒绝；When Narrator 触发兜底；Then 写入 `fallback=true`、`fallback_reason`、`fallback_action`、`fallback_result`。 |
| US-09 | 作为世界引擎，我希望物候以硬规则影响资源/疾病/迁徙/冲突概率，以便其成为真实因果而非文案装饰。 | Given tick 推进；When 物候更新；Then 至少影响一个可量化状态字段并参与后续结算。 |
| US-10 | 作为调试与运营人员，我希望所有关键流程可重放与审计，以便定位叙事异常和规则缺陷。 | Given 任一历史轮次；When 使用同 seed 重放；Then 关键状态与结算路径一致，并可查询拒绝/重试/fallback 全链路日志。 |

## 补充约束（已按改动更新）
- 规则结算器由“全确定性裁决”调整为“半确定性裁决”：`Narrator裁定 + 确定性打包 + 无状态DM执行`。
- `REJECTED` 不进入 DM 执行，先走 Agent LLM 重试。
- 连续拒绝超过阈值后，必须由 Narrator 产出 fallback，并落库标记该次为 fallback 结算。
