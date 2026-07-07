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
store.insert(collection="Food_List", records=[...])
results = store.search(collection="Food_List", query="火锅", top_k=5)
```

- HNSW 索引，IP 度量
- 支持多 Collection (食物、记忆)

### graph_store.py — Neo4j 知识图谱

```python
from nexus.rag.graph_store import Neo4jGraphStore

store = Neo4jGraphStore()
store.connect()
store.add_user_preference(user_id="u1", key="food", value="川菜")
prefs = store.get_user_preferences(user_id="u1")
```

- 用户画像节点 + 偏好关系
- Cypher 查询

### retriever.py — GraphRAG 融合检索器

```python
from nexus.rag.retriever import GraphRAGRetriever

retriever = GraphRAGRetriever(vector_store, graph_store, embedding_service)
results = await retriever.retrieve(
    query="推荐附近的川菜",
    user_id="u1",
    top_k=5,
)
```

- **向量路径**: Milvus 语义搜索 → Top-K
- **图谱路径**: Neo4j 用户画像 + 关系遍历
- **融合策略**: RRF (Reciprocal Rank Fusion) 排序合并

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

### compressor.py — 上下文压缩

```python
from nexus.memory.compressor import ContextCompressor

compressor = ContextCompressor()
compressed = compressor.compress(history, max_tokens=2000)
```

- 基于 LLM 的摘要压缩
- 保留关键信息，控制 Token 消耗

### conflict.py — 记忆冲突检测

```python
from nexus.memory.conflict import ConflictDetector

detector = ConflictDetector()
conflict = detector.check(new_memory, existing_memories)
# → {"has_conflict": True, "conflicting_id": "mem_123", "resolution": "replace"}
```

## 数据模型 (nexus/models/)

### state.py — Agent 状态

定义 LangGraph 工作流中传递的状态对象：
- `user_input` — 用户输入文本
- `intent` — 识别的意图
- `plan` — Planner 生成的执行计划
- `execution_result` — Executor 执行结果
- `response` — Responder 生成的响应
- `review_passed` — Reviewer 审查结果
- `memory_context` — 召回的记忆上下文

### schemas.py — API 模型

定义 API 请求/响应的 Pydantic 模型。
