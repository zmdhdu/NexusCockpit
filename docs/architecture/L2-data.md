# L2 数据层 (Data)

> 对应代码: `nexus/rag/` + `nexus/memory/` + `nexus/models/`

## 职责

提供知识检索和记忆管理能力：
- **GraphRAG 引擎** — 融合向量检索与知识图谱
- **记忆系统** — 用户画像、对话历史、长期记忆
- **数据模型** — Agent 状态和 API 模型定义

## RAG 引擎 (nexus/rag/)

### embedding.py — Embedding 服务

```python
from nexus.rag.embedding import EmbeddingService

service = EmbeddingService()
vector = await service.embed("把空调调到24度")  # → List[float]
```

- 支持 Ark API (Qwen3-Embedding-4B, 2560维) 和本地模型
- 内置批量嵌入和缓存

### vector_store.py — Milvus 向量存储

```python
from nexus.rag.vector_store import MilvusVectorStore

store = MilvusVectorStore(embedding_service)
store.connect()
await store.insert_memory(text="用户喜欢24度", user_id="u1")
results = await store.search_memory(query_text="空调温度", user_id="u1", top_k=5)
foods = await store.search_food(query_text="火锅", top_k=5)
```

- HNSW 索引，IP 度量
- 支持多 Collection (食物、记忆)
- 继承 `BaseVectorStore` 抽象基类，支持双模式部署

### vector_base.py / vector_factory.py — 向量存储抽象层与工厂 (双模式新增)

```python
from nexus.rag.vector_factory import build_vector_store

# 根据 .env 的 VECTOR_STORE_PROVIDER 自动选择后端
store = build_vector_store(embedding_service)
# local  → MilvusVectorStore (本地 Docker)
# cloud  → ZillizVectorStore  (Zilliz Cloud 云端)
```

- `BaseVectorStore(ABC)` 定义统一接口: connect/search_memory/insert_memory/search_food 等
- `MilvusVectorStore` 继承基类，本地 Docker 部署
- `ZillizVectorStore` 继承 MilvusVectorStore，仅覆写 connect() 使用云端 URI+Token
- `build_vector_store()` 工厂函数按 `VECTOR_STORE_PROVIDER` 分发

### graph_store.py — Neo4j 知识图谱

```python
from nexus.rag.graph_store import Neo4jGraphStore

store = Neo4jGraphStore()
store.connect()
store.upsert_relation(user_id="u1", relation="LIKES", target="川菜", target_type="Food", milvus_id=42)
results = store.search_user_graph(user_id="u1", depth=1)
profile = store.get_user_profile(user_id="u1")
```

- 用户画像节点 + 偏好关系
- Cypher 查询
- 继承 `BaseGraphStore` 抽象基类，支持双模式部署

### graph_base.py / graph_factory.py — 图谱存储抽象层与工厂 (双模式新增)

```python
from nexus.rag.graph_factory import build_graph_store

# 根据 .env 的 GRAPH_STORE_PROVIDER 自动选择后端
store = build_graph_store()
# local  → Neo4jGraphStore  (本地 Docker)
# cloud  → AuraGraphStore    (Neo4j AuraDB 云端)
```

- `BaseGraphStore(ABC)` 定义统一接口: connect/upsert_relation/search_user_graph 等
- `Neo4jGraphStore` 继承基类，本地 Docker 部署
- `AuraGraphStore` 继承 Neo4jGraphStore，仅覆写 connect() 使用 neo4j+s:// 加密 URI

### retriever.py — GraphRAG 三路融合检索器 (v2.0)

```python
from nexus.rag.retriever import GraphRAGRetriever

retriever = GraphRAGRetriever(
    vector_store, graph_store, embedding_service,
    enable_rerank=True,
    enable_bm25=True,
)
results = await retriever.retrieve_memories(
    query="推荐附近的川菜",
    user_id="u1",
    top_k=5,
)
```

v2.0 三路融合检索:
- **向量路**: Milvus 语义相似度召回（基于文本含义匹配）
- **图谱路**: Neo4j 关系遍历召回（基于实体关系匹配）
- **BM25路**: 全文关键词匹配召回（基于词频精确匹配）
- **融合策略**: RRF (Reciprocal Rank Fusion) 三路融合排序
- **后处理**: `bge-reranker-v2-m3` Rerank 模型重排 Top-N

### reranker.py / reranker_base.py / reranker_factory.py — Rerank 重排服务 (v2.0 + 双模式)

```python
from nexus.rag.reranker_factory import build_reranker

# 根据 .env 的 RERANKER_PROVIDER 自动选择后端
reranker = build_reranker()
# local  → LocalReranker          (本地 BGE CrossEncoder)
# cloud  → SiliconFlowReranker    (硅基流动 Rerank API)
# none   → NoneReranker           (跳过重排)

reranked = reranker.rerank(query="故障灯亮了", documents=results, top_k=5)
# 每条结果新增 rerank_score 字段
```

- `BaseReranker(ABC)` 定义统一接口: rerank() + is_available
- `LocalReranker` (原 `RerankerService`) 使用 BAAI/bge-reranker-v2-m3 本地模型
- `SiliconFlowReranker` 调用硅基流动 `/rerank` API，复用 ARK_API_KEY
- `NoneReranker` 直接原序返回，用于省成本场景
- `build_reranker()` 工厂函数按 `RERANKER_PROVIDER` 分发
- 向后兼容: `from nexus.rag.reranker import RerankerService` 仍可用 (别名指向 LocalReranker)

### cherry_kb.py — Cherry 知识库 (v2.0 新增)

```python
from nexus.rag.cherry_kb import CherryKnowledgeBase

kb = CherryKnowledgeBase(embedding_service)
kb.connect(milvus_client)
chunks = kb.add_document(text, source="manual.pdf", category="manual")
results = kb.search("发动机故障灯", top_k=5)
```

- 基于 Milvus 的文档型知识库
- 支持文档分块、向量化、入库
- 按类别管理 (manual/dtc/faq/maintenance)

### unified_retriever.py — 统一检索路由 (v2.0 新增)

```python
from nexus.rag.unified_retriever import UnifiedRetriever

retriever = UnifiedRetriever(
    graphrag=graphrag_retriever,
    cherry_kb=cherry_kb,
)
results = await retriever.retrieve(query, query_type="hybrid", top_k=5)
```

- 统一路由: 根据查询类型 (memory/knowledge/hybrid) 分发到对应检索器
- 混合查询: 同时检索用户记忆和知识库，合并结果

## 记忆系统 (nexus/memory/)

### manager.py — 记忆管理器

```python
from nexus.memory.manager import MemoryManager

manager = MemoryManager(vector_store, graph_store)
manager.connect()

# 召回记忆
context = manager.recall(user_id="u1", query="空调温度")

# 存储记忆
manager.store(user_id="u1", content="用户喜欢24度", metadata={"type": "preference"})
```

### compressor.py — 上下文压缩 (v2.0 增强)

```python
from nexus.memory.compressor import ContextCompressor

compressor = ContextCompressor()
compressed = compressor.compress(history, max_tokens=2000)
```

- v2.0: 基于 `tiktoken` 精准 Token 计数（替代粗略字数估算）
- 动态上下文窗口: 根据模型 max_tokens 自适应截断
- 保留关键信息，控制 Token 消耗

### conflict.py — 记忆冲突检测

```python
from nexus.memory.conflict import ConflictDetector

detector = ConflictDetector()
conflict = detector.check(new_memory, existing_memories)
# → {"has_conflict": True, "conflicting_id": "mem_123", "resolution": "replace"}
```

## 数据模型 (nexus/models/)

### state.py — Agent 状态 (v2.0 TypedDict)

v2.0 从 `@dataclass` 改为 `TypedDict`（LangGraph 原生支持），使用 `Annotated` reducer 处理并行写入：
- `user_input` — 用户输入文本
- `intent` — 识别的意图
- `active_experts` — Supervisor 决定分派给哪些专家
- `expert_results` — 专家并行输出（`Annotated[list, add]` 累加）
- `skill_result` / `skill_handled` / `skill_action` — 兼容 v1.0 技能字段
- `has_side_effect` — 副作用标记（车控指令禁止缓存）
- `final_response` — 最终响应
- `metadata` — 元数据（`Annotated[dict, merge_dict]` 合并）

> 详细字段定义见 L4-agent.md

### schemas.py — API 模型

定义 API 请求/响应的 Pydantic 模型。
