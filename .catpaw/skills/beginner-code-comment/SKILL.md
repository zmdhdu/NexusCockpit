---
name: beginner-code-comment
description: 面向编程小白的代码注释技能。用通俗易懂的中文为每一行/每一段代码添加注释，解释"这是什么"和"为什么这样做"，帮助初学者快速理解项目代码。
---

## 适用场景

- 小白开发者初次阅读 NexusCockpit 项目代码时，需要逐行注释帮助理解。
- 为复杂算法、异步逻辑、设计模式添加"大白话"注释。
- 将英文技术术语翻译为中文并附上通俗解释。
- 为配置文件（.env、yaml、json）的每一项添加说明。

## 非适用场景

- 不用于生成正式 API 文档（请使用 `code-doc` 技能）。
- 不用于检测代码质量（请使用 `code-review` 技能）。

## 注释规范

### 1. Python 代码注释

**函数注释 — 通俗版**:
```python
def search_memory(query: str, user_id: str, top_k: int = 3) -> list:
    """
    在记忆库里搜索和用户问题最相关的历史记忆。

    打个比方：这就像在你的笔记本里搜索和当前问题相关的页码。
    系统会把用户的问题转成向量（一串数字），然后在 Milvus 数据库里
    找出最相似的几条记忆。

    参数:
        query: 用户的问题文本，比如 "我昨天设的空调温度是多少"
        user_id: 哪个用户在问，每个用户的记忆是隔离的
        top_k: 最多返回几条记忆，默认3条

    返回:
        一个列表，里面是找到的记忆，每条记忆包含:
        - text: 记忆的内容
        - score: 相似度分数（越高越相关）
    """
```

**行内注释 — 解释式**:
```python
# === 1. 把用户的文字问题转成向量（一串2560个数字）===
# 就像把一句话翻译成机器能理解的"密码"
embedding = await self._embed_text(query)

# === 2. 在 Milvus 向量数据库里搜索相似的记忆 ===
# Milvus 会计算向量的距离，距离越近 = 内容越相关
results = self.collection.search(
    data=[embedding],          # 搜索用的向量
    anns_field="vector",       # 在哪个字段搜索
    limit=top_k,               # 最多返回几条
    filter=f'user_id == "{user_id}"',  # 只搜这个用户的记忆
)
```

### 2. TypeScript / React 代码注释

```typescript
// 这是一个 React Hook，用来管理聊天消息的状态
// "状态" 就是会随着用户操作而变化的数据
const [messages, setMessages] = useState<Message[]>([])

// 当用户点击发送按钮时执行
const handleSend = async () => {
  const text = input.trim()  // 去掉输入框文字的首尾空格
  if (!text || isStreaming) return  // 如果没内容或在等待回复，就不发送

  // 1. 先把用户的消息加到聊天列表里
  addMessage({
    id: crypto.randomUUID(),  // 生成一个唯一ID
    role: "user",             // 标记这是用户发的消息
    content: text,
    timestamp: new Date(),
  })

  // 2. 创建一个空的AI回复占位，等后端返回内容后再填充
  // 这样用户能立刻看到"AI正在思考..."的效果
  const assistantId = crypto.randomUUID()
  addMessage({
    id: assistantId,
    role: "assistant",
    content: "",
    loading: true,  // 显示加载动画
    timestamp: new Date(),
  })
}
```

### 3. 配置文件注释

```bash
# .env 配置文件注释示例

# === 大语言模型 (LLM) 配置 ===
# ARK_API_KEY 是调用火山引擎大模型的密钥
# 就像进入游乐园的门票，没有它就不能调用AI
ARK_API_KEY=your_key_here

# LLM_MODEL 指定用哪个AI模型
# DeepSeek-V3 是一个中文能力很强的模型
LLM_MODEL=deepseek-ai/DeepSeek-V3

# === 向量数据库 (Milvus) 配置 ===
# Milvus 用来存储和搜索"向量"（把文字转成的数字序列）
# 搜索时，系统会找出和用户问题最相似的历史记忆
MILVUS_HOST=127.0.0.1    # Milvus 运行在哪台机器上
MILVUS_PORT=19530        # Milvus 的通信端口
```

## 注释原则

| 原则 | 说明 | 示例 |
|------|------|------|
| **大白话** | 用生活类比解释技术概念 | "向量就像把句子翻译成机器能理解的密码" |
| **分层注释** | 先模块级概述，再函数级说明，最后行内细节 | `=== 1. xxx ===` 标记步骤 |
| **标注术语** | 英文术语首次出现时附中文翻译 | `Embedding（嵌入/向量化）` |
| **解释 Why** | 注释重点解释"为什么这样做"而非"做了什么" | "用异步是为了不阻塞主线程" |
| **适度注释** | 不是每行都注释，只注释非显而易见的逻辑 | 简单赋值不需要注释 |

## 执行步骤

1. **通读模块**：先阅读整个文件，理解模块整体职责。
2. **添加模块头注释**：在文件开头用 3-5 句话说明这个模块做什么。
3. **标注关键函数**：为每个类和公开函数添加通俗版 docstring。
4. **补充行内注释**：用 `# === N. xxx ===` 格式标注关键步骤。
5. **翻译术语**：将英文术语翻译并附上通俗解释。
6. **检查可读性**：确保一个编程新手能看懂注释后的代码。
