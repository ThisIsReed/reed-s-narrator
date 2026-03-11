# reed-narrator

面向“无玩家介入”故事演化的叙事模拟项目。

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
