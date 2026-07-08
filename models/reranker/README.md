# Reranker Model

## BAAI/bge-reranker-v2-m3

### 下载地址
- HuggingFace: https://huggingface.co/BAAI/bge-reranker-v2-m3
- ModelScope（国内镜像）: https://modelscope.cn/models/BAAI/bge-reranker-v2-m3

### 下载方式

```bash
# 方式1: huggingface-cli（需翻墙）
pip install huggingface_hub
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir ./models/reranker/bge-reranker-v2-m3

# 方式2: modelscope（国内推荐，无需翻墙）
pip install modelscope
modelscope download --model BAAI/bge-reranker-v2-m3 --local_dir ./models/reranker/bge-reranker-v2-m3

# 方式3: git lfs（HuggingFace，需翻墙）
git lfs install
git clone https://huggingface.co/BAAI/bge-reranker-v2-m3 ./models/reranker/bge-reranker-v2-m3

# 方式4: git lfs（ModelScope 国内镜像，推荐！无需翻墙，无需 modelscope 包）
git lfs install
git clone https://www.modelscope.cn/BAAI/bge-reranker-v2-m3.git ./models/reranker/bge-reranker-v2-m3
```

### 存放路径
`./models/reranker/bge-reranker-v2-m3/`

### 模型信息
- 大小: 约 2.2GB（model.safetensors）
- 框架: sentence-transformers / transformers
- 用途: RAG 检索结果重排序（Top20 → Top5）
- 推理: CPU 可用（约200ms/20条），GPU 更快
- 多语言: 支持中文、英文等 100+ 语言
