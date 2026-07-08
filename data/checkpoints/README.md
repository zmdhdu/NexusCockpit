# Checkpoints Directory

LangGraph SqliteSaver checkpoint 持久化目录。

## 说明
- v2.0 使用 SqliteSaver 替代 v1.0 的内存 dict
- SQLite 数据库文件: `nexus_checkpoints.db`
- 路径由 config.py 配置，默认 `./data/checkpoints/`
- 重启后不丢失会话状态，thread_id 隔离不同会话
