# TODO

> 文档定位：本文件维护“当前迭代最直接的执行待办、优先级、状态与收口标准”。  
> 它不替代 [`系统架构设计方案.md`](./系统架构设计方案.md)、[`系统架构工作包拆分.md`](./系统架构工作包拆分.md) 或 [`changelog.md`](./changelog.md)；而是把它们收敛为当前最该做的少数事项。

## 1. 当前判断

### 1.1 项目阶段
- 当前仓库已从“模拟内核已成形，CLI 产品面未收口”推进到“CLI MVP 已收口，可支撑前端只读联调”。
- 以“后端/引擎是否可运行”为口径，当前完成度约为 `75% ~ 85%`。
- 以“CLI 是否基本完成、可以支持前端开始开发”为口径，当前完成度已提升到 `85% ~ 90%`。

### 1.2 已有基础
- 主循环、持久化、checkpoint、snapshot、replay、narrate、demo 与正式 `run` 已具备可运行基础。
- `pytest tests/unit -q` 已通过，结果为 `94 passed in 4.79s`。
- 统一 CLI 入口、`--json` 契约、正式 runtime、tick audit inspect 与端到端 CLI 集成测试已落地。

### 1.3 当前结论
- 当前这轮 CLI MVP 收口已完成，可在只读边界内启动前端开发。
- 前端仍不应绕过 CLI JSON 契约直接绑定 demo 文本或 SQLite 细节。

## 2. 目标与非目标

### 2.1 本轮目标
- 形成统一 CLI 入口。
- 提供前端可依赖的机器可读输出。
- 补齐正式 `run` 命令，支持真实模拟运行而不是只跑 demo。
- 建立一条正式 CLI 的端到端集成验证链路。

### 2.2 本轮非目标
- 不在本轮优先扩展更复杂的传播增强、运营可观测性或更重的前端能力。
- 不把 demo 场景继续膨胀为临时产品接口。
- 不为“先跑起来”引入新的 silent fallback、mock 成功路径或隐式降级。

## 3. 优先级待办

状态说明：
- `TODO`：未开始
- `DOING`：进行中
- `BLOCKED`：受阻
- `DONE`：已完成

| ID | 优先级 | 状态 | 事项 | 目的 | 主要落点 | 完成标准 |
|---|---|---|---|---|---|---|
| CLI-MVP-01 | P0 | DONE | 建立统一 CLI 入口 | 让 `run / replay / narrate / inspect` 收敛到同一产品面 | `src/narrator/main.py`, `scripts/run.py`, `pyproject.toml` | 统一子命令可用，参数风格一致，现有脚本不再是唯一入口 |
| CLI-MVP-02 | P0 | DONE | 为 CLI 定义稳定机器可读输出 | 让前端依赖 JSON 契约而不是解析文本 | `src/narrator/main.py`, `src/narrator/replay.py`, `src/narrator/narrate.py` | 至少 `run / replay / narrate` 支持 `--json`，schema 在文档中明确 |
| CLI-MVP-03 | P0 | DONE | 补正式 `run` 命令 | 让用户能基于真实配置推进模拟并产出可回放结果 | `src/narrator/main.py`, `src/narrator/orchestrator/`, `src/narrator/persistence/` | 支持指定 `db / max_ticks / checkpoint_interval / config`，运行后可直接 replay 和 narrate |
| CLI-MVP-04 | P1 | DONE | 拆分 demo 装配与正式 runtime 装配 | 避免 MVP 入口继续绑定 demo 逻辑 | `src/narrator/demo_support.py`, `src/narrator/demo_runtime.py` | demo 场景数据与正式 builder 解耦，正式 CLI 不依赖 demo runtime |
| CLI-MVP-05 | P1 | DONE | 补正式 CLI 端到端集成测试 | 防止前端未来依赖的入口没有回归保障 | `tests/integration/` | 存在一条 `run -> replay -> narrate` 全链路测试 |
| CLI-MVP-06 | P1 | DONE | 补 CLI 包装与文档 | 降低使用成本，避免入口分裂 | `pyproject.toml`, `README.md`, `docs/README.md` | console scripts 完整，README 能说明 MVP 使用方式和 JSON 输出 |
| CLI-MVP-07 | P2 | DONE | 定义前端第一期只读模型边界 | 控制联调范围，避免 UI 提前绑定未稳定能力 | `docs/` | 明确前端第一期只依赖“运行列表、tick 列表、tick 审计、叙事摘要”四类数据 |

## 4. 执行顺序

1. 先完成 `CLI-MVP-01`，统一入口先收口。
2. 紧接着完成 `CLI-MVP-02`，先定 JSON 契约。
3. 再完成 `CLI-MVP-03`，让真实模拟运行具备正式命令面。
4. 然后完成 `CLI-MVP-04` 和 `CLI-MVP-05`，把 demo 依赖清掉并补强回归验证。
5. 最后完成 `CLI-MVP-06` 和 `CLI-MVP-07`，补齐文档与前端联调边界。

## 5. MVP 收口标准

满足以下条件后，可认为“CLI 功能基本完成，允许开始前端页面开发”：

1. 存在统一 CLI 入口，用户无需记忆多个脚本文件。
2. `run / replay / narrate` 都提供稳定的机器可读输出。
3. 正式 `run` 命令可基于真实配置运行主循环，并产出可回放数据库结果。
4. demo 与正式 runtime 装配已分层，前端无需依赖 demo 专用逻辑。
5. 存在正式 CLI 的端到端集成测试，覆盖 `run -> replay -> narrate`。
6. README 与 docs 已更新为 MVP 用法，而不是只展示 demo。
7. 前端第一期只读模型边界已文档化，联调无需直接依赖数据库表结构。

## 6. 暂缓事项

以下事项重要，但不应抢在 CLI MVP 收口前推进：

- `WP-11` 传播增强与叙事节奏控制
- `WP-12` 质量度量与运营可观测性
- 更复杂的 PASSIVE/DORMANT UI 展示语义
- 围绕 demo 输出继续堆叠临时接口

原因：
- 它们会放大当前“产品面未收口”的问题。
- 当前前端真正需要的是稳定入口和稳定读模型，而不是更多引擎内部复杂度。

## 7. 维护规则

为保证本文件长期可维护，后续更新时遵循以下规则：

1. 只记录“当前 1~2 个迭代内真的要做的事”，不要把所有远期工作都倒进来。
2. 每个待办必须有唯一 ID、明确优先级、明确完成标准。
3. 已完成事项从表格状态改为 `DONE`，并在 [`changelog.md`](./changelog.md) 补实现事实；不要只改 TODO 不改 changelog。
4. 若优先级发生变化，优先同步本文件，再决定是否需要回写 [`系统架构工作包拆分.md`](./系统架构工作包拆分.md)。
5. 若代码状态与本文不一致，以代码和测试为准，并尽快修正文档。

## 8. 关联文档

- 目标设计基线：[`系统架构设计方案.md`](./系统架构设计方案.md)
- 中长期执行规划：[`系统架构工作包拆分.md`](./系统架构工作包拆分.md)
- 实现事实基线：[`changelog.md`](./changelog.md)
