# Changelog

## 2026-03-10

### WP-05 物候系统（硬约束）
- 新增物候领域模型 [`src/narrator/models/phenology.py`](../src/narrator/models/phenology.py)，定义 `PhenologyState`，将季节、气候、节庆与 `day_of_year/season_progress` 作为不可变状态纳入世界状态。
- 扩展 [`src/narrator/models/world.py`](../src/narrator/models/world.py)，新增 `phenology` 字段，使物候更新进入正式状态结算，而非仅停留在文案层。
- 实现物候日历 [`src/narrator/phenology/calendar.py`](../src/narrator/phenology/calendar.py)：
  - 固定 120 tick 年历与四季映射；
  - `tick -> season/climate/festival` 的确定性转换；
  - 产出可直接落库的 `PhenologySnapshot/PhenologyState`。
- 实现规则注册表 [`src/narrator/phenology/registry.py`](../src/narrator/phenology/registry.py)，按 `priority + 注册顺序` 稳定执行物候硬约束，并输出完整审计记录。
- 实现物候效果模块 [`src/narrator/phenology/effects.py`](../src/narrator/phenology/effects.py)：
  - 严冬行军惩罚：降低 `resources.military_readiness`；
  - 雨季疾病提升：提高 `resources.disease_pressure`；
  - 歉收降粮：降低 `resources.grain_stock`；
  - 每次物候更新至少落入一个数值字段变更：`phenology.day_of_year`。
- 完成模块导出 [`src/narrator/phenology/__init__.py`](../src/narrator/phenology/__init__.py) 与模型导出 [`src/narrator/models/__init__.py`](../src/narrator/models/__init__.py)。
- 新增 WP-05 单测：
  - [`tests/unit/phenology/test_calendar.py`](../tests/unit/phenology/test_calendar.py)
  - [`tests/unit/phenology/test_effects.py`](../tests/unit/phenology/test_effects.py)
- 验证结果：
  - `pytest tests/unit/phenology -q` 通过（`6 passed`）。
  - `pytest tests/unit -q` 通过（`65 passed`）。

### WP-07 Knowledge & Diffusion 基础层
- 实现客观事实存储 [`src/narrator/knowledge/fact_store.py`](../src/narrator/knowledge/fact_store.py)：
  - 新增 `Fact`、`FactVisibility`、`FactStore`；
  - 支持 `global` / `location` / `private` 三类可见性；
  - 角色读取事实时按 `location_id` 与显式授权角色过滤，未授权事实不会进入角色上下文。
- 实现角色主观认知存储 [`src/narrator/knowledge/belief_store.py`](../src/narrator/knowledge/belief_store.py)：
  - 新增 `Belief`、`BeliefStore`；
  - 区分 `direct` / `rumor` / `inference` 来源；
  - 传闻/推断内容独立保存为摘要，不依赖泄露客观事实正文。
- 实现上下文构建与基础传播接口 [`src/narrator/knowledge/propagation.py`](../src/narrator/knowledge/propagation.py)：
  - 新增 `KnowledgeAssembler`，构建 `CharacterKnowledgeContext`；
  - 角色上下文拆分为 `facts` 与 `clues`，仅注入授权事实与允许暴露的推断线索；
  - 生成稳定 `audit_log`，保证同输入下上下文构建可复现、可审计；
  - 新增 `PropagationTask` 与 `plan_diffusion()`，为阶段 B 的传播时延机制预留显式接口。
- 完成模块导出 [`src/narrator/knowledge/__init__.py`](../src/narrator/knowledge/__init__.py)。
- 新增测试：
  - [`tests/unit/knowledge/test_stores.py`](../tests/unit/knowledge/test_stores.py)：覆盖可见性校验、作用域过滤、去重规则、传播延迟非法值显式失败。
  - [`tests/integration/test_isolation.py`](../tests/integration/test_isolation.py)：覆盖信息隔离与上下文构建可复现/可审计。
- 验证结果：
  - `pytest tests/unit/knowledge/test_stores.py -q` 通过（`4 passed`）。
  - `pytest tests/integration/test_isolation.py -q` 通过（`2 passed`）。
  - `pytest tests/unit -q` 通过（`66 passed`）。
  - `pytest tests/integration -q` 通过（`4 passed`）。

## 2026-02-27

### WP-01 项目基线与配置体系
- 新增项目骨架目录与占位模块，结构对齐 `docs/系统架构设计方案.md`。
- 新增 [`pyproject.toml`](../pyproject.toml)，定义运行依赖、开发依赖与 `narrator-run` 启动脚本。
- 新增 [`config/default.yaml`](../config/default.yaml) 与 [`config/schemas/action_whitelist.yaml`](../config/schemas/action_whitelist.yaml)。
- 新增 [`src/narrator/config.py`](../src/narrator/config.py)，实现：
  - YAML 加载；
  - `${ENV_VAR}` 环境变量替换；
  - Pydantic 严格校验（缺失字段/类型错误显式报错）。
- 新增启动入口：
  - [`src/narrator/main.py`](../src/narrator/main.py)
  - [`scripts/run.py`](../scripts/run.py)
- 新增配置单测 [`tests/unit/test_config.py`](../tests/unit/test_config.py)，覆盖：
  - 正常加载与环境变量替换；
  - 缺失字段显式失败；
  - 类型错误显式失败；
  - 缺失环境变量显式失败。
- 验证结果：`pytest tests/unit/test_config.py -q` 通过（`4 passed`）。

### WP-02 领域模型与契约定义
- 新增领域模型基类 [`src/narrator/models/base.py`](../src/narrator/models/base.py)，统一启用严格校验（`extra=forbid`）与不可变模型（`frozen=True`）。
- 完成核心枚举定义 [`src/narrator/models/enums.py`](../src/narrator/models/enums.py)：`StateMode`、`Granularity`、`Verdict`。
- 完成核心数据模型：
  - [`src/narrator/models/character.py`](../src/narrator/models/character.py)
  - [`src/narrator/models/event.py`](../src/narrator/models/event.py)
  - [`src/narrator/models/world.py`](../src/narrator/models/world.py)
  - [`src/narrator/models/action.py`](../src/narrator/models/action.py)
- 完成意图结构化协议与白名单校验器 [`src/narrator/agents/intent.py`](../src/narrator/agents/intent.py)：
  - `IntentPayload` 结构化协议（`intent + flavor_text`）；
  - `ActionWhitelist`/`ActionRule` 白名单模型；
  - 白名单加载与动作/参数合法性校验；
  - 非法动作、缺失参数、未知参数均显式报错。
- 升级动作白名单 schema [`config/schemas/action_whitelist.yaml`](../config/schemas/action_whitelist.yaml) 为“动作 -> 必填/可选参数”结构。
- 新增单测：
  - [`tests/unit/test_models.py`](../tests/unit/test_models.py)：覆盖非法枚举值、非法字段、契约结构有效性。
  - [`tests/unit/agents/test_intent.py`](../tests/unit/agents/test_intent.py)：覆盖白名单放行与非法动作/参数拦截。
- 验证结果：`pytest tests/unit -q` 通过（`12 passed`）。

### WP-03 Simulation Core 确定性内核
- 实现 `GlobalClock` [`src/narrator/core/clock.py`](../src/narrator/core/clock.py)：
  - `current_tick/advance/peek` 接口；
  - tick 单调推进；
  - 非法 `start_tick/step` 显式抛错。
- 实现 `SeedManager` [`src/narrator/core/seed.py`](../src/narrator/core/seed.py)：
  - 全局 seed 管理；
  - 基于稳定哈希（`sha256`）的子种子分配；
  - `rng(label)` 可复现实例化随机序列。
- 实现 `InterruptManager` [`src/narrator/core/interrupt.py`](../src/narrator/core/interrupt.py)：
  - `InterruptSignal` 模型与 `InterruptRule` 协议；
  - 规则注册与按注册顺序聚合中断信号；
  - 规则异常不吞错，直接外抛。
- 实现 `RuleEngine` [`src/narrator/core/rule_engine.py`](../src/narrator/core/rule_engine.py)：
  - `RuleContext`、`RuleExecutionRecord`、`RuleEngineResult`；
  - 规则注册、按 `priority + 注册顺序` 稳定执行；
  - 命中与未命中规则均产出审计日志；
  - 结果合并顺序稳定。
- 更新导出 [`src/narrator/core/__init__.py`](../src/narrator/core/__init__.py)。
- 新增 WP-03 单测：
  - [`tests/unit/core/test_clock.py`](../tests/unit/core/test_clock.py)
  - [`tests/unit/core/test_seed.py`](../tests/unit/core/test_seed.py)
  - [`tests/unit/core/test_interrupt.py`](../tests/unit/core/test_interrupt.py)
  - [`tests/unit/core/test_rule_engine.py`](../tests/unit/core/test_rule_engine.py)
- 验证结果：
  - `pytest tests/unit/core -q` 通过（`13 passed`）。
  - `pytest tests/unit -q` 通过（`59 passed`）。
- 说明：按本轮范围决策，`GlobalClock` 暂不提供 `tick -> datetime` 映射，仅负责 tick 管理。

### WP-04 持久化与可恢复能力
- 新增 SQLite 初始化与迁移执行器 [`src/narrator/persistence/database.py`](../src/narrator/persistence/database.py)：
  - 自动创建 `schema_migrations`；
  - 按文件名顺序执行 `migrations/*.sql`；
  - 空迁移脚本显式报错，不做静默跳过。
- 新增初始化迁移 [`src/narrator/persistence/migrations/001_init.sql`](../src/narrator/persistence/migrations/001_init.sql)，落地：
  - `world_snapshots`
  - `events`
  - `facts`
  - `beliefs`
  - `action_log`
  - `checkpoints`
- 新增仓储层 [`src/narrator/persistence/repositories.py`](../src/narrator/persistence/repositories.py)：
  - `WorldSnapshotRepository` 保存/读取完整世界快照；
  - `EventRepository` 按 tick 持久化与查询事件；
  - `FactRepository` / `BeliefRepository` 持久化客观事实与角色主观认知；
  - `ActionLogRepository` 记录 `verdict`、`retry_count`、`is_fallback`、`fallback_reason` 等关键审计字段。
- 新增 checkpoint 能力 [`src/narrator/persistence/checkpoint.py`](../src/narrator/persistence/checkpoint.py)：
  - `CheckpointRepository` 保存/恢复压缩后的 `WorldState` 与 RNG 状态；
  - `CheckpointManager` 基于固定间隔触发存档；
  - 恢复失败显式抛出 `LookupError`。
- 完成模块导出 [`src/narrator/persistence/__init__.py`](../src/narrator/persistence/__init__.py)。
- 新增测试：
  - [`tests/unit/persistence/test_repositories.py`](../tests/unit/persistence/test_repositories.py)：覆盖迁移建表、仓储 round-trip、checkpoint RNG 恢复；
  - [`tests/integration/test_replay.py`](../tests/integration/test_replay.py)：覆盖从 checkpoint 恢复后继续推进，结果与直接连续推进一致；
  - [`tests/integration/test_main_loop.py`](../tests/integration/test_main_loop.py)：覆盖 checkpoint 间隔触发行为。
- 验证结果：
  - `pytest tests/unit/persistence/test_repositories.py -q` 通过（`3 passed`）。
  - `pytest tests/integration/test_replay.py tests/integration/test_main_loop.py -q` 通过（`2 passed`）。

### WP-06 LLM 抽象与多 Provider 路由
- 新增 LLM Provider 抽象基类 [`src/narrator/llm/base.py`](../src/narrator/llm/base.py)：
  - `LLMProvider[T]` 泛型抽象基类（`async` 接口）；
  - `LLMRequest`/`LLMResponse` 请求响应模型；
  - `ProviderError`、`ProviderUnavailableError`、`ProviderValidationError` 异常体系；
  - `health_check()` 健康检查接口；
  - `complete()` 标准补全接口；
  - `complete_structured()` 结构化输出接口。
- 新增结构化响应 Schema [`src/narrator/llm/schemas.py`](../src/narrator/llm/schemas.py)：
  - `StructuredResponse` 基础响应模型；
  - `IntentResponse` 意图生成响应（`intent + flavor_text + parameters`）；
  - `DecisionResponse` 裁定响应（`verdict + reason + outcome`）；
  - `HealthCheckResponse` 健康检查响应；
  - `validate_structured_response()` 通用校验器。
- 新增 OpenAI Provider 实现 [`src/narrator/llm/openai.py`](../src/narrator/llm/openai.py)：
  - 支持 `chat/completions` 接口；
  - JSON Mode 结构化输出（`response_format: json_object`）；
  - Token 使用量统计返回。
- 新增 Anthropic Provider 实现 [`src/narrator/llm/anthropic.py`](../src/narrator/llm/anthropic.py)：
  - 支持 Messages API（`/v1/messages`）；
  - System Prompt + JSON 约束结构化输出；
  - Input/Output Tokens 统计返回。
- 新增 Ollama Provider 实现 [`src/narrator/llm/ollama.py`](../src/narrator/llm/ollama.py)：
  - 支持 `/api/generate` 接口；
  - JSON Mode（`format: json`）结构化输出；
  - Prompt/Completion Token 统计返回。
- 新增 Provider Router [`src/narrator/llm/router.py`](../src/narrator/llm/router.py)：
  - `LLMRouter` 多 Provider 管理与路由；
  - `register_provider()` 动态注册；
  - `set_default_provider()` 切换默认 Provider；
  - `health_check_all()` 批量健康检查；
  - `from_config()` 从配置字典批量初始化。
- 完成模块导出 [`src/narrator/llm/__init__.py`](../src/narrator/llm/__init__.py)。
- 新增 WP-06 单测：
  - [`tests/unit/llm/test_provider.py`](../tests/unit/llm/test_provider.py)：覆盖 Schema 校验、请求响应模型、异常体系。
  - [`tests/unit/llm/test_router.py`](../tests/unit/llm/test_router.py)：覆盖 Provider 注册、路由、健康检查、完成接口。
- 验证结果：
  - `pytest tests/unit/llm -q` 通过（`34 passed`）。
  - `pytest tests/unit -q` 通过（`59 passed`）。
