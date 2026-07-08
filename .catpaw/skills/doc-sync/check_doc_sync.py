"""
Doc Sync Checker — 文档同步检查脚本

在代码修改完成后运行，自动检查关联的 .md 文档是否与最新代码一致。
配合 doc_mapping.yaml 映射表，定位变更代码对应的文档，执行一致性校验。

用法:
    python check_doc_sync.py                    # 检查最近一次提交的变更
    python check_doc_sync.py --staged            # 检查暂存区的变更
    python check_doc_sync.py --all               # 检查工作区所有变更
    python check_doc_sync.py --file path/to.py   # 检查指定文件关联的文档

输出:
    Markdown 格式的同步检查报告，同时输出到 stdout 和 docs/doc_sync_report.md
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    import yaml
except ImportError:
    print("PyYAML not installed. Install with: pip install pyyaml")
    sys.exit(1)

# ============================================================
# 路径常量
# ============================================================
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # .catpaw/skills/doc-sync/ -> project root
MAPPING_FILE = SCRIPT_DIR / "doc_mapping.yaml"
REPORT_FILE = PROJECT_ROOT / "docs" / "doc_sync_report.md"


# ============================================================
# 数据结构
# ============================================================
@dataclass
class DocIssue:
    """文档一致性问题"""
    severity: str  # Critical / Warning / Info
    doc_path: str
    description: str
    code_file: str = ""
    suggestion: str = ""


@dataclass
class SyncReport:
    """同步检查报告"""
    check_time: str = ""
    changed_code_files: List[str] = field(default_factory=list)
    changed_doc_files: List[str] = field(default_factory=list)
    related_docs: Set[str] = field(default_factory=set)
    issues: List[DocIssue] = field(default_factory=list)
    consistent_docs: List[str] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "Critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "Warning")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "Info")


# ============================================================
# Git 变更检测
# ============================================================
def get_changed_files(mode: str = "last_commit") -> List[str]:
    """获取变更文件列表。

    Args:
        mode: "last_commit" = 最近一次提交, "staged" = 暂存区, "all" = 工作区所有变更

    Returns:
        变更文件路径列表（相对于项目根目录）
    """
    if mode == "staged":
        cmd = ["git", "diff", "--cached", "--name-only"]
    elif mode == "all":
        cmd = ["git", "diff", "--name-only", "HEAD"]
    else:
        cmd = ["git", "diff", "--name-only", "HEAD~1", "HEAD"]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        # 可能是第一个提交，没有 HEAD~1
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except Exception:
            return []


# ============================================================
# 映射表加载
# ============================================================
def load_mapping() -> Tuple[List[dict], List[str]]:
    """加载 doc_mapping.yaml 映射表。

    Returns:
        (mappings, skip_docs) — 映射规则列表和跳过检查的文档列表
    """
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    mappings = data.get("mappings", [])
    skip_docs = data.get("skip_docs", [])
    return mappings, skip_docs


def find_related_docs(changed_file: str, mappings: List[dict]) -> Set[str]:
    """根据映射表查找变更文件关联的文档。

    Args:
        changed_file: 变更文件路径（相对于项目根目录）
        mappings: 映射规则列表

    Returns:
        关联文档路径集合
    """
    related = set()

    for mapping in mappings:
        # 精确路径匹配
        code_path = mapping.get("code_path", "")
        if code_path and changed_file == code_path:
            related.update(mapping.get("docs", []))
            continue

        # 前缀匹配
        code_prefix = mapping.get("code_prefix", "")
        if code_prefix and changed_file.startswith(code_prefix):
            related.update(mapping.get("docs", []))

    return related


# ============================================================
# 文档一致性检查
# ============================================================
def check_file_existence(doc_path: str, code_files: List[str], project_root: Path) -> List[DocIssue]:
    """检查文档中引用的文件路径是否仍然存在。"""
    issues = []
    full_path = project_root / doc_path

    if not full_path.exists():
        issues.append(DocIssue(
            severity="Critical",
            doc_path=doc_path,
            description=f"文档本身不存在: {doc_path}",
            suggestion="检查文档路径是否正确，或创建该文档",
        ))
        return issues

    # 读取文档内容，提取代码文件引用
    content = full_path.read_text(encoding="utf-8")

    # 匹配 `path/to/file.py` 格式的代码引用
    code_refs = re.findall(r'`((?:backend_design/|frontend_design/|config/|models/|data/|assets/)[^\s`]+)`', content)

    for ref in code_refs:
        ref_path = project_root / ref
        if not ref_path.exists():
            issues.append(DocIssue(
                severity="Warning",
                doc_path=doc_path,
                description=f"文档引用的文件不存在: `{ref}`",
                suggestion=f"检查 {ref} 是否已被删除或重命名，更新文档引用",
            ))

    return issues


def check_new_files_registered(doc_path: str, code_files: List[str], project_root: Path) -> List[DocIssue]:
    """检查新增的源码文件是否在文档中登记。

    支持两种登记粒度（与 check_progress_modules 一致）：
    - 文件级: `backend_design/nexus/config.py`
    - 目录级: `backend_design/nexus/agent/`
    """
    issues = []

    full_path = project_root / doc_path
    if not full_path.exists():
        return issues

    content = full_path.read_text(encoding="utf-8")

    # 预提取文档中所有目录级注册
    dir_registrations = set(re.findall(r'`(backend_design/nexus/[^`]+/)', content))

    # 找出新增的 .py 文件
    new_py_files = [f for f in code_files if f.endswith(".py")]

    for py_file in new_py_files:
        # 提取文件名（不含路径）
        filename = os.path.basename(py_file)

        # 检查文件名是否出现
        if filename in content or py_file in content:
            continue

        # 检查父目录是否已注册（目录级登记覆盖子文件）
        registered = False
        for reg_dir in dir_registrations:
            if py_file.startswith(reg_dir):
                registered = True
                break
        if registered:
            continue

        # 检查是否在 PROGRESS.md 或 architecture README 中
        if doc_path in ("docs/PROGRESS.md", "docs/architecture/README.md"):
            issues.append(DocIssue(
                severity="Warning",
                doc_path=doc_path,
                description=f"新增文件未在文档中登记: {py_file}",
                code_file=py_file,
                suggestion=f"在 {doc_path} 中补充 {filename} 的登记信息",
            ))

    return issues


def check_api_routes(doc_path: str, project_root: Path) -> List[DocIssue]:
    """检查 API 路由文档是否与代码一致（仅对 L6-api.md）。"""
    issues = []

    if "L6-api" not in doc_path and "L6-api.md" not in doc_path:
        return issues

    full_path = project_root / doc_path
    if not full_path.exists():
        return issues

    doc_content = full_path.read_text(encoding="utf-8")

    # 扫描 api/routes/ 目录下的所有路由
    api_dir = project_root / "backend_design" / "nexus" / "api" / "routes"
    if not api_dir.exists():
        return issues

    code_routes: Dict[str, List[str]] = {}  # {router_prefix: [methods+paths]}

    for py_file in api_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        file_content = py_file.read_text(encoding="utf-8")

        # 提取 router 前缀
        prefix_match = re.search(r'APIRouter\(prefix="([^"]*)"', file_content)
        prefix = prefix_match.group(1) if prefix_match else ""

        # 提取路由装饰器
        route_matches = re.findall(
            r'@(router|app)\.(get|post|put|delete|patch|websocket)\("([^"]*)"', file_content
        )

        for _, method, path in route_matches:
            full_route = f"{prefix}{path}" if prefix else path
            code_routes.setdefault(method.upper(), []).append(full_route)

    # 检查文档中是否有路由清单表格
    # 提取文档表格中的路由行
    doc_routes = re.findall(r'\|\s*`(/[^`]*)`\s*\|\s*(GET|POST|PUT|DELETE|PATCH|WS)\s*\|', doc_content, re.IGNORECASE)

    doc_route_set = {(route, method.upper()) for route, method in doc_routes}

    # 检查代码中有但文档中没有的路由
    for method, routes in code_routes.items():
        for route in routes:
            found = False
            for doc_route, doc_method in doc_route_set:
                if route == doc_route or route.rstrip("/") == doc_route.rstrip("/"):
                    found = True
                    break
            if not found:
                issues.append(DocIssue(
                    severity="Warning",
                    doc_path=doc_path,
                    description=f"API 路由未在文档中登记: {method} {route}",
                    suggestion=f"在路由清单表格中补充 `{route}` | {method} | 说明",
                ))

    return issues


def check_progress_modules(doc_path: str, project_root: Path) -> List[DocIssue]:
    """检查 PROGRESS.md 中的模块清单是否包含所有代码文件（仅对 PROGRESS.md）。

    PROGRESS.md 支持两种登记粒度：
    - 文件级: `backend_design/nexus/config.py` — 精确到文件
    - 目录级: `backend_design/nexus/agent/` — 覆盖目录下所有文件
    检查时优先匹配目录级注册，减少误报。
    """
    issues = []

    if "PROGRESS.md" not in doc_path:
        return issues

    full_path = project_root / doc_path
    if not full_path.exists():
        return issues

    content = full_path.read_text(encoding="utf-8")

    # 扫描 backend_design/nexus/ 下的所有 .py 文件（排除 __init__.py）
    nexus_dir = project_root / "backend_design" / "nexus"

    # 预提取 PROGRESS.md 中所有 `backend_design/nexus/xxx/` 格式的目录级注册
    dir_registrations = set(re.findall(r'`(backend_design/nexus/[^`]+/)', content))

    for py_file in nexus_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        rel_path = py_file.relative_to(project_root).as_posix()
        filename = py_file.name
        parent_dir = "/".join(rel_path.split("/")[:-1]) + "/"

        # 检查文件名是否出现
        if filename in content or rel_path in content:
            continue

        # 检查父目录是否已注册（目录级登记覆盖子文件）
        registered = False
        for reg_dir in dir_registrations:
            if rel_path.startswith(reg_dir):
                registered = True
                break
        if registered:
            continue

        # 只有当父目录也未被注册时才报告
        issues.append(DocIssue(
            severity="Warning",
            doc_path=doc_path,
            description=f"后端模块未在进度表中登记: {rel_path}",
            suggestion=f"在 PROGRESS.md 后端模块完成详情表中补充 {filename} 或其目录 {parent_dir}",
        ))

    return issues


def check_skills_registry(doc_path: str, project_root: Path) -> List[DocIssue]:
    """检查 architecture/README.md 中的 Skills 清单是否完整。"""
    issues = []

    if "architecture/README.md" not in doc_path:
        return issues

    full_path = project_root / doc_path
    if not full_path.exists():
        return issues

    content = full_path.read_text(encoding="utf-8")

    # 扫描 .catpaw/skills/ 目录
    skills_dir = project_root / ".catpaw" / "skills"
    if not skills_dir.exists():
        return issues

    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            skill_name = skill_dir.name
            if skill_name not in content:
                issues.append(DocIssue(
                    severity="Warning",
                    doc_path=doc_path,
                    description=f"Skill 未在文档清单中登记: {skill_name}",
                    suggestion=f"在 architecture/README.md 的 Skills 清单表格中补充 {skill_name}",
                ))

    return issues


# ============================================================
# 主检查流程
# ============================================================
def run_check(changed_files: List[str]) -> SyncReport:
    """执行完整的文档同步检查。

    Args:
        changed_files: 变更文件列表

    Returns:
        SyncReport 检查报告
    """
    report = SyncReport(
        check_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # 分类变更文件
    code_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}
    for f in changed_files:
        ext = os.path.splitext(f)[1]
        if ext == ".md":
            report.changed_doc_files.append(f)
        elif ext in code_extensions or ext in {".yaml", ".yml", ".toml", ".json"}:
            report.changed_code_files.append(f)

    if not report.changed_code_files:
        # 没有代码变更，无需检查
        report.consistent_docs.append("无代码变更，无需文档同步检查")
        return report

    # 加载映射表
    mappings, skip_docs = load_mapping()

    # 查找关联文档
    for code_file in report.changed_code_files:
        related = find_related_docs(code_file, mappings)
        report.related_docs.update(related)

    # 过滤掉跳过的文档
    report.related_docs = {d for d in report.related_docs if d not in skip_docs}

    if not report.related_docs:
        report.consistent_docs.append("变更代码无关联文档（可能需要创建文档）")
        return report

    # 逐文档检查
    for doc_path in sorted(report.related_docs):
        doc_issues: List[DocIssue] = []

        # 通用检查: 文件引用存在性
        doc_issues.extend(check_file_existence(doc_path, report.changed_code_files, PROJECT_ROOT))

        # 通用检查: 新增文件登记
        doc_issues.extend(check_new_files_registered(doc_path, report.changed_code_files, PROJECT_ROOT))

        # 专项检查: API 路由
        doc_issues.extend(check_api_routes(doc_path, PROJECT_ROOT))

        # 专项检查: PROGRESS.md 模块清单
        doc_issues.extend(check_progress_modules(doc_path, PROJECT_ROOT))

        # 专项检查: Skills 清单
        doc_issues.extend(check_skills_registry(doc_path, PROJECT_ROOT))

        if doc_issues:
            report.issues.extend(doc_issues)
        else:
            report.consistent_docs.append(doc_path)

    return report


# ============================================================
# 报告生成
# ============================================================
def generate_report(report: SyncReport) -> str:
    """生成 Markdown 格式的检查报告。"""
    lines = []
    lines.append("# 文档同步检查报告\n")
    lines.append(f"> 检查时间: {report.check_time}\n")

    # 概要
    lines.append("## 检查概要\n")
    lines.append(f"- **变更源码文件数**: {len(report.changed_code_files)}")
    lines.append(f"- **变更文档文件数**: {len(report.changed_doc_files)}")
    lines.append(f"- **关联文档数**: {len(report.related_docs)}")
    lines.append(f"- **一致文档数**: {len(report.consistent_docs)}")
    lines.append(f"- **需更新文档数**: {len(set(i.doc_path for i in report.issues))}")
    lines.append(f"- **Critical**: {report.critical_count}  |  **Warning**: {report.warning_count}  |  **Info**: {report.info_count}")
    lines.append("")

    # 变更文件清单
    if report.changed_code_files:
        lines.append("## 变更源码文件\n")
        lines.append("| 文件路径 |")
        lines.append("|----------|")
        for f in report.changed_code_files:
            lines.append(f"| `{f}` |")
        lines.append("")

    # 需更新文档
    if report.issues:
        lines.append("## 需更新文档清单\n")

        # Critical
        critical_issues = [i for i in report.issues if i.severity == "Critical"]
        if critical_issues:
            lines.append("### 🔴 Critical（文档与代码严重不一致）\n")
            lines.append("| 文档路径 | 问题描述 | 涉及代码 | 建议操作 |")
            lines.append("|----------|----------|----------|----------|")
            for issue in critical_issues:
                lines.append(f"| {issue.doc_path} | {issue.description} | {issue.code_file} | {issue.suggestion} |")
            lines.append("")

        # Warning
        warning_issues = [i for i in report.issues if i.severity == "Warning"]
        if warning_issues:
            lines.append("### 🟡 Warning（文档缺失或索引过期）\n")
            lines.append("| 文档路径 | 问题描述 | 建议操作 |")
            lines.append("|----------|----------|----------|")
            for issue in warning_issues:
                lines.append(f"| {issue.doc_path} | {issue.description} | {issue.suggestion} |")
            lines.append("")

        # Info
        info_issues = [i for i in report.issues if i.severity == "Info"]
        if info_issues:
            lines.append("### 🟢 Info（建议优化）\n")
            lines.append("| 文档路径 | 问题描述 | 建议操作 |")
            lines.append("|----------|----------|----------|")
            for issue in info_issues:
                lines.append(f"| {issue.doc_path} | {issue.description} | {issue.suggestion} |")
            lines.append("")

    # 一致文档
    if report.consistent_docs:
        lines.append("## 已检查且一致的文档\n")
        for doc in report.consistent_docs:
            lines.append(f"- ✅ {doc}")
        lines.append("")

    # 摘要
    lines.append("## 文档同步完成摘要\n")
    updated_docs = set(i.doc_path for i in report.issues)
    lines.append(f"- 需更新文档: {len(updated_docs)} 个")
    lines.append(f"- 一致文档: {len(report.consistent_docs)} 个")
    if updated_docs:
        lines.append("- 更新详情:")
        for doc in sorted(updated_docs):
            lines.append(f"  - ✏️ {doc}")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 主入口
# ============================================================
def main():
    # Windows PowerShell 默认 GBK 编码，强制 UTF-8 输出
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="NexusCockpit 文档同步检查工具")
    parser.add_argument("--staged", action="store_true", help="检查暂存区变更")
    parser.add_argument("--all", action="store_true", help="检查工作区所有变更")
    parser.add_argument("--file", type=str, help="检查指定文件关联的文档")
    args = parser.parse_args()

    # 获取变更文件
    if args.file:
        changed_files = [args.file]
    elif args.staged:
        changed_files = get_changed_files("staged")
    elif args.all:
        changed_files = get_changed_files("all")
    else:
        changed_files = get_changed_files("last_commit")

    if not changed_files:
        print("ℹ️ 没有检测到代码变更，无需文档同步检查。")
        return

    print(f"📋 检测到 {len(changed_files)} 个变更文件，开始文档同步检查...\n")

    # 执行检查
    report = run_check(changed_files)

    # 生成报告
    md_report = generate_report(report)

    # 输出到 stdout
    print(md_report)

    # 保存到文件
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(md_report, encoding="utf-8")
    print(f"\n📄 报告已保存到: {REPORT_FILE}")

    # 退出码: 有 Critical 则返回 1
    if report.critical_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
