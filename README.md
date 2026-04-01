# reed-narrator

面向“无玩家介入”故事演化的叙事模拟项目。

## CLI MVP

统一入口：

```bash
narrator --help
```

或在未安装 editable package 时直接运行：

```bash
python scripts/run.py --help
```

正式运行：

```bash
narrator run --db data/runtime.db --max-ticks 8 --checkpoint-interval 4 --json
```

回放 tick 列表：

```bash
narrator replay --db data/runtime.db --json list --source snapshot
```

生成规则叙事摘要：

```bash
narrator narrate --db data/runtime.db --rules-only --from-tick 1 --to-tick 8 --json
```

读取 tick 审计：

```bash
narrator inspect --db data/runtime.db --json audit --tick 4
```

当前稳定机器可读输出范围：

- `narrator run --json`
- `narrator replay --json`
- `narrator narrate --json`
- `narrator inspect --json`

前端第一期只读模型边界见 [`docs/frontend-read-model.md`](./docs/frontend-read-model.md)。

## Demo

运行当前项目亮点演示：

```bash
python scripts/demo.py
```

或使用安装后的入口：

```bash
narrator-demo
```

这个 demo 只复用现有模块，不引入新功能，重点展示：

- 物候系统对世界状态的硬约束
- 信息隔离与线索脱敏
- 事件驱动的粒度切换、聚光灯分层与行动时间线
- 认知生成、谣言扩散与 tick audit 持久化
- SQLite snapshot / checkpoint / replay 检查能力

如需保留 demo 生成的 SQLite 文件：

```bash
python scripts/demo.py --db data/demo.db
```

## Config

运行配置加载入口前，先复制 `.env.example` 为 `.env` 并补齐所需 API Key。
