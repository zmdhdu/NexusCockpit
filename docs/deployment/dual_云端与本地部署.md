# NexusCockpit 双模式部署实施方案（本地 ⇄ 云端 AK/SK）

> **核心目标**：让每个"本地部署型"组件都能通过 `.env` 一键切换为"云端 API/AK·SK 型"。本地能跑、线上只改配置也能跑。

---

## 一、背景与目标

当前项目所有数据库/中间件/模型都假设本地 Docker 部署（Milvus、Neo4j、Redis、MySQL + 本地 ASR/TTS 模型）。痛点：

1. **本地部署重**：要起 9 个容器、下 3.5GB 语音模型、占用大量内存。
2. **无法平滑迁移到线上**：一旦想用云托管服务，要改一堆代码。

**云端供应商首选：硅基流动（SiliconFlow）**
- **OpenAI 兼容**：base_url `https://api.siliconflow.cn/v1`，认证用 Bearer Token，`/chat/completions`、`/embeddings`、`/rerank` 端点格式与火山方舟一致。现有代码 LLM 全用 `AsyncOpenAI` SDK、Embedding 用 `httpx` 调 `/embeddings`，**切硅基流动只需改 `.env` 的 base_url + key + 模型名，代码零改动**。
- **有免费档**：免费 embedding（`BAAI/bge-m3`、`BAAI/bge-large-zh`）和 rerank（`BAAI/bge-reranker-v2-m3`），RAG 链路可零成本起步。
- **一站式**：LLM + Embedding + Rerank 同一平台同一 Key。

## 二、改造范围

| 组件 | 本地实现 | 接线状态 | 云端目标 |
|---|---|---|---|
| LLM 对话 | 火山方舟（`AsyncOpenAI` SDK） | ✅ 已接线，OpenAI 兼容 | **硅基流动**（改 .env 即可） |
| Embedding | 火山方舟（httpx `/embeddings`） | ✅ 已接线，OpenAI 兼容 | **硅基流动免费 bge-m3** |
| OSS | 阿里云 oss2 | ❌ v2.2 已移除（未集成，过度设计） | 无需改 |
| Langfuse | cloud.langfuse.com | ✅ 已是云端，空 Key 自动降级 | 无需改 |
| **Milvus** | Docker 本地 | ✅ 已接线 | **Zilliz Cloud** |
| **Neo4j** | Docker 本地 | ✅ 已接线 | **Neo4j AuraDB** |
| **Redis 语义缓存** | redis-stack-server（含 RediSearch） | ✅ 已接线 | **云 Redis（接受 scan 回退）** |
| **Reranker** | 本地 BGE CrossEncoder | ✅ 已接线 | **硅基流动 Rerank API（免费 bge-reranker）** |
| ASR/TTS/声纹 | 本地 funasr/CosyVoice/CAM++ | ❌ 未接线（死代码） | 本次不做 |
| MySQL | Docker | ❌ 死配置（无 ORM） | 本次清理 |
| Celery/RabbitMQ | Docker | ❌ v2.2 已移除（任务队列改为 asyncio.create_task） | 无需改 |
## 三、关键发现（探索结论）

- **LLM 全用 `AsyncOpenAI` SDK**（7 处调用点：`responder.py:45`、`supervisor_graph.py:85`、`llm_router.py:31`、`router.py:57`、`compressor.py:69`、`manager.py:40`、`conflict.py:25`），都读 `config.llm.ark_api_key` + `ark_base_url`。硅基流动 OpenAI 兼容，**改 base_url + key + 模型名即可切换，代码零改动**。
- **Embedding 用 httpx** 调 `/embeddings`（`embedding.py:105`），同样 OpenAI 兼容。**注意**：硅基流动 bge-m3 维度 1024，当前 `.env` 的 `EMBEDDING_DIM=2560`（火山 Qwen3-Embedding-4B），切换时必须同步改维度，否则 Milvus collection 维度不匹配会报错。
- 语义缓存 `redis_cache.py` 已有两条路径：RediSearch KNN（快）+ O(n) scan（回退，第 159/237 行）。普通云 Redis 没 RediSearch 模块会自动走 scan，**功能不丢，只是慢**。
- Redis 限流器 `rate_limiter.py` 只用普通 Lua（ZADD/ZCARD），**任何云 Redis 都能跑**。
- Reranker `reranker.py` 已有"模型缺失/导入失败则 passthrough"降级（第 47-72 行），加云端实现只需新增一个子类。
- 车控 `vehicle/factory.py` 是现成工厂模板：读 `config.xxx.adapter` → 分发到不同实现。**本方案复用这个模式**。

## 四、设计策略

每个需要双模式的组件，统一用三层结构：

```
base.py        → ABC 抽象基类（定义接口）
local.py       → 本地实现（现有代码继承 ABC）
cloud.py       → 云端实现（新增，调 API）
factory.py     → 工厂函数（读 .env 的 PROVIDER 字段分发）
```

`.env` 新增一组 `*_PROVIDER` 开关，值为 `local` / `cloud` / `none`。切换线上时把 `local` 改成 `cloud` 并填对应 AK/SK，**代码零改动**。

---

## 五、改动文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend_design/nexus/config.py` | 改 | 加 `ProvidersConfig` + `RerankerConfig` |
| `.env.example` | 改 | 加 provider 段 + LLM 供应商切换注释 + 删 MySQL 段 |
| `backend_design/nexus/rag/vector_base.py` | 新建 | `BaseVectorStore(ABC)` |
| `backend_design/nexus/rag/vector_store.py` | 改 | `MilvusVectorStore` 继承基类 |
| `backend_design/nexus/rag/zilliz_vector_store.py` | 新建 | Zilliz 云端实现 |
| `backend_design/nexus/rag/vector_factory.py` | 新建 | `build_vector_store()` |
| `backend_design/nexus/rag/graph_base.py` | 新建 | `BaseGraphStore(ABC)` |
| `backend_design/nexus/rag/graph_store.py` | 改 | `Neo4jGraphStore` 继承基类 |
| `backend_design/nexus/rag/aura_graph_store.py` | 新建 | AuraDB 云端实现 |
| `backend_design/nexus/rag/graph_factory.py` | 新建 | `build_graph_store()` |
| `backend_design/nexus/rag/reranker_base.py` | 新建 | `BaseReranker(ABC)` |
| `backend_design/nexus/rag/reranker.py` | 改 | 拆出 `LocalReranker` 继承基类 |
| `backend_design/nexus/rag/siliconflow_reranker.py` | 新建 | 硅基流动 Rerank API |
| `backend_design/nexus/rag/reranker_factory.py` | 新建 | `build_reranker()` |
| `backend_design/nexus/middleware/redis_cache.py` | 微改 | `connect()` 加 provider 日志/降级提示 |
| `backend_design/nexus/main.py` | 改 | 3 处构造换工厂函数 |
| `backend_design/scripts/init_milvus.py` | 改 | 换工厂 + 加 `--rebuild` 参数 |
| `backend_design/scripts/init_neo4j.py` | 改 | 换工厂 |
| `backend_design/nexus/rag/retriever.py` | 改 | Reranker 换工厂 |
| `backend_design/nexus/rag/unified_retriever.py` | 改 | Reranker 换工厂 |
| `docker-compose.yml` | 改 | 删 mysql 服务 |
| `backend_design/requirements.txt` | 改 | 删 SQLAlchemy/aiomysql/alembic |

---

## 六、执行顺序

建议按依赖关系从底往上改：

1. **Step 1**：改 `config.py`（加 provider 配置）
2. **Step 2**：改 `.env.example`（加 provider 段）
3. **Step 3**：向量库 ABC + 工厂 + Zilliz 实现
4. **Step 4**：图谱 ABC + 工厂 + AuraDB 实现
5. **Step 5**：Reranker ABC + 工厂 + 硅基流动实现
6. **Step 6**：微调 `redis_cache.py`
7. **Step 7**：改 `main.py` 接工厂
8. **Step 8**：改初始化脚本 + retriever 调用点
9. **Step 9**：清理 MySQL 死配置
10. **Step 10**：验证

下面每一步都给出**完整代码**。

---
## 七、Step 1：改 config.py

在 `backend_design/nexus/config.py` 的 `TavilyConfig` 类**之后**、`AppConfig` 类**之前**，新增两个配置类：

```python
class ProvidersConfig(BaseSettings):
    """双模式部署开关 — 控制各组件使用本地中间件还是云端托管。

    每个开关取值:
        - local:  使用本地 Docker 部署的中间件/模型 (开发默认)
        - cloud:  使用云端托管服务 (Zilliz/AuraDB/云Redis/硅基流动)
        - none:   仅 RERANKER_PROVIDER 支持，跳过重排省成本

    切换线上时，把对应开关改为 cloud 并在下方各组件配置中填入云端 AK/SK，
    代码无需改动。详见 docs/deployment/SETUP.md 双模式部署章节。
    """

    # 向量库: local=本地 Milvus | cloud=Zilliz Cloud
    vector_store: str = Field(default="local", validation_alias="VECTOR_STORE_PROVIDER")
    # 图谱: local=本地 Neo4j | cloud=Neo4j AuraDB
    graph_store: str = Field(default="local", validation_alias="GRAPH_STORE_PROVIDER")
    # 语义缓存: local=本地 Redis Stack | cloud=云 Redis (无 RediSearch 时自动降级 scan)
    cache: str = Field(default="local", validation_alias="CACHE_PROVIDER")
    # 重排: local=本地 BGE | cloud=硅基流动 Rerank | none=跳过
    reranker: str = Field(default="local", validation_alias="RERANKER_PROVIDER")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def normalized(self) -> dict[str, str]:
        """返回小写归一化后的 provider 取值，便于工厂函数比较。"""
        return {
            "vector_store": (self.vector_store or "local").strip().lower(),
            "graph_store": (self.graph_store or "local").strip().lower(),
            "cache": (self.cache or "local").strip().lower(),
            "reranker": (self.reranker or "local").strip().lower(),
        }

class RerankerConfig(BaseSettings):
    """Rerank 重排配置。

    RERANKER_PROVIDER=cloud 时使用硅基流动 Rerank API (复用 ARK_API_KEY/ARK_BASE_URL)。
    本地模式 (RERANKER_PROVIDER=local) 加载 ./models/reranker/bge-reranker-v2-m3 模型。
    """

    # 硅基流动 Rerank 模型 ID (云端模式)
    model: str = Field(
        default="BAAI/bge-reranker-v2-m3", validation_alias="RERANK_MODEL"
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")
```

然后在 `AppConfig` 类的字段列表里，**在 `tavily` 之后**追加两行：

```python
    tavily: TavilyConfig = Field(default_factory=TavilyConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)   # 新增
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)       # 新增
```

> 注意：`MySQLConfig` 类**保留不动**（虽然死配置，但删它要动 AppConfig 字段和 .env，留到 Step 9 一起清理）。

---

## 八、Step 2：改 .env.example

把 `.env.example` 顶部的 LLM 段改为（加供应商切换注释）：

```ini
# --- LLM / Embedding (OpenAI 兼容, 改 base_url 即可切换供应商) ---
# 火山方舟:   ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# 硅基流动:   ARK_BASE_URL=https://api.siliconflow.cn/v1  (免费 embedding/rerank)
ARK_API_KEY=your_ark_api_key_here
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_MODEL=deepseek-ai/DeepSeek-V3
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B
EMBEDDING_DIM=2560
# ⚠️ 切换 embedding 模型时 EMBEDDING_DIM 必须同步改, 并重建 Milvus collection:
#   硅基流动 BAAI/bge-m3 → EMBEDDING_DIM=1024
```


把 MySQL 段**整段删除**：

```ini
# --- MySQL (User Data + Audit Log) ---       ← 删掉这 6 行
# MYSQL_HOST=127.0.0.1
# MYSQL_PORT=3306
# MYSQL_USER=root
# MYSQL_PASSWORD=nexuscockpit
# MYSQL_DATABASE=nexus_cockpit
```

在文件**末尾**追加双模式部署开关段：

```ini
# ============================================================
# 双模式部署开关 (local=本地Docker | cloud=云端托管)
# 切换线上时改 provider 为 cloud 并填下方云端 AK/SK, 代码无需改动
# ============================================================
VECTOR_STORE_PROVIDER=local      # local=本地Milvus | cloud=Zilliz Cloud
GRAPH_STORE_PROVIDER=local       # local=本地Neo4j | cloud=AuraDB
CACHE_PROVIDER=local             # local=本地Redis | cloud=云Redis
RERANKER_PROVIDER=local          # local=本地BGE | cloud=硅基流动Rerank | none=跳过

# --- Zilliz Cloud (VECTOR_STORE_PROVIDER=cloud 时填) ---
# MILVUS_URI=https://<your-cluster>.zillizcloud.com
# MILVUS_TOKEN=<zilliz api key>

# --- Neo4j AuraDB (GRAPH_STORE_PROVIDER=cloud 时填) ---
# NEO4J_URI=neo4j+s://<your-db-id>.databases.neo4j.io
# NEO4J_PASSWORD=<aura password>

# --- 云 Redis (CACHE_PROVIDER=cloud 时填) ---
# REDIS_HOST=<cloud redis host>
# REDIS_PORT=<port>
# REDIS_PASSWORD=<cloud redis password>
# 注意: 云 Redis 若无 RediSearch 模块, 语义缓存自动降级为 scan 模式

# --- 硅基流动 Rerank (RERANKER_PROVIDER=cloud 时填, 复用 ARK_API_KEY/ARK_BASE_URL) ---
# RERANK_MODEL=BAAI/bge-reranker-v2-m3
```


## 九、Step 3：向量库双模式（Milvus ⇄ Zilliz Cloud）

### 9.1 新建 `backend_design/nexus/rag/vector_base.py`

```python
"""
Vector Store Base — 向量存储抽象基类

定义向量库的统一接口。本地 Milvus 与云端 Zilliz Cloud 都继承此类，
让上层 (检索器/记忆管理) 无需关心具体后端。

接口与现有 MilvusVectorStore 的公开方法保持一致，便于平滑迁移。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from nexus.rag.embedding import EmbeddingService


class BaseVectorStore(ABC):
    """向量存储抽象接口。

    子类必须实现: 连接 / 记忆检索 / 记忆写入 / 记忆删除 / 食材检索 / 断开。
    """

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()

    @abstractmethod
    def connect(self) -> None:
        """连接向量库并初始化集合。"""
        raise NotImplementedError

    @abstractmethod
    async def search_memory(self, query_text: str, user_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索特定用户的语义记忆。"""
        raise NotImplementedError

    @abstractmethod
    async def insert_memory(self, text: str, user_id: str) -> Optional[int]:
        """插入一条用户记忆，返回主键 ID。"""
        raise NotImplementedError

    @abstractmethod
    def delete_memory_by_ids(self, id_list: List[int], user_id: str) -> bool:
        """根据 ID 列表和 user_id 安全删除记忆。"""
        raise NotImplementedError

    @abstractmethod
    async def search_food(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索食材库。"""
        raise NotImplementedError

    @abstractmethod
    def drop_collection(self, name: str) -> bool:
        """删除集合（切换 embedding 维度时用）。"""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接。"""
        raise NotImplementedError

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError
```

### 9.2 改 `backend_design/nexus/rag/vector_store.py`

只需改两处：①导入基类；②类定义继承基类。**其余逻辑不动**。

文件顶部导入区，把：
```python
from nexus.rag.embedding import EmbeddingService
```
改为：
```python
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_base import BaseVectorStore
```

类定义：
```python
class MilvusVectorStore(BaseVectorStore):   # ← 原来是 class MilvusVectorStore:
    """Milvus 向量数据库管理器。

    Args:
        embedding_service: 文本向量化服务
    """

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.config = get_config().milvus
        self.embedding_service = embedding_service or EmbeddingService()
        self._connected = False
        self.food_collection: Optional[Collection] = None
        self.memory_collection: Optional[Collection] = None
```

> 因为基类 `__init__` 已设置 `self.embedding_service`，子类这里重复设置无妨（保持原样即可，不破坏现有行为）。其余方法**完全不动**。

### 9.3 新建 `backend_design/nexus/rag/zilliz_vector_store.py`

```python
"""
Zilliz Cloud Vector Store — Zilliz 云端向量存储

Zilliz 是 Milvus 的官方云托管, pymilvus 客户端完全通用。
与 MilvusVectorStore 的唯一区别: connect() 使用云端 URI + Token。

配置 (.env, VECTOR_STORE_PROVIDER=cloud):
    MILVUS_URI=https://<cluster>.zillizcloud.com
    MILVUS_TOKEN=<zilliz api key>
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from nexus.core.logger import get_logger
from nexus.rag.vector_base import BaseVectorStore
from nexus.rag.vector_store import MilvusVectorStore

logger = get_logger(__name__)


class ZillizVectorStore(MilvusVectorStore):
    """Zilliz Cloud 向量存储。

    继承 MilvusVectorStore 的全部逻辑, 仅在 connect() 时使用云端连接参数。
    Zilliz 与 Milvus 协议一致, 无需重写任何检索/写入方法。
    """

    def connect(self) -> None:
        """连接 Zilliz Cloud。

        复用父类 connect(), 但日志标注为 Zilliz 云端。
        连接参数 (uri/token) 来自 config.milvus, 由 .env 的 MILVUS_URI/MILVUS_TOKEN 提供。
        """
        logger.info(
            "Connecting to Zilliz Cloud",
            uri=self.config.uri,
            has_token=bool(self.config.token),
        )
        # 父类 connect() 已处理连接 + 集合初始化 + 异常
        super().connect()
        if self.is_connected:
            logger.info("Zilliz Cloud vector store connected")
```


### 9.4 新建 `backend_design/nexus/rag/vector_factory.py`

```python
"""
Vector Store Factory — 向量存储工厂

根据 .env 的 VECTOR_STORE_PROVIDER 选择向量库后端:
  - local: 本地 Milvus (Docker)
  - cloud: Zilliz Cloud (Milvus 官方云托管)
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_base import BaseVectorStore
from nexus.rag.vector_store import MilvusVectorStore
from nexus.rag.zilliz_vector_store import ZillizVectorStore

logger = get_logger(__name__)


def build_vector_store(
    embedding_service: EmbeddingService | None = None,
) -> BaseVectorStore:
    """根据 VECTOR_STORE_PROVIDER 配置选择向量存储后端。

    Args:
        embedding_service: 文本向量化服务 (可选, 缺省自动创建)

    Returns:
        BaseVectorStore 实例 (MilvusVectorStore / ZillizVectorStore)
    """
    provider = get_config().providers.normalized()["vector_store"]

    if provider == "cloud":
        logger.info("VectorStore provider: Zilliz Cloud")
        return ZillizVectorStore(embedding_service)

    # 默认 local
    logger.info("VectorStore provider: local Milvus")
    return MilvusVectorStore(embedding_service)
```


---

## 十、Step 4：图谱双模式（Neo4j ⇄ AuraDB）

### 10.1 新建 `backend_design/nexus/rag/graph_base.py`

```python
"""
Graph Store Base — 知识图谱存储抽象基类

定义图谱库的统一接口。本地 Neo4j 与云端 AuraDB 都继承此类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseGraphStore(ABC):
    """知识图谱抽象接口。

    子类必须实现: 连接 / 关系增删 / 用户图谱查询 / 食材查询 / 画像 / 清库 / 关闭。
    """

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_relation(
        self,
        user_id: str,
        relation: str,
        target: str,
        target_type: str,
        milvus_id: int,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_relation_by_mid(self, milvus_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def search_user_graph(self, user_id: str, depth: int = 1) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def search_food(self, food_name: str) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def clear_database(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
```

### 10.2 改 `backend_design/nexus/rag/graph_store.py`

文件顶部导入区追加：
```python
from nexus.rag.graph_base import BaseGraphStore
```

类定义改为继承基类：
```python
class Neo4jGraphStore(BaseGraphStore):   # ← 原来是 class Neo4jGraphStore:
    """Neo4j 知识图谱管理器"""
```

**其余方法完全不动**。

### 10.3 新建 `backend_design/nexus/rag/aura_graph_store.py`

```python
"""
AuraDB Graph Store — Neo4j AuraDB 云端图谱存储

AuraDB 是 Neo4j 官方云托管, 使用同一个 neo4j Python driver。
与 Neo4jGraphStore 的唯一区别: connect() 使用 neo4j+s:// 加密 URI + 云端密码。

配置 (.env, GRAPH_STORE_PROVIDER=cloud):
    NEO4J_URI=neo4j+s://<your-db-id>.databases.neo4j.io
    NEO4J_PASSWORD=<aura password>
"""

from __future__ import annotations

from nexus.core.logger import get_logger
from nexus.rag.graph_store import Neo4jGraphStore

logger = get_logger(__name__)


class AuraGraphStore(Neo4jGraphStore):
    """Neo4j AuraDB 云端图谱存储。

    继承 Neo4jGraphStore 的全部 Cypher 逻辑, 仅连接参数走云端。
    AuraDB 使用 neo4j+s 协议 (TLS 加密), driver 自动处理, 无需额外代码。
    """

    def connect(self) -> None:
        """连接 AuraDB 云端。"""
        logger.info(
            "Connecting to Neo4j AuraDB",
            uri=self.config.uri,
            user=self.config.user,
        )
        # 父类 connect() 已处理 driver 创建 + verify_connectivity + 约束初始化
        super().connect()
        logger.info("AuraDB graph store connected")
```

### 10.4 新建 `backend_design/nexus/rag/graph_factory.py`

```python
"""
Graph Store Factory — 图谱存储工厂

根据 .env 的 GRAPH_STORE_PROVIDER 选择图谱后端:
  - local: 本地 Neo4j (Docker)
  - cloud: Neo4j AuraDB (官方云托管)
"""

from __future__ import annotations

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.aura_graph_store import AuraGraphStore
from nexus.rag.graph_base import BaseGraphStore
from nexus.rag.graph_store import Neo4jGraphStore

logger = get_logger(__name__)


def build_graph_store() -> BaseGraphStore:
    """根据 GRAPH_STORE_PROVIDER 配置选择图谱存储后端。

    Returns:
        BaseGraphStore 实例 (Neo4jGraphStore / AuraGraphStore)
    """
    provider = get_config().providers.normalized()["graph_store"]

    if provider == "cloud":
        logger.info("GraphStore provider: Neo4j AuraDB")
        return AuraGraphStore()

    # 默认 local
    logger.info("GraphStore provider: local Neo4j")
    return Neo4jGraphStore()
```

---

## 十一、Step 5：Reranker 双模式（本地 BGE ⇄ 硅基流动）

### 11.1 新建 `backend_design/nexus/rag/reranker_base.py`

```python
"""
Reranker Base — 重排抽象基类

定义重排服务的统一接口。本地 BGE CrossEncoder 与云端硅基流动 Rerank 都继承此类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseReranker(ABC):
    """重排服务抽象接口。

    子类必须实现 rerank(): 对检索结果按与 query 的相关度重排序, 返回 Top-K。
    输出约定: 每项新增 rerank_score 字段, 与现有 LocalReranker 保持一致。
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        text_field: str = "text",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """对检索结果重排。

        Args:
            query: 查询文本
            documents: 检索结果列表 (dict 列表)
            text_field: 文档中文本字段名
            top_k: 返回前 K 条

        Returns:
            重排后的 Top-K 结果列表, 每项新增 rerank_score 字段
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """检查 reranker 是否可用。"""
        raise NotImplementedError
```

### 11.2 改 `backend_design/nexus/rag/reranker.py`

文件顶部导入区追加：
```python
from nexus.rag.reranker_base import BaseReranker
```

类定义改为继承基类，并**保留类名 `RerankerService` 作为向后兼容别名**：
```python
class LocalReranker(BaseReranker):
    """Rerank 重排服务 (本地 BGE CrossEncoder)。

    使用 BAAI/bge-reranker-v2-m3 模型对检索结果进行二次排序。
    模型首次加载约2秒，后续推理 CPU 约200ms/20条。
    模型不可用时降级为原序返回前 top_k 条。
    """
    # ... 整个类体保持不变 ...
```

在文件**末尾**追加向后兼容别名（让旧代码 `from nexus.rag.reranker import RerankerService` 仍可用）：
```python
# 向后兼容别名: 旧代码引用 RerankerService 仍可工作
RerankerService = LocalReranker
```

> 这样 `retriever.py` / `unified_retriever.py` 里现有的 `RerankerService()` 调用不会报错，但 Step 8 会把它们改成 `build_reranker()`。

### 11.3 新建 `backend_design/nexus/rag/siliconflow_reranker.py`

```python
"""
SiliconFlow Reranker — 硅基流动云端重排

调用硅基流动 Rerank API (POST {ARK_BASE_URL}/rerank), 复用 ARK_API_KEY。
使用免费模型 BAAI/bge-reranker-v2-m3。

请求体: {"model": ..., "query": ..., "documents": [...], "top_n": k}
响应:   {"results": [{"index": 0, "relevance_score": 0.99}, ...]}

注意: 硅基流动返回的是 index + score, 需映射回原 documents 列表,
      保持与 LocalReranker 相同输出结构 (每项加 rerank_score 字段)。
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.reranker_base import BaseReranker

logger = get_logger(__name__)


class SiliconFlowReranker(BaseReranker):
    """硅基流动云端重排服务。

    复用 LLM/Embedding 的 ARK_API_KEY + ARK_BASE_URL, 同一平台同一 Key。
    """

    def __init__(self):
        self.config = get_config().llm
        self.rerank_config = get_config().reranker
        self._client = httpx.AsyncClient(
            base_url=self.config.ark_base_url,
            headers={
                "Authorization": f"Bearer {self.config.ark_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        text_field: str = "text",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """对检索结果重排 (硅基流动 API)。

        硅基流动 API 为同步 HTTP, 这里用 httpx 同步调用 (rerank 在检索链路中是阻塞步骤)。
        """
        if not documents:
            return []

        # 提取每条文档的文本
        texts: List[str] = []
        valid_docs: List[Dict[str, Any]] = []
        for doc in documents:
            text = doc.get(text_field, "") or doc.get("content", "") or str(doc)
            if text:
                texts.append(text)
                valid_docs.append(doc)
           if not texts:
            return documents[:top_k]

        try:
            # 硅基流动 Rerank 接口 (同步调用)
            response = self._client.post(
                "/rerank",
                json={
                    "model": self.rerank_config.model,
                    "query": query,
                    "documents": texts,
                    "top_n": min(top_k, len(texts)),
                    "return_documents": False,
                },
            )
            response.raise_for_status()
            data = response.json()

            # 映射回原 documents, 加 rerank_score
            results: List[Dict[str, Any]] = []
            for item in data.get("results", []):
                idx = item.get("index")
                score = float(item.get("relevance_score", 0.0))
                if idx is not None and 0 <= idx < len(valid_docs):
                    doc_with_score = dict(valid_docs[idx])
                    doc_with_score["rerank_score"] = round(score, 6)
                    results.append(doc_with_score)

            logger.info(
                f"SiliconFlow rerank done: {len(documents)} → {len(results)} docs"
            )
            return results if results else documents[:top_k]

        except Exception as e:
            logger.error(f"SiliconFlow rerank failed: {e}, falling back to original order")
            return documents[:top_k]

    @property
    def is_available(self) -> bool:
        return bool(self.config.ark_api_key)
```

### 11.4 新建 `backend_design/nexus/rag/reranker_factory.py`

```python
"""
Reranker Factory — 重排服务工厂

根据 .env 的 RERANKER_PROVIDER 选择重排后端:
  - local: 本地 BGE CrossEncoder (需下载模型)
  - cloud: 硅基流动 Rerank API (免费 bge-reranker-v2-m3)
  - none:  跳过重排 (省成本)
"""


from __future__ import annotations

from typing import Optional

from nexus.config import get_config
from nexus.core.logger import get_logger
from nexus.rag.reranker_base import BaseReranker
from nexus.rag.reranker import LocalReranker
from nexus.rag.siliconflow_reranker import SiliconFlowReranker

logger = get_logger(__name__)


class NoneReranker(BaseReranker):
    """空重排器 — 直接原序返回前 top_k 条, 不做重排。

    对应 RERANKER_PROVIDER=none, 给"不想花钱也不想下模型"的场景。
    """

    def rerank(
        self,
        query: str,
        documents: list,
        text_field: str = "text",
        top_k: int = 5,
    ) -> list:
        return documents[:top_k]

    @property
    def is_available(self) -> bool:
        return True


def build_reranker() -> Optional[BaseReranker]:
    """根据 RERANKER_PROVIDER 配置选择重排后端。

    Returns:
        BaseReranker 实例, 或 None (provider=none 时返回 NoneReranker, 不返回 None 以保持调用方简单)
    """
    provider = get_config().providers.normalized()["reranker"]

    if provider == "none":
        logger.info("Reranker provider: none (disabled)")
        return NoneReranker()
    if provider == "cloud":
        logger.info("Reranker provider: SiliconFlow API")
        return SiliconFlowReranker()

    # 默认 local
    logger.info("Reranker provider: local BGE")
    return LocalReranker()
```

---

## 十二、Step 6：微调 redis_cache.py

在 `backend_design/nexus/middleware/redis_cache.py` 的 `connect()` 方法里，`await self._redis.ping()` 之后、`await self._ensure_index()` 之前，加一段 provider 判断日志。

找到这段（约第 88-90 行）：
```python
            await self._redis.ping()
            await self._ensure_index()
            logger.info("Redis Stack semantic cache connected (v2.0 VECTOR index)")
```

改为：
```python
            await self._redis.ping()

            # 双模式: 云 Redis 通常无 RediSearch 模块, 跳过 VECTOR 索引走 scan 降级
            cache_provider = get_config().providers.normalized()["cache"]
            if cache_provider == "cloud":
                logger.info(
                    "Cloud Redis detected, semantic cache using scan fallback "
                    "(no RediSearch VECTOR index)"
                )
                self._index_ready = False
            else:
                await self._ensure_index()
                logger.info("Redis Stack semantic cache connected (v2.0 VECTOR index)")
```

> 文件顶部已有 `from nexus.config import get_config`，无需再加导入。
> 注意：即使不显式跳过，`_ensure_index()` 在云 Redis 上 `FT.CREATE` 失败也会自动 `_index_ready=False`（第 139-141 行 try/except）。这里显式判断只是让日志更清晰、避免无谓的报错噪音。

---

## 十三、Step 7：改 main.py 接工厂

在 `backend_design/nexus/main.py` 中做三处替换。

### 13.1 导入区

找到（约第 42-44 行）：
```python
from nexus.rag.embedding import EmbeddingService
from nexus.rag.graph_store import Neo4jGraphStore
from nexus.rag.vector_store import MilvusVectorStore
```

改为：
```python
from nexus.rag.embedding import EmbeddingService
from nexus.rag.graph_factory import build_graph_store
from nexus.rag.vector_factory import build_vector_store
```

### 13.2 向量库初始化（约第 70 行）

找到：
```python
    # --- 2. 初始化 Milvus 向量存储 ---
    vector_store = MilvusVectorStore(embedding_service)
```
改为：
```python
    # --- 2. 初始化向量存储 (本地 Milvus / 云端 Zilliz, 由 VECTOR_STORE_PROVIDER 决定) ---
    vector_store = build_vector_store(embedding_service)
```

### 13.3 图谱初始化（约第 79 行）

找到：
```python
    # --- 3. 初始化 Neo4j 图谱存储 ---
    graph_store = Neo4jGraphStore()
```
改为：
```python
    # --- 3. 初始化图谱存储 (本地 Neo4j / 云端 AuraDB, 由 GRAPH_STORE_PROVIDER 决定) ---
    graph_store = build_graph_store()
```

> Reranker 不在 main.py 初始化（它在 retriever 里按需创建），所以 main.py 只改这 3 处。

---
## 十四、Step 8：改初始化脚本 + retriever 调用点

### 14.1 改 `backend_design/scripts/init_milvus.py`

整文件替换为：
```python
"""
Initialize Milvus / Zilliz Collections
运行此脚本创建向量集合和索引
用法:
    python -m scripts.init_milvus              # 创建集合 (已存在则跳过)
    python -m scripts.init_milvus --rebuild    # 先删除再重建 (切换 embedding 维度时用)
"""

from __future__ import annotations

import sys

from nexus.config import get_config
from nexus.core.logger import get_logger, setup_logging
from nexus.rag.embedding import EmbeddingService
from nexus.rag.vector_factory import build_vector_store

logger = get_logger(__name__)


def main():
    setup_logging()
    rebuild = "--rebuild" in sys.argv

    provider = get_config().providers.normalized()["vector_store"]
    logger.info(f"Initializing vector store (provider={provider}, rebuild={rebuild})...")

    embedding_service = EmbeddingService()
    vector_store = build_vector_store(embedding_service)

    try:
        if rebuild:
            # 切换 embedding 模型导致维度变化时, 必须先删除旧集合再重建
            cfg = get_config().milvus
            logger.warning(f"Dropping collection '{cfg.collection_food}' for rebuild...")
            vector_store.drop_collection(cfg.collection_food)
            logger.warning(f"Dropping collection '{cfg.collection_memory}' for rebuild...")
            vector_store.drop_collection(cfg.collection_memory)

        vector_store.connect()
        logger.info("✅ Vector store collections initialized successfully!")
        logger.info(f"   - Food collection: {vector_store.config.collection_food}")
        logger.info(f"   - Memory collection: {vector_store.config.collection_memory}")
        logger.info(f"   - Embedding dim: {get_config().llm.embedding_dim}")
    except Exception as e:
        logger.error(f"❌ Vector store initialization failed: {e}")
        sys.exit(1)
    finally:
        vector_store.disconnect()


if __name__ == "__main__":
    main()
```

### 14.2 改 `backend_design/scripts/init_neo4j.py`

整文件替换为：
```python
"""
Initialize Neo4j / AuraDB Constraints and Indexes
运行此脚本创建约束和索引
用法: python -m scripts.init_neo4j
"""

from __future__ import annotations

import sys

from nexus.config import get_config
from nexus.core.logger import get_logger, setup_logging
from nexus.rag.graph_factory import build_graph_store

logger = get_logger(__name__)


def main():
    setup_logging()
    provider = get_config().providers.normalized()["graph_store"]
    logger.info(f"Initializing graph store (provider={provider})...")

    graph_store = build_graph_store()

    try:
        graph_store.connect()
        logger.info("✅ Graph store initialized successfully!")
        logger.info("   - Constraint: user_id_unique (User.id)")
        logger.info("   - Index: entity_name_index (Entity.name)")
    except Exception as e:
        logger.error(f"❌ Graph store initialization failed: {e}")
        sys.exit(1)
    finally:
        graph_store.close()


if __name__ == "__main__":
    main()
```

### 14.3 改 `backend_design/nexus/rag/retriever.py`

顶部导入区，把：
```python
from nexus.rag.reranker import RerankerService
from nexus.rag.vector_store import MilvusVectorStore
```
改为：
```python
from nexus.rag.graph_store import Neo4jGraphStore   # 保留, 类型注解用
from nexus.rag.reranker_base import BaseReranker
from nexus.rag.reranker_factory import build_reranker
from nexus.rag.vector_base import BaseVectorStore
```

> 注意原文件已有 `from nexus.rag.graph_store import Neo4jGraphStore`，别重复导入。

`GraphRAGRetriever.__init__` 改为：
```python
    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,       # ← 原 MilvusVectorStore
        graph_store: Optional[Neo4jGraphStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
        reranker: Optional[BaseReranker] = None,               # ← 原 RerankerService
        enable_rerank: bool = True,
        enable_bm25: bool = True,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or build_vector_store(self.embedding_service)  # ← 原 MilvusVectorStore(...)
        self.graph_store = graph_store or build_graph_store()                            # ← 原 Neo4jGraphStore()
        self.enable_rerank = enable_rerank
        self.enable_bm25 = enable_bm25

        # Rerank 服务 (由工厂按 provider 选择)
        self.reranker = reranker or (build_reranker() if enable_rerank else None)        # ← 原 RerankerService()
```

### 14.4 改 `backend_design/nexus/rag/unified_retriever.py`

顶部导入区，把：
```python
from nexus.rag.reranker import RerankerService
```
改为：
```python
from nexus.rag.reranker_base import BaseReranker
from nexus.rag.reranker_factory import build_reranker
```

`UnifiedRetriever.__init__` 改为：
```python
    def __init__(
        self,
        graph_rag: Optional[GraphRAGRetriever] = None,
        cherry_kb: Optional[CherryKnowledgeBase] = None,
        reranker: Optional[BaseReranker] = None,     # ← 原 RerankerService
    ):
        self.graph_rag = graph_rag or GraphRAGRetriever()
        self.cherry_kb = cherry_kb or CherryKnowledgeBase()
        self.reranker = reranker or build_reranker()  # ← 原 reranker (默认 None)
```

> 原 `unified_retriever.py` 的 `self.reranker = reranker` 默认是 None（不自动建 reranker）。改为 `or build_reranker()` 后会自动按 provider 创建。若想保持"默认不重排"的原行为，可保留 `self.reranker = reranker`，由调用方显式传 `build_reranker()`。**建议改为自动创建**（`or build_reranker()`），因为 provider=none 时 `build_reranker()` 返回 NoneReranker（原序返回，等价不重排），行为安全。

---

## 十五、Step 9：清理 MySQL 死配置

> **⚠️ 更新说明 (2026-07-11)**：MySQL 已重新加入 `docker-compose.yml` 和 `requirements.txt`（`aiomysql>=0.2.0`），因为 `config.py` 中的 `MySQLConfig` 一直保留且连接 URL 依赖 `aiomysql` 驱动。以下内容仅作为历史记录保留，实际部署时 MySQL 服务已恢复。

### 15.1 改 `docker-compose.yml`

删除整个 `mysql` 服务块（约第 106-118 行）：
```yaml
  # --- MySQL (User Data + Audit Log) ---       ← 删掉这整段
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: nexuscockpit
      MYSQL_DATABASE: nexus_cockpit
      MYSQL_CHARSET: utf8mb4
      MYSQL_COLLATION: utf8mb4_unicode_ci
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"
    command: --default-authentication-plugin=mysql_native_password --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

并在底部 `volumes:` 块里删除 `mysql_data:` 一行。

### 15.2 改 `backend_design/requirements.txt`

删除这三行（约第 43-45 行）：
```
SQLAlchemy==2.0.45       ← 删
aiomysql>=0.2.0          ← 删
alembic==1.17.2          ← 删
```

> `config.py` 里的 `MySQLConfig` 类和 `AppConfig.mysql` 字段**可保留**（删它要动 config 结构，且留着不影响运行——它从不被实例化使用）。若想彻底清理，可删 `MySQLConfig` 类定义和 `AppConfig` 里的 `mysql` 字段，但非必须。

---

## 十六、Step 10：验证

### 16.1 本地模式回归验证（确保不破坏现有功能）
1. `.env` 保持 `*_PROVIDER=local`，`docker compose up -d` 起本地中间件。
2. `cd backend_design && python -m nexus.main` 启动，看日志 `NexusCockpit ready!`。
3. `curl http://localhost:8000/health` 应返回各服务 connected。
4. `curl -X POST http://localhost:8000/chat -d '{"text":"把空调调到24度","user_id":"test"}'` 验证 RAG + Reranker + 车控链路。
5. `make init-db` 验证工厂函数初始化库正常。

### 16.2 云端模式切换验证
1. **先切 LLM/Embedding 到硅基流动**（改 `.env`）：
   ```ini
   ARK_API_KEY=<硅基流动 api key>
   ARK_BASE_URL=https://api.siliconflow.cn/v1
   EMBEDDING_MODEL=BAAI/bge-m3
   EMBEDDING_DIM=1024        # ⚠️ 必须改
   ```
   因维度变了，执行 `python -m scripts.init_milvus --rebuild` 重建 collection。
2. 重启后端，`curl -X POST http://localhost:8000/chat -d '{"text":"你好","user_id":"test"}'` 验证 LLM 走硅基流动、Embedding 维度 1024 正常。
3. 切 `VECTOR_STORE_PROVIDER=cloud` + 填 Zilliz URI/Token；`docker compose down` 停本地 Milvus。重启后日志显示 `VectorStore provider: Zilliz Cloud`，`/health` 的 milvus 仍 connected。
4. 切 `GRAPH_STORE_PROVIDER=cloud` + AuraDB URI，验证图谱。
5. 切 `CACHE_PROVIDER=cloud` + 云 Redis（无 RediSearch），验证语义缓存走 scan 降级、限流仍正常。
6. 切 `RERANKER_PROVIDER=cloud` + `RERANK_MODEL=BAAI/bge-reranker-v2-m3`，验证检索结果排序正常。
7. 全切云端后，`docker compose down` 全停，仅留后端 + 前端，验证"零本地中间件"也能跑。

### 16.3 单元验证（快速）
```bash
python -c "from nexus.rag.vector_factory import build_vector_store; print(type(build_vector_store()).__name__)"
python -c "from nexus.rag.graph_factory import build_graph_store; print(type(build_graph_store()).__name__)"
python -c "from nexus.rag.reranker_factory import build_reranker; print(type(build_reranker()).__name__)"
```
按 provider 返回对应类名（local → MilvusVectorStore/Neo4jGraphStore/LocalReranker，cloud → ZillizVectorStore/AuraGraphStore/SiliconFlowReranker）。

---


## 十七、风险与取舍

1. **云 Redis 语义缓存性能**：无 RediSearch 时走 O(n) scan，缓存量大时变慢。可接受，或后续上带 Search 模块的 Redis Enterprise。
2. **Zilliz/AuraDB 网络延迟**：云端比本地多几十 ms RTT，RAG 检索链路会略慢，但省去本地运维。
3. **Embedding 维度切换是高危操作**：换 embedding 模型（火山 2560 维 → 硅基流动 bge-m3 1024 维）必须同步改 `EMBEDDING_DIM` 并重建 Milvus collection，否则维度不匹配直接报错。`init_milvus --rebuild` 是切换时的必经步骤。
4. **硅基流动免费额度**：免费 embedding/rerank 模型有速率/用量限制，高频场景需升级付费档或切回本地模型。`RERANKER_PROVIDER=none` 可随时跳过 rerank 省成本。
5. **Embedding 仍是云端硬依赖**：RAG/缓存/记忆都依赖 Embedding API（火山或硅基流动），无论本地/云端中间件模式都需要 API Key（这点不变，但硅基流动免费档降低了成本门槛）。

---

## 十八、硅基流动 API 速查

- **Base URL**：`https://api.siliconflow.cn/v1`
- **认证**：`Authorization: Bearer <api_key>`（在控制台 https://cloud.siliconflow.cn 申请）
- **LLM 对话**：`POST /chat/completions`（OpenAI 兼容，模型如 `deepseek-ai/DeepSeek-V3`、`Qwen/Qwen2.5-7B-Instruct`）
- **Embedding**：`POST /embeddings`（模型 `BAAI/bge-m3`，维度 1024，免费）
- **Rerank**：`POST /rerank`（模型 `BAAI/bge-reranker-v2-m3`，免费）
- **切换方式**：只需在 `.env` 把 `ARK_BASE_URL` 改为硅基流动地址、`ARK_API_KEY` 换成硅基流动 Key、`LLM_MODEL`/`EMBEDDING_MODEL`/`EMBEDDING_DIM`/`RERANK_MODEL` 换成硅基流动模型，**代码零改动**。

> ⚠️ 硅基流动的模型 ID 和维度以官方文档为准，上线前请到 https://docs.siliconflow.cn 核对最新模型名与维度。bge-m3 实际维度为 1024。


