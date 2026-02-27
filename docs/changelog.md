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
