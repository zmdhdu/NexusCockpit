# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
NexusCockpit 配置中心 (Configuration Center)

本模块是整个后端的"配置大脑"，所有组件（数据库、缓存、LLM、车控等）
的连接地址、API Key、超时时间等参数都集中在这里管理。

工作原理:
  1. 使用 Pydantic Settings 库实现类型安全的配置管理
  2. 自动从项目根目录的 .env 文件读取环境变量
  3. 提供全局单例 get_config() 供其他模块使用

路径说明:
  本文件位于 backend_design/nexus/config.py
  项目根目录 (NexusCockpit/) 在此文件向上三级
  .env 文件、models/、data/、assets/ 等目录均位于项目根目录下
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ============================================================
# 路径常量 — 自动定位项目根目录
# ============================================================
# config.py 的位置: NexusCockpit/backend_design/nexus/config.py
# 向上三级 (__file__ → nexus/ → backend_design/ → NexusCockpit/) 得到项目根目录
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# ============================================================
# 环境文件加载策略 (local / prod 自动切换)
# ============================================================
# 优先级 (从高到低):
#   1. 环境变量 APP_ENV=prod → 加载 .env.prod
#   2. 环境变量 APP_ENV=local → 加载 .env.local
#   3. 默认 (未设置 APP_ENV) → 加载 .env.local (本地开发默认)
#   4. 如果目标文件不存在 → 回退到 .env (兼容旧逻辑)
#
# 使用方式:
#   本地开发: 无需设置，默认加载 .env.local
#   线上生产: export APP_ENV=prod  (或 docker 环境变量 APP_ENV=prod)

_APP_ENV = os.getenv("APP_ENV", "local").strip().lower()
_ENV_LOCAL = os.path.join(_PROJECT_ROOT, ".env.local")
_ENV_PROD = os.path.join(_PROJECT_ROOT, ".env.prod")
_ENV_FALLBACK = os.path.join(_PROJECT_ROOT, ".env")

if _APP_ENV == "prod" and os.path.exists(_ENV_PROD):
    _ENV_FILE = _ENV_PROD
elif _APP_ENV == "local" and os.path.exists(_ENV_LOCAL):
    _ENV_FILE = _ENV_LOCAL
elif os.path.exists(_ENV_LOCAL):
    _ENV_FILE = _ENV_LOCAL
else:
    _ENV_FILE = _ENV_FALLBACK

# 显式加载环境文件到 os.environ，确保 .env.local 中的值不会被 .env 中的空值覆盖
# pydantic-settings 在读取 env_file 时可能会被其他 .env 文件干扰
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_ENV_FILE, override=True)
except ImportError:
    pass


def _resolve_path(relative_path: str) -> str:
    """将相对路径 (如 ./models/asr) 解析为基于项目根目录的绝对路径。

    为什么需要这个函数:
        项目可能在任意目录下被启动 (如从 backend_design/ 启动或从根目录启动)，
        使用相对路径会因工作目录不同而失效。此函数确保所有路径都基于项目根目录。

    Args:
        relative_path: 以 ./ 开头的相对路径，或已经是绝对路径。

    Returns:
        解析后的绝对路径字符串。
    """
    # 如果已经是绝对路径 (如 C:\...)，直接返回
    if os.path.isabs(relative_path):
        return relative_path
    # 去掉开头的 ./ 前缀，然后拼接到项目根目录
    clean = relative_path.lstrip("./") if relative_path.startswith("./") else relative_path
    return os.path.join(_PROJECT_ROOT, clean)


class LLMConfig(BaseSettings):
    """大语言模型 (LLM) 配置。

    管理与 LLM 供应商 (硅基流动 / 火山方舟) 的连接参数，两者均为 OpenAI 兼容 API。
    """

    # LLM API Key (硅基流动 / 火山方舟均兼容)，从 .env 的 ARK_API_KEY 读取
    ark_api_key: str = Field(default="", validation_alias="ARK_API_KEY")
    # API 基础地址 (默认硅基流动，可切换为火山方舟)
    ark_base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        validation_alias="ARK_BASE_URL",
    )
    # 对话使用的 LLM 模型名称
    llm_model: str = Field(default="deepseek-ai/DeepSeek-V3", validation_alias="LLM_MODEL")
    # Embedding 向量化使用的模型
    embedding_model: str = Field(
        default="Qwen/Qwen3-Embedding-4B", validation_alias="EMBEDDING_MODEL"
    )
    # Embedding 向量维度 (必须与模型匹配)
    embedding_dim: int = Field(default=2560, validation_alias="EMBEDDING_DIM")
    # LLM 生成温度: 越高越随机，越低越确定
    temperature: float = Field(default=0.7)
    # 单次生成的最大 token 数
    max_tokens: int = Field(default=512)
    # API 调用超时时间 (秒)
    timeout: float = Field(default=30.0)

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @computed_field
    @property
    def embedding_url(self) -> str:
        """Embedding API 的完整 URL (base_url + /embeddings)"""
        return f"{self.ark_base_url}/embeddings"


class MilvusConfig(BaseSettings):
    """Milvus 向量数据库配置。

    Milvus 用于存储和检索语义向量，支持食物知识库搜索和用户记忆召回。
    """

    host: str = Field(default="127.0.0.1", validation_alias="MILVUS_HOST")
    port: int = Field(default=19530, validation_alias="MILVUS_PORT")
    uri: str = Field(default="http://127.0.0.1:19530", validation_alias="MILVUS_URI")
    token: str = Field(default="", validation_alias="MILVUS_TOKEN")
    # 食物知识库的 collection 名称
    collection_food: str = Field(
        default="Food_List", validation_alias="MILVUS_COLLECTION_FOOD"
    )
    # 用户记忆的 collection 名称
    collection_memory: str = Field(
        default="User_Memory", validation_alias="MILVUS_COLLECTION_MEMORY"
    )
    # Milvus 连接别名 (用于多实例区分)
    alias: str = "nexus_link"
    # 索引类型: HNSW (分层可导航小世界图，适合高召回率场景)
    index_type: str = "HNSW"
    # 距离度量: IP (内积)，用于余弦相似度
    metric_type: str = "IP"
    # HNSW 索引参数: M=每层连接数, efConstruction=建图精度
    index_params: dict = Field(
        default_factory=lambda: {"M": 16, "efConstruction": 200}
    )
    # HNSW 搜索参数: ef=搜索时的候选队列大小
    search_params: dict = Field(default_factory=lambda: {"ef": 64})

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class Neo4jConfig(BaseSettings):
    """Neo4j 知识图谱配置。

    Neo4j 存储用户画像、偏好关系等图结构数据，与 Milvus 向量检索融合 (GraphRAG)。
    """

    uri: str = Field(default="bolt://127.0.0.1:7687", validation_alias="NEO4J_URI")
    user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    password: str = Field(default="nexuscockpit", validation_alias="NEO4J_PASSWORD")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class RedisConfig(BaseSettings):
    """Redis 缓存配置。

    Redis 承担两个职责:
    1. 语义缓存 — 基于向量相似度复用历史回答，减少 LLM 调用
    2. 限流器 — 使用令牌桶算法控制请求频率
    """

    host: str = Field(default="127.0.0.1", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    password: str = Field(default="", validation_alias="REDIS_PASSWORD")
    db: int = Field(default=0, validation_alias="REDIS_DB")

    # --- 语义缓存参数 ---
    # 是否启用语义缓存
    cache_enabled: bool = Field(default=True, validation_alias="SEMANTIC_CACHE_ENABLED")
    # 相似度阈值: 超过此值则复用缓存 (0~1，越大越严格)
    cache_similarity_threshold: float = Field(
        default=0.92, validation_alias="SEMANTIC_CACHE_SIMILARITY_THRESHOLD"
    )
    # 缓存过期时间 (秒)，默认 1 小时
    cache_ttl: int = Field(
        default=3600, validation_alias="SEMANTIC_CACHE_TTL_SECONDS"
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @computed_field
    @property
    def url(self) -> str:
        """Redis 连接 URL (redis://[password@]host:port/db)"""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class RabbitMQConfig(BaseSettings):
    """RabbitMQ 消息队列配置。

    RabbitMQ 用于 Celery 异步任务队列，处理耗时操作 (如批量 Embedding 生成)。
    """

    host: str = Field(default="127.0.0.1", validation_alias="RABBITMQ_HOST")
    port: int = Field(default=5672, validation_alias="RABBITMQ_PORT")
    user: str = Field(default="guest", validation_alias="RABBITMQ_USER")
    password: str = Field(default="guest", validation_alias="RABBITMQ_PASSWORD")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @computed_field
    @property
    def url(self) -> str:
        """AMQP 连接 URL"""
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}//"


class MySQLConfig(BaseSettings):
    """MySQL 数据库配置。

    MySQL 存储用户账号、会话历史、系统配置等持久化数据。
    """

    host: str = Field(default="127.0.0.1", validation_alias="MYSQL_HOST")
    port: int = Field(default=3306, validation_alias="MYSQL_PORT")
    user: str = Field(default="root", validation_alias="MYSQL_USER")
    password: str = Field(default="nexuscockpit", validation_alias="MYSQL_PASSWORD")
    database: str = Field(default="nexus_cockpit", validation_alias="MYSQL_DATABASE")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @computed_field
    @property
    def url(self) -> str:
        """异步 MySQL 连接 URL (使用 aiomysql 驱动)"""
        return (
            f"mysql+aiomysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        )


class JWTConfig(BaseSettings):
    """JWT 认证配置。

    用于用户登录后的 Token 签发与验证，保护 API 接口安全。
    """

    # JWT 签名密钥 (生产环境必须修改)
    secret_key: str = Field(
        default="change-me-in-production", validation_alias="JWT_SECRET_KEY"
    )
    # 签名算法
    algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    # Token 过期时间 (分钟)，默认 24 小时
    expire_minutes: int = Field(default=1440, validation_alias="JWT_EXPIRE_MINUTES")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class VehicleConfig(BaseSettings):
    """车控总线配置。

    控制车控指令的发送方式:
    - mock: 模拟模式 (开发测试用，不发送真实指令)
    - http: HTTP REST 模式 (通过 HTTP 接口发送到车机)
    - mcp: MCP stdio 模式 (通过标准输入输出与 MCP 服务通信)
    """

    # 适配器类型: mock / http / mcp
    adapter: str = Field(default="mock", validation_alias="VEHICLE_ADAPTER")
    # HTTP 模式的车机 API 地址
    api_base_url: str = Field(default="", validation_alias="VEHICLE_API_BASE_URL")
    # HTTP 模式的协议类型
    api_protocol: str = Field(default="rest", validation_alias="VEHICLE_API_PROTOCOL")
    # HTTP 模式的接口路径
    api_endpoint: str = Field(
        default="/vehicle/tools/invoke", validation_alias="VEHICLE_API_ENDPOINT"
    )
    # HTTP 调用超时时间 (秒)
    api_timeout: float = Field(default=5.0, validation_alias="VEHICLE_API_TIMEOUT")
    # HTTP 认证 Token
    api_token: Optional[str] = Field(default=None, validation_alias="VEHICLE_API_TOKEN")
    # MCP 模式的启动命令 (如 "python vehicle_mcp_server.py")
    mcp_command: str = Field(default="", validation_alias="VEHICLE_MCP_COMMAND")
    # MCP 启动参数
    mcp_args: str = Field(default="", validation_alias="VEHICLE_MCP_ARGS")
    # MCP 工作目录
    mcp_workdir: str = Field(default="", validation_alias="VEHICLE_MCP_WORKDIR")
    # 是否验证 MCP 工具列表
    mcp_validate_tools: bool = Field(
        default=True, validation_alias="VEHICLE_MCP_VALIDATE_TOOLS"
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class ASRConfig(BaseSettings):
    """语音识别 / 语音合成模型路径配置。

    所有路径使用项目根目录的相对路径，确保项目可整体迁移。
    模型文件需提前下载，详见 docs/deployment/SETUP.md。
    """

    # FunASR (SenseVoice) 语音识别模型路径
    funasr_model_path: str = Field(
        default="./models/asr/sensevoice",
        validation_alias="FUNASR_MODEL_PATH",
    )
    # CAM++ 声纹识别模型路径 (用于说话人验证)
    cam_model_path: str = Field(
        default="./models/sv/cam_plus",
        validation_alias="CAM_MODEL_PATH",
    )
    # CosyVoice 语音合成模型路径
    cosyvoice_model_path: str = Field(
        default="./models/tts/cosyvoice",
        validation_alias="COSYVOICE_MODEL_PATH",
    )
    # 本地 LLM 模型路径 (可选，用于端侧部署降级)
    local_llm_model_path: str = Field(
        default="./models/llm/qwen", validation_alias="LOCAL_LLM_MODEL_PATH"
    )
    # 是否使用本地 LLM (False=用云端 Ark API)
    use_local_llm: bool = Field(default=False, validation_alias="USE_LOCAL_LLM")

    # --- 声纹验证音频目录 ---
    # 注册音频目录: 存放用户预先录制的声纹样本
    speaker_enroll_dir: str = Field(
        default="./assets/speaker/enroll_wav",
        validation_alias="SPEAKER_ENROLL_DIR",
    )
    # 用户声纹目录: 存放每个用户的声纹特征文件
    speaker_users_dir: str = Field(
        default="./assets/speaker/users",
        validation_alias="SPEAKER_USERS_DIR",
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def resolved_funasr_path(self) -> str:
        """返回基于项目根目录解析后的 ASR 模型绝对路径。"""
        return _resolve_path(self.funasr_model_path)

    def resolved_cam_path(self) -> str:
        """返回基于项目根目录解析后的声纹模型绝对路径。"""
        return _resolve_path(self.cam_model_path)

    def resolved_cosyvoice_path(self) -> str:
        """返回基于项目根目录解析后的 TTS 模型绝对路径。"""
        return _resolve_path(self.cosyvoice_model_path)

    def resolved_llm_path(self) -> str:
        """返回基于项目根目录解析后的本地 LLM 绝对路径。"""
        return _resolve_path(self.local_llm_model_path)

    def resolved_speaker_enroll_dir(self) -> str:
        """返回声纹注册音频目录的绝对路径。"""
        return _resolve_path(self.speaker_enroll_dir)

    def resolved_speaker_users_dir(self) -> str:
        """返回声纹用户目录的绝对路径。"""
        return _resolve_path(self.speaker_users_dir)


class LangfuseConfig(BaseSettings):
    """Langfuse 可观测性配置。

    Langfuse 是专为 LLM 应用设计的追踪平台，记录每次 Agent 调用的完整链路。
    仅当 public_key 和 secret_key 都配置时才启用。
    """

    public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    host: str = Field(
        default="https://cloud.langfuse.com", validation_alias="LANGFUSE_HOST"
    )
    enabled: bool = False  # 自动计算，无需手动配置

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def model_post_init(self, __context) -> None:
        """模型初始化后自动判断是否启用 Langfuse。"""
        self.enabled = bool(self.public_key and self.secret_key)


class ServerConfig(BaseSettings):
    """FastAPI 服务器配置。"""

    # 监听地址 (0.0.0.0 表示所有网卡)
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    # 监听端口
    port: int = Field(default=8000, validation_alias="PORT")
    # 调试模式 (开启热重载)
    debug: bool = Field(default=True, validation_alias="DEBUG")
    # 日志级别
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    # CORS 允许的来源 (* 表示允许所有)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"]
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class TavilyConfig(BaseSettings):
    """Tavily 搜索配置。

    Tavily 是专为 AI 设计的搜索引擎，用于联网搜索技能 (如查天气、查新闻)。
    """

    api_key: str = Field(default="", validation_alias="TAVILY_API_KEY")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class AmapConfig(BaseSettings):
    """高德地图 API 配置。

    用于逆地理编码（坐标→地址）和 POI 周边搜索（周边美食/加油站/停车场等）。
    申请: https://lbs.amap.com/api/webservice/guide/create-project/get-key
    """

    api_key: str = Field(default="", validation_alias="AMAP_KEY")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


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


class DataConfig(BaseSettings):
    """数据目录配置 — 所有路径使用项目根目录的相对路径。"""

    # 食物知识库数据目录
    food_data_dir: str = Field(
        default="./data/food", validation_alias="FOOD_DATA_DIR"
    )
    # 知识文档目录
    knowledge_data_dir: str = Field(
        default="./data/knowledge", validation_alias="KNOWLEDGE_DATA_DIR"
    )
    # 用户上传文件目录
    upload_dir: str = Field(
        default="./data/uploads", validation_alias="UPLOAD_DIR"
    )
    # 临时文件目录
    temp_dir: str = Field(
        default="./data/temp", validation_alias="TEMP_DIR"
    )

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def resolved_food_dir(self) -> str:
        """食物数据目录的绝对路径"""
        return _resolve_path(self.food_data_dir)

    def resolved_knowledge_dir(self) -> str:
        """知识文档目录的绝对路径"""
        return _resolve_path(self.knowledge_data_dir)

    def resolved_upload_dir(self) -> str:
        """上传文件目录的绝对路径"""
        return _resolve_path(self.upload_dir)

    def resolved_temp_dir(self) -> str:
        """临时文件目录的绝对路径"""
        return _resolve_path(self.temp_dir)


class OSSConfig(BaseSettings):
    """阿里云 OSS 对象存储配置。

    OSS 用于存储音频文件、用户上传文件等大文件，
    减轻本地磁盘压力并提供 CDN 加速访问。
    """

    # OSS AccessKey (从阿里云控制台获取)
    access_key: str = Field(default="", validation_alias="OSS_ACCESS_KEY")
    # OSS SecretKey
    secret_key: str = Field(default="", validation_alias="OSS_SECRET_KEY")
    # Bucket 名称
    bucket_name: str = Field(
        default="project-zmd", validation_alias="OSS_BUCKET_NAME"
    )
    # OSS Endpoint (区域节点)
    endpoint: str = Field(
        default="oss-cn-beijing.aliyuncs.com",
        validation_alias="OSS_ENDPOINT",
    )
    # OSS 区域
    region: str = Field(default="cn-beijing", validation_alias="OSS_REGION")
    # 公开访问的基础 URL (如通过 CDN 域名)
    public_base_url: str = Field(
        default="", validation_alias="OSS_PUBLIC_BASE_URL"
    )
    enabled: bool = False  # 自动计算

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    def model_post_init(self, __context) -> None:
        """初始化后自动计算 enabled 和 public_base_url。"""
        self.enabled = bool(self.access_key and self.secret_key)
        # 如果未配置自定义域名，则使用默认 OSS 域名
        if not self.public_base_url and self.bucket_name:
            self.public_base_url = (
                f"https://{self.bucket_name}.{self.endpoint}"
            )


class CockpitSettings(BaseSettings):
    """v2.1 多座舱配置。

    控制多座舱行为，包括座舱数量、隔离模式、SubAgent 巡检等。
    """

    # 默认座舱数量
    default_cockpit_count: int = Field(default=3, validation_alias="COCKPIT_COUNT")
    # SubAgent 巡检间隔范围（秒）
    subagent_check_interval_min: int = Field(default=30, validation_alias="SUBAGENT_CHECK_MIN")
    subagent_check_interval_max: int = Field(default=60, validation_alias="SUBAGENT_CHECK_MAX")
    # MainAgent 确认是否启用
    mainagent_confirm_enabled: bool = Field(default=True, validation_alias="MAINAGENT_CONFIRM_ENABLED")
    # 隔离模式: strict(每座舱独立DB) / shared(共享DB+前缀)
    isolation_mode: str = Field(default="shared", validation_alias="COCKPIT_ISOLATION_MODE")
    # SubAgent 使用的 LLM 模型（降本策略：用便宜模型）
    subagent_llm_model: str = Field(default="Qwen/Qwen2.5-7B-Instruct", validation_alias="SUBAGENT_LLM_MODEL")
    # Go 网关配置
    gate_host: str = Field(default="0.0.0.0", validation_alias="NEXUS_GATE_HOST")
    gate_port: int = Field(default=8080, validation_alias="NEXUS_GATE_PORT")
    gate_mode: str = Field(default="proxy", validation_alias="NEXUS_GATE_MODE")  # proxy / grpc
    # RBAC 配置
    rbac_default_role: str = Field(default="cockpit_user", validation_alias="RBAC_DEFAULT_ROLE")
    rbac_admin_username: str = Field(default="admin", validation_alias="RBAC_ADMIN_USERNAME")
    # 声纹配置
    voiceprint_model: str = Field(default="cam_plus", validation_alias="VOICEPRINT_MODEL")
    voiceprint_threshold: float = Field(default=0.7, validation_alias="VOICEPRINT_THRESHOLD")
    voiceprint_enroll_count: int = Field(default=3, validation_alias="VOICEPRINT_ENROLL_COUNT")

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")


class AppConfig(BaseSettings):
    """全局应用配置 — 所有子配置的聚合入口。

    这是整个配置体系的根，通过 get_config() 获取全局单例。
    包含 LLM、数据库、缓存、车控、OSS 等所有子系统的配置。
    """

    llm: LLMConfig = Field(default_factory=LLMConfig)
    milvus: MilvusConfig = Field(default_factory=MilvusConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    rabbitmq: RabbitMQConfig = Field(default_factory=RabbitMQConfig)
    mysql: MySQLConfig = Field(default_factory=MySQLConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    vehicle: VehicleConfig = Field(default_factory=VehicleConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    oss: OSSConfig = Field(default_factory=OSSConfig)
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    tavily: TavilyConfig = Field(default_factory=TavilyConfig)
    amap: AmapConfig = Field(default_factory=AmapConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    cockpit: CockpitSettings = Field(default_factory=CockpitSettings)

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @computed_field
    @property
    def project_root(self) -> str:
        """项目根目录的绝对路径 (NexusCockpit/)"""
        return _PROJECT_ROOT


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """获取全局配置单例。

    使用 lru_cache 确保整个应用生命周期内只创建一次配置实例，
    避免重复读取 .env 文件。

    Returns:
        AppConfig 全局配置对象
    """
    return AppConfig()


# ============================================================
# 快捷访问函数 — 避免每次都调用 get_config().xxx
# ============================================================

def get_llm_config() -> LLMConfig:
    """快捷获取 LLM 配置"""
    return get_config().llm


def get_milvus_config() -> MilvusConfig:
    """快捷获取 Milvus 配置"""
    return get_config().milvus


def get_redis_config() -> RedisConfig:
    """快捷获取 Redis 配置"""
    return get_config().redis
