---
name: rapid-dev
description: 当需要快速开发新功能、生成脚手架代码、实现原型或加速迭代时使用。覆盖 API 开发、数据处理、模型推理、前端组件等场景。
---

## 权威入口

- `.catpaw/skills/rapid-dev/SKILL.md`

## 适用场景

- 快速搭建 RESTful API（FastAPI / Flask）。
- 生成数据处理管道脚手代码。
- 实现模型推理服务封装。
- 创建 React / Vue 前端组件。
- 生成数据库模型和迁移脚本。
- 快速集成第三方服务（Milvus、Redis、RabbitMQ 等）。

## 非适用场景

- 不用于替代深度架构设计和技术选型。
- 不用于生成完整的生产级系统（仅提供起点）。

## 执行步骤

1. **需求解析**：明确功能目标、输入输出、约束条件。
2. **技术选型**：根据场景选择合适的框架和库。
3. **脚手生成**：生成项目结构、入口文件、配置模板。
4. **核心实现**：编写关键业务逻辑，保持最小可用。
5. **集成测试**：生成基础测试用例，验证核心路径。
6. **文档同步**：生成简要使用说明和运行步骤。

## 快速开发模板库

### FastAPI 服务模板
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Service Name", version="1.0.0")

class ItemRequest(BaseModel):
    """请求模型"""
    name: str
    value: str

class ItemResponse(BaseModel):
    """响应模型"""
    id: int
    name: str
    status: str

@app.post("/api/items", response_model=ItemResponse)
async def create_item(req: ItemRequest):
    # 业务逻辑
    return ItemResponse(id=1, name=req.name, status="created")
```

### Milvus 向量检索模板
```python
from pymilvus import connections, Collection

class VectorStore:
    def __init__(self, uri: str, collection_name: str):
        connections.connect(alias="default", uri=uri)
        self.collection = Collection(collection_name)
        self.collection.load()

    def search(self, vector: list, top_k: int = 5, filter_expr: str = ""):
        results = self.collection.search(
            data=[vector], anns_field="vector",
            param={"metric_type": "IP", "params": {"ef": 64}},
            limit=top_k, expr=filter_expr,
            output_fields=["text", "id"]
        )
        return results[0] if results else []
```

### LangChain RAG 模板
```python
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

def build_rag_chain(llm, retriever):
    prompt = ChatPromptTemplate.from_messages([
        ("system", "基于以下上下文回答用户问题：\n{context}"),
        ("human", "{question}")
    ])
    chain = prompt | llm | StrOutputParser()
    return chain
```

## 常见陷阱

- 过度生成代码，导致原型过于复杂难以迭代。
- 忽略错误处理和边界条件，原型可用但不可扩展。
- 未考虑并发安全，多线程/异步场景下出问题。
