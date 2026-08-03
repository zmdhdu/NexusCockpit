# Copyright (c) 2026 zhangmengdi (NexusCockpit)
# Licensed under the MIT License. See LICENSE in the project root for details.
# Source: https://github.com/zmdhdu/NexusCockpit

"""
Prompt Manager — Prompt 模板管理 (LangChain ChatPromptTemplate 接入)

功能:
  1. 模板外置：所有 prompt 从 nexus/prompts/ 目录加载 .md 文件
  2. 动态变量注入：通过 LangChain ChatPromptTemplate 实现变量注入
  3. Few-shot 示例：每个模板可附带 examples 段落
  4. 版本管理：模板文件头部带 version 注释

LangChain 接入:
  - 使用 langchain_core.prompts.ChatPromptTemplate.from_template() 创建模板
  - .format(**variables) 渲染变量，替代手动 string.replace()
  - 模板文件中的 {variable} 占位符自动被 ChatPromptTemplate 识别

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

from langchain_core.prompts import ChatPromptTemplate

from nexus.core.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


class PromptManager:
    """Prompt 模板管理器 (LangChain ChatPromptTemplate 接入)。

    从 nexus/prompts/ 目录加载 .md 模板文件，
    使用 LangChain ChatPromptTemplate 实现变量注入。

    Usage:
        pm = PromptManager()
        prompt = pm.render("chat", user_profile="张三", memory="喜欢24度")
    """

    def __init__(self, prompts_dir: str = ""):
        self.prompts_dir = prompts_dir or _PROMPTS_DIR
        # 缓存 ChatPromptTemplate 实例
        self._template_cache: dict[str, ChatPromptTemplate] = {}
        # 缓存原始文件内容 (用于 get_version 等元信息提取)
        self._raw_cache: dict[str, str] = {}

    def _load_raw(self, name: str) -> str:
        """加载模板文件原始内容（带缓存）。

        Args:
            name: 模板名（不含扩展名）

        Returns:
            模板文本
        """
        if name in self._raw_cache:
            return self._raw_cache[name]

        filepath = os.path.join(self.prompts_dir, f"{name}.md")
        if not os.path.exists(filepath):
            logger.warning(f"Prompt template not found: {filepath}")
            return ""

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            self._raw_cache[name] = content
            return content
        except Exception as e:
            logger.error(f"Failed to load prompt template '{name}': {e}")
            return ""

    def load(self, name: str) -> ChatPromptTemplate | None:
        """加载模板并创建 ChatPromptTemplate 实例（带缓存）。

        Args:
            name: 模板名（不含扩展名）

        Returns:
            ChatPromptTemplate 实例，如果文件不存在则返回 None
        """
        if name in self._template_cache:
            return self._template_cache[name]

        content = self._load_raw(name)
        if not content:
            return None

        try:
            template = ChatPromptTemplate.from_template(content)
            self._template_cache[name] = template
            return template
        except Exception as e:
            logger.error(f"Failed to create ChatPromptTemplate for '{name}': {e}")
            # 降级：返回 None，render() 会返回空字符串
            return None

    def render(self, name: str, **variables: Any) -> str:
        """加载模板并通过 ChatPromptTemplate 注入变量。

        使用 LangChain ChatPromptTemplate.format() 方法渲染变量，
        替代原有的手动 string.replace() 方式。

        Args:
            name: 模板名
            **variables: 要注入的变量（替换 {var} 占位符）

        Returns:
            渲染后的 prompt 文本
        """
        template = self.load(name)
        if template is None:
            return ""

        try:
            # ChatPromptTemplate.format() 返回渲染后的字符串
            result = template.format(**variables)
            return result.strip()
        except Exception as e:
            logger.error(f"Failed to render prompt template '{name}': {e}")
            # 降级：尝试手动替换
            raw = self._load_raw(name)
            if not raw:
                return ""
            result = raw
            for key, value in variables.items():
                placeholder = "{" + key + "}"
                result = result.replace(placeholder, str(value) if value is not None else "")
            return result.strip()

    def get_version(self, name: str) -> str:
        """获取模板版本号。"""
        content = self._load_raw(name)
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
