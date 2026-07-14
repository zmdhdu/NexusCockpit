#!/usr/bin/env python3
"""
批量添加 MIT 版权头脚本 — 为所有 Python/Go/TypeScript 源码文件添加版权声明。

用法: python scripts/add_copyright.py
"""
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

COPYRIGHT_LINE = "Copyright (c) 2026 zhangmengdi (NexusCockpit)"
LICENSE_LINE = "Licensed under the MIT License. See LICENSE in the project root for details."
SOURCE_LINE = "Source: https://github.com/zmdhdu/NexusCockpit"

# 各语言版权头格式
HEADERS = {
    ".py": f"# {COPYRIGHT_LINE}\n# {LICENSE_LINE}\n# {SOURCE_LINE}\n",
    ".go": f"// {COPYRIGHT_LINE}\n// {LICENSE_LINE}\n// {SOURCE_LINE}\n",
    ".ts": f"/**\n * {COPYRIGHT_LINE}\n * {LICENSE_LINE}\n * {SOURCE_LINE}\n */\n",
    ".tsx": f"/**\n * {COPYRIGHT_LINE}\n * {LICENSE_LINE}\n * {SOURCE_LINE}\n */\n",
}

# 需要扫描的目录
SCAN_DIRS = [
    PROJECT_ROOT / "backend_design" / "nexus",
    PROJECT_ROOT / "backend_design" / "nexus_gate",
    PROJECT_ROOT / "frontend_design" / "src",
]

# 需要跳过的目录
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".next", "vendor", "dist", "build"}

# 版权标记（用于检测是否已有版权头）
COPYRIGHT_MARKERS = ["Copyright (c) 2026", "Licensed under the MIT License"]


def has_copyright(content: str) -> bool:
    """检查文件内容是否已包含版权头。"""
    return all(marker in content[:500] for marker in COPYRIGHT_MARKERS)


def add_header_to_file(filepath: Path, ext: str) -> bool:
    """为单个文件添加版权头。返回是否进行了修改。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  SKIP (read error): {filepath} — {e}")
        return False

    if has_copyright(content):
        return False

    header = HEADERS[ext]

    if ext == ".py":
        # Python: 保留 shebang 和编码声明
        lines = content.split("\n")
        prepend_lines = []
        idx = 0
        while idx < len(lines) and (
            lines[idx].startswith("#!") or
            lines[idx].startswith("# -*- coding") or
            lines[idx].startswith("# coding")
        ):
            prepend_lines.append(lines[idx])
            idx += 1

        if prepend_lines:
            # shebang/encoding 之后加空行再加版权头
            remaining = "\n".join(lines[idx:])
            new_content = "\n".join(prepend_lines) + "\n" + header + "\n" + remaining
        else:
            new_content = header + "\n" + content

    elif ext == ".go":
        # Go: 版权头放在 package 声明之前
        # 如果文件以 // 开头（已有注释），在注释之前插入版权头
        new_content = header + "\n" + content

    elif ext in (".ts", ".tsx"):
        # TypeScript: 版权头放在文件最前面
        # 如果文件以 /** 开头（已有 JSDoc），在之前插入
        new_content = header + "\n" + content

    else:
        return False

    # 确保不以过多空行开头
    new_content = re.sub(r"\n{4,}", "\n\n\n", new_content)

    try:
        filepath.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"  SKIP (write error): {filepath} — {e}")
        return False


def main():
    stats = {ext: {"total": 0, "modified": 0, "skipped": 0} for ext in HEADERS}

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            print(f"Directory not found: {scan_dir}")
            continue

        for root, dirs, files in os.walk(scan_dir):
            # 跳过不需要的目录
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in files:
                ext = Path(fname).suffix
                if ext not in HEADERS:
                    continue

                filepath = Path(root) / fname
                stats[ext]["total"] += 1

                modified = add_header_to_file(filepath, ext)
                if modified:
                    stats[ext]["modified"] += 1
                    print(f"  + Added: {filepath.relative_to(PROJECT_ROOT)}")
                else:
                    stats[ext]["skipped"] += 1

    print("\n========== Summary ==========")
    total_files = 0
    total_modified = 0
    for ext, s in stats.items():
        print(f"  {ext:5s}: {s['modified']:3d} added / {s['skipped']:3d} skipped / {s['total']:3d} total")
        total_files += s["total"]
        total_modified += s["modified"]
    print(f"  {'ALL':5s}: {total_modified:3d} added / {total_files - total_modified:3d} skipped / {total_files:3d} total")


if __name__ == "__main__":
    main()
