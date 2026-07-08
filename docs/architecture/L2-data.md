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

### reranker.py — Rerank 重排服务 (v2.0 新增)

```python
from nexus.rag.reranker import RerankerService

reranker = RerankerService()
reranked = reranker.rerank(query="故障灯亮了", documents=results, top_k=5)
# 每条结果新增 rerank_score 字段
```

- 使用 BAAI/bge-reranker-v2-m3 模型（约560MB）
- 延迟加载，首次调用约2秒加载，后续 CPU 约200ms/20条
- 模型不可用时自动降级为原始顺序
- 模型路径: `./models/reranker/bge-reranker-v2-m3/`

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
