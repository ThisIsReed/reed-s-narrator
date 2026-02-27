# Changelog

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
