---
name: code-doc
description: 当需要为代码生成注释、文档字符串、API 文档或 README 时使用。支持 Python、JavaScript、TypeScript 等语言，自动生成符合规范的 docstring 和 inline 注释。
---

## 权威入口

- `.catpaw/skills/code-doc/SKILL.md`

## 适用场景

- 为无注释的遗留代码补充文档。
- 生成函数/类/模块级别的 docstring。
- 编写 API 接口文档（OpenAPI / Swagger 风格）。
- 为复杂算法添加行内注释。
- 生成项目 README 和架构说明文档。

## 非适用场景

- 不用于为简单赋值语句或显而易见的代码添加冗余注释。
- 不用于替代设计文档或需求文档。

## 执行步骤

1. **分析代码结构**：识别模块、类、函数的职责和依赖关系。
2. **推断意图**：通过调用链和上下文理解代码的业务目的。
3. **生成 Docstring**：按 Google / NumPy / Sphinx 风格生成函数文档。
4. **补充行内注释**：仅对非显而易见的逻辑添加解释。
5. **生成模块文档**：概述模块职责、关键类/函数、使用示例。
6. **更新 README**：同步更新项目说明文档。

## 文档规范

### Python Docstring（Google 风格）
```python
def search_memory(query: str, user_id: str, top_k: int = 3) -> list:
    """检索特定用户的语义记忆。

    Args:
        query: 查询文本，将通过 Embedding 模型转向量。
        user_id: 用户唯一标识，用于过滤记忆范围。
        top_k: 返回的最相似记忆数量。

    Returns:
        包含记忆字典的列表，每个字典包含 id、text、score 字段。

    Raises:
        ConnectionError: 当 Milvus 连接不可用时抛出。
    """
```

### 注释原则
- **Why > What**：注释解释"为什么"而非"做了什么"。
- **简洁精准**：每条注释不超过两行，避免段落式注释。
- **同步更新**：代码变更时同步更新注释，禁止过期注释。

## 常见陷阱

- 逐行翻译代码为注释，产生噪音而非信息。
- 生成的 docstring 参数名与实际参数不匹配。
- 忽略异步函数的 docstring 需要标注 coroutine。
