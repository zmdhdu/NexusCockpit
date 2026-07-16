---
kind: external_dependency
name: MinIO — S3 兼容对象存储
slug: minio
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

### 供应商身份
MinIO 高性能 S3 兼容对象存储服务，提供分布式文件存储能力。

### 在本项目中的角色
- **本地开发对象存储**：为阿里云 OSS 提供 S3 兼容的本地替代方案
- **模型文件存储**：存储 ASR/TTS/SV 等大型 AI 模型文件
- **用户上传文件**：声纹注册音频、聊天附件等用户生成内容

### 集成方式
- 控制台访问：http://localhost:9001
- API 访问：http://localhost:9000
- 默认账号：minioadmin/minioadmin
- 数据持久化到 `minio_data` 卷

### 约束条件
- 仅用于本地开发和测试环境
- 生产环境建议使用阿里云 OSS 或 AWS S3 等云服务