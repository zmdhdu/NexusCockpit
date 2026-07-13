---
name: rapid-dev
description: 当需要快速开发新功能、生成脚手架代码、实现原型或加速迭代时使用。覆盖 NexusCockpit 技术栈：FastAPI API、LangGraph Agent、Go 网关处理、React 组件、Zustand Store、Milvus 检索等场景。
---

## 权威入口

- `.catpaw/skills/rapid-dev/SKILL.md`

## 适用场景

- 快速搭建新的 FastAPI REST API 端点。
- 创建新的 LangGraph Expert Agent。
- 新增 Go 网关原生处理器。
- 生成新的 React/Next.js 页面或组件。
- 创建新的 Zustand Store。
- 快速集成新的第三方服务（Milvus、Redis、RabbitMQ 等）。
- 生成数据库模型和迁移脚本。
- 新增 Celery 异步任务。

## 非适用场景

- 不用于替代深度架构设计和技术选型。
- 不用于生成完整的生产级系统（仅提供起点）。
- 不用于代码质量审查（使用 `code-review`）。
- 不用于前端 UI 设计规范（使用 `fronted-design`）。

## 执行步骤

1. **需求解析**：明确功能目标、输入输出、约束条件。
2. **技术选型**：根据场景选择合适的框架和库（参考下方模板库）。
3. **脚手生成**：生成项目结构、入口文件、配置模板。
4. **核心实现**：编写关键业务逻辑，保持最小可用。
5. **集成测试**：生成基础测试用例，验证核心路径。
6. **文档同步**：调用 `doc-sync` 技能更新相关文档。

## NexusCockpit 快速开发模板库

### 1. FastAPI REST API 端点模板

```python
"""新的 REST API 路由模块。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nexus.core.auth import get_current_user
from nexus.core.tenant_context import get_cockpit_id

router = APIRouter(prefix="/api/v1/example", tags=["example"])

class ExampleRequest(BaseModel):
    """请求模型。"""
    name: str
    value: str

class ExampleResponse(BaseModel):
    """响应模型。"""
    id: int
    name: str
    status: str
    cockpit_id: str

@router.post("/", response_model=ExampleResponse)
async def create_example(
    req: ExampleRequest,
    user: dict = Depends(get_current_user),
    cockpit_id: str = Depends(get_cockpit_id),
):
    """创建示例资源。

    Args:
        req: 请求体
        user: 当前用户（JWT 解析）
        cockpit_id: 当前座舱 ID（contextvars）

    Returns:
        ExampleResponse: 创建结果
    """
    # TODO: 实现业务逻辑
    return ExampleResponse(id=1, name=req.name, status="created", cockpit_id=cockpit_id)
```

### 2. FastAPI SSE 流式端点模板

```python
"""SSE 流式响应端点。"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json
import asyncio

router = APIRouter()

@router.post("/stream")
async def stream_response(message: str):
    """SSE 流式返回。"""
    async def event_generator():
        for i in range(10):
            data = {"content": f"chunk {i}", "index": i}
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(0.1)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
```

### 3. LangGraph Expert Agent 模板

```python
"""新的 Expert Agent — 参照 nexus/agent/experts/base.py。"""
from typing import Dict, Any
from langchain_core.language_models import BaseChatModel

from nexus.models.state import SupervisorState

class CustomExpert:
    """自定义专家 Agent。

    每个 Expert 负责一类特定任务，由 Supervisor 调度。
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.name = "custom_expert"

    async def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        """执行专家逻辑。

        Args:
            state: Supervisor 共享状态

        Returns:
            包含 expert_results 的状态更新
        """
        user_input = state["messages"][-1]
        # TODO: 实现专家逻辑
        response = f"Custom expert processed: {user_input}"
        return {
            "expert_results": [{"expert": self.name, "response": response}]
        }
```

### 4. Go 网关原生处理器模板

```go
// NewHandler 新的 Go 原生处理器
package handlers

import (
    "github.com/gin-gonic/gin"
    "nexus_gate/internal/config"
)

// GetCustomData 处理自定义数据请求（Go 原生，不转发 Python）
func GetCustomData(c *gin.Context) {
    cfg := config.Get()

    // 从 Redis 获取数据
    redisClient := NewRedisClient(cfg.RedisHost, cfg.RedisPort, cfg.RedisPassword, 0)
    defer redisClient.Close()

    // TODO: 实现业务逻辑

    c.JSON(200, gin.H{
        "data":   "result",
        "source": "go_native",
    })
}
```

### 5. React 页面组件模板

```tsx
"use client"
import { useState, useEffect, useCallback } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { useAuth } from "@/stores/auth-store"
import { cn } from "@/lib/utils"

export default function CustomPage() {
  const { token, cockpitId } = useAuth()
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    if (!token || !cockpitId) return
    try {
      const res = await api.get(`/custom/${cockpitId}`)
      setData(res.data.items || [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "加载失败")
    } finally {
      setLoading(false)
    }
  }, [token, cockpitId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  if (loading) return <div className="p-4">加载中...</div>

  return (
    <div className="p-4 space-y-4">
      {data.map((item, i) => (
        <div key={i} className={cn("p-4 rounded-lg border")}>
          {item.name}
        </div>
      ))}
    </div>
  )
}
```

### 6. Zustand Store 模板

```tsx
import { create } from "zustand"
import { persist } from "zustand/middleware"

interface CustomItem {
  id: string
  name: string
}

interface CustomState {
  items: CustomItem[]
  loading: boolean
  addItem: (item: CustomItem) => void
  removeItem: (id: string) => void
  clear: () => void
}

export const useCustomStore = create<CustomState>()(
  persist(
    (set) => ({
      items: [],
      loading: false,
      addItem: (item) => set((s) => ({ items: [...s.items, item] })),
      removeItem: (id) => set((s) => ({ items: s.items.filter((i) => i.id !== id) })),
      clear: () => set({ items: [] }),
    }),
    { name: "custom-storage" }
  )
)
```

### 7. Milvus 向量检索模板

```python
"""Milvus 向量检索 — 参照 nexus/rag/vector_store.py。"""
from pymilvus import connections, Collection

class VectorStore:
    """Milvus 向量存储管理器。"""

    def __init__(self, uri: str, collection_name: str):
        connections.connect(alias="default", uri=uri)
        self.collection = Collection(collection_name)
        self.collection.load()

    def search(self, vector: list, top_k: int = 5, filter_expr: str = ""):
        """向量相似度搜索。

        Args:
            vector: 查询向量
            top_k: 返回 Top-K 结果
            filter_expr: 过滤表达式（如 user_id == "u1"）

        Returns:
            搜索结果列表
        """
        results = self.collection.search(
            data=[vector],
            anns_field="vector",
            param={"metric_type": "IP", "params": {"ef": 64}},
            limit=top_k,
            expr=filter_expr,
            output_fields=["text", "id", "user_id"],
        )
        return results[0] if results else []
```

### 8. Celery 异步任务模板

```python
"""Celery 异步任务 — 参照 nexus/middleware/task_queue.py。"""
from celery_app import celery_app
import asyncio

@celery_app.task(name="nexus.tasks.custom_task")
def task_custom(param: str):
    """自定义异步任务。

    Args:
        param: 任务参数

    Returns:
        任务执行结果
    """
    async def _run():
        # TODO: 实现异步逻辑
        return f"Processed: {param}"

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
```

### 9. Neo4j 图谱操作模板

```python
"""Neo4j 图谱操作 — 参照 nexus/rag/graph_store.py。"""
from neo4j import GraphDatabase

class GraphStore:
    """Neo4j 图谱存储管理器。"""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def upsert_relation(self, user_id: str, relation: str, target: str, target_type: str, mid: int):
        """创建或更新关系（幂等）。

        Args:
            user_id: 用户 ID
            relation: 关系类型（如 LIKES, ALLERGY）
            target: 目标实体名称
            target_type: 目标实体类型（如 Food, Music）
            mid: Milvus 向量 ID（用于双向查找）
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (u:User {id: $user_id})
                MERGE (t:%s {name: $target})
                MERGE (u)-[r:%s]->(t)
                SET r.mid = $mid, r.timestamp = timestamp()
                """ % (target_type, relation),
                user_id=user_id, target=target, mid=mid,
            )
```

## 常见陷阱

- 过度生成代码，导致原型过于复杂难以迭代。
- 忽略错误处理和边界条件，原型可用但不可扩展。
- 未考虑并发安全，多线程/异步场景下出问题。
- 新增 API 端点后忘记在 `router.go` 或 `main.py` 中注册路由。
- 新增 Expert Agent 后忘记在 `supervisor_graph.py` 中添加节点和边。
- 新增前端页面后忘记在 `sidebar.tsx` 中添加导航菜单。
- 新增 Celery 任务后忘记在文档中登记。
