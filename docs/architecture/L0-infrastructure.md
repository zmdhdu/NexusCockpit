# L0 基础设施层 (Infrastructure)

> 对应代码: `docker-compose.yml` + `config/`

## 职责

提供所有中间件的容器化部署，包括：
- Milvus (向量数据库)
- Neo4j (知识图谱)
- Redis (缓存 + 限流 + PubSub)
- RabbitMQ (消息队列)
- MySQL (用户数据 + 审计日志)
- Prometheus (指标采集)
- Grafana (可视化面板)

> **双模式部署**: 所有中间件均可通过 `.env` 的 `*_PROVIDER` 开关切换为云端托管服务（Zilliz Cloud / AuraDB / 云 Redis / 硅基流动 Rerank），详见 `docs/deployment/dual_云端与本地部署.md`。

## 组件清单

| 服务 | 镜像 | 端口 | 用途 |
|------|------|------|------|
| Milvus | milvusdb/milvus:v2.4.0 | 19530, 9091 | 向量存储与检索 |
| etcd | quay.io/coreos/etcd:v3.5.5 | 2379 | Milvus 元数据 |
| MinIO | minio/minio | 9000, 9001 | Milvus 对象存储 |
| Neo4j | neo4j:5.19.0 | 7474, 7687 | 知识图谱 |
| Redis | redis:7.2-alpine | 6379 | 缓存/限流/PubSub |
| RabbitMQ | rabbitmq:3.13-management | 5672, 15672 | 消息队列 |
| MySQL | mysql:8.0 | 3306 | 用户数据/审计日志 |
| Prometheus | prom/prometheus:v2.51.0 | 9090 | 指标采集 |
| Grafana | grafana/grafana:10.4.0 | 3001 | 可视化面板 |

## 启动方式

```bash
# 启动全部基础设施
docker compose up -d

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f milvus

# 停止
docker compose down

# 清除数据 (谨慎!)
docker compose down -v
```

## 配置文件

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | 主编排文件 |
| `config/prometheus/prometheus.yml` | Prometheus 采集配置 |
| `config/grafana/provisioning/` | Grafana 数据源和面板自动配置 |

## 数据持久化

所有数据通过 Docker Volume 持久化：
- `milvus_data` — Milvus 向量数据
- `neo4j_data` — Neo4j 图谱数据
- `redis_data` — Redis AOF 持久化
- `rabbitmq_data` — RabbitMQ 消息持久化
- `mysql_data` — MySQL 数据库数据
- `prometheus_data` — Prometheus 指标历史
- `grafana_data` — Grafana 面板配置

## 健康检查

| 服务 | 健康检查端点 |
|------|-------------|
| Milvus | `http://localhost:9091/healthz` |
| Redis | `redis-cli ping` |
| RabbitMQ | `rabbitmq-diagnostics check_running` |
| Neo4j | `http://localhost:7474` |
| MySQL | `mysqladmin ping -h localhost` |
