#!/usr/bin/env python3
# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
API 接口文档导出脚本 — 将 FastAPI OpenAPI schema 导出为静态文件

使用方式:
    cd backend_design
    python -m scripts.export_openapi

输出:
    - docs/api/openapi.json   — OpenAPI 3.1 JSON schema
    - docs/api/openapi.yaml   — OpenAPI 3.1 YAML schema
    - docs/api/API_REFERENCE.md — 可读的 Markdown 文档

说明:
    FastAPI /docs 已有交互式文档，此脚本导出静态版本用于:
    1. 离线查阅
    2. CI/CD 中生成文档制品
    3. 接口审计
"""

import json
import os
import sys

# 确保能导入 nexus 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nexus.main import create_app


def export_openapi():
    """导出 OpenAPI schema 和 Markdown 文档。"""
    app = create_app()
    schema = app.openapi()

    # 输出目录
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs", "api",
    )
    os.makedirs(output_dir, exist_ok=True)

    # 1. 导出 JSON
    json_path = os.path.join(output_dir, "openapi.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"[OK] OpenAPI JSON → {json_path}")

    # 2. 导出 YAML (如果安装了 PyYAML)
    try:
        import yaml
        yaml_path = os.path.join(output_dir, "openapi.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(schema, f, allow_unicode=True, default_flow_style=False)
        print(f"[OK] OpenAPI YAML → {yaml_path}")
    except ImportError:
        print("[SKIP] PyYAML not installed, skipping YAML export")

    # 3. 导出 Markdown 文档
    md_path = os.path.join(output_dir, "API_REFERENCE.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# NexusCockpit API 参考文档\n\n")
        f.write(f"> 版本: {schema.get('info', {}).get('version', 'unknown')}\n")
        f.write(f"> 生成时间: 自动导出\n\n")
        f.write("---\n\n")

        f.write("## 目录\n\n")
        for path, methods in sorted(schema.get("paths", {}).items()):
            for method in methods:
                if method in ("get", "post", "put", "delete", "patch"):
                    summary = methods[method].get("summary", "")
                    f.write(f"- [{method.upper()} {path}]({method}-{path.replace('/', '-').strip('-')}) — {summary}\n")

        f.write("\n---\n\n")

        for path, methods in sorted(schema.get("paths", {}).items()):
            for method, detail in methods.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                f.write(f"## {method.upper()} {path}\n\n")
                f.write(f"**摘要**: {detail.get('summary', 'N/A')}\n\n")
                if detail.get("description"):
                    f.write(f"**描述**: {detail['description']}\n\n")
                if detail.get("tags"):
                    f.write(f"**标签**: {', '.join(detail['tags'])}\n\n")

                # 请求体
                rb = detail.get("requestBody", {})
                if rb:
                    f.write("### 请求体\n\n")
                    content = rb.get("content", {})
                    for ct, ct_detail in content.items():
                        f.write(f"Content-Type: `{ct}`\n\n")
                        schema_ref = ct_detail.get("schema", {}).get("$ref", "")
                        if schema_ref:
                            f.write(f"Schema: `{schema_ref.split('/')[-1]}`\n\n")

                # 响应
                f.write("### 响应\n\n")
                for code, resp in sorted(detail.get("responses", {}).items()):
                    f.write(f"- **{code}**: {resp.get('description', '')}\n")

                f.write("\n---\n\n")

    print(f"[OK] API Markdown → {md_path}")
    print(f"\n导出完成! 文件位于 docs/api/")


if __name__ == "__main__":
    export_openapi()
