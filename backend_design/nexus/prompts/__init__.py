# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Prompt Manager — Prompt 模板管理

功能:
  1. 模板外置：所有 prompt 从 nexus/prompts/ 目录加载 .md 文件
  2. 动态变量注入：支持 {user_profile} {memory} {slots} 运行时填充
  3. Few-shot 示例：每个模板可附带 examples 段落
  4. 版本管理：模板文件头部带 version 注释

模板目录: nexus/prompts/
模板文件:
  - chat.md          闲聊系统提示
  - vehicle.md       车控路由提示
  - search.md        搜索结果组织提示
  - memory_extract.md 记忆提取提示
  - clarification.md  澄清提问提示
"""

from __future__ import annotations

import os
from typing import Any

from nexus.core.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


class PromptManager:
    """Prompt 模板管理器。

    从 nexus/prompts/ 目录加载 .md 模板文件，支持动态变量注入。

    Usage:
        pm = PromptManager()
        prompt = pm.render("chat", user_profile="张三", memory="喜欢24度")
    """

    def __init__(self, prompts_dir: str = ""):
        self.prompts_dir = prompts_dir or _PROMPTS_DIR
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        """加载模板文件内容。

        Args:
            name: 模板名（不含扩展名）

        Returns:
            模板文本
        """
        if name in self._cache:
            return self._cache[name]

        filepath = os.path.join(self.prompts_dir, f"{name}.md")
        if not os.path.exists(filepath):
            logger.warning(f"Prompt template not found: {filepath}")
            return ""

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            self._cache[name] = content
            return content
        except Exception as e:
            logger.error(f"Failed to load prompt template '{name}': {e}")
            return ""

    def render(self, name: str, **variables: Any) -> str:
        """加载模板并注入变量。

        Args:
            name: 模板名
            **variables: 要注入的变量（替换 {var} 占位符）

        Returns:
            渲染后的 prompt 文本
        """
        template = self.load(name)
        if not template:
            return ""

        # 简单的变量替换（不使用 str.format 以避免大括号冲突）
        result = template
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(value) if value is not None else "")

        return result.strip()

    def get_version(self, name: str) -> str:
        """获取模板版本号。"""
        content = self.load(name)
        for line in content.split("\n"):
            if line.strip().startswith("<!-- version:"):
                return line.strip().replace("<!-- version:", "").replace("-->", "").strip()
        return "unknown"

    def list_templates(self) -> list[str]:
        """列出所有可用模板。"""
        if not os.path.exists(self.prompts_dir):
            return []
        return [
            f.replace(".md", "")
            for f in os.listdir(self.prompts_dir)
            if f.endswith(".md")
        ]
