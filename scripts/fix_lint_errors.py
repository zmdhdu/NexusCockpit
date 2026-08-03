"""Fix all ruff lint errors in one script."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def fix_supervisor_node():
    p = ROOT / "backend_design" / "nexus" / "agent" / "nodes" / "supervisor_node.py"
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

    # Find the block starting at "if _is_fast_vehicle and _has_non_vehicle_intent:"
    # and ending before "# 处理记忆结果"
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if "if _is_fast_vehicle and _has_non_vehicle_intent:" in line:
            start_idx = i
        if start_idx is not None and "# 处理记忆结果" in line:
            end_idx = i
            break

    assert start_idx is not None, "Could not find start of supervisor_node block"
    assert end_idx is not None, "Could not find end of supervisor_node block"

    new_block = (
        "            _skip_keys = (\n"
        "                'Route_Source', 'Route_Confidence',\n"
        "                'Need_Clarification', 'Clarification_Prompt',\n"
        "            )\n"
        "            _active_keys = [\n"
        "                k for k in intent\n"
        "                if intent[k] and k not in _skip_keys\n"
        "            ]\n"
        "            if _is_fast_vehicle and _has_non_vehicle_intent:\n"
        "                logger.info(\n"
        '                    f"Mixed-intent: vehicle + non-vehicle, "\n'
        '                    f"memory recall done. "\n'
        '                    f"intent_keys={_active_keys} "\n'
        '                    f"memories={len(memories)}"\n'
        "                )\n"
        "            if _is_compound:\n"
        "                logger.info(\n"
        '                    f"Compound query routed: "\n'
        "                    f\"source={intent.get('Route_Source', 'unknown')}, \"\n"
        '                    f"intent_keys={_active_keys}"\n'
        "                )\n"
    )

    lines[start_idx:end_idx] = [new_block]
    p.write_text("".join(lines), encoding="utf-8")
    print("  supervisor_node.py: OK")


def fix_reviewer_node():
    p = ROOT / "backend_design" / "nexus" / "agent" / "nodes" / "reviewer_node.py"
    t = p.read_text(encoding="utf-8")
    # Find the long line by searching for a unique prefix
    prefix = '        reflection_passed = "passed" in reflection_result or reflection_result in ('
    idx = t.find(prefix)
    assert idx != -1, "reviewer_node.py: long line not found"
    # Find the end of this line (next newline)
    end = t.find("\n", idx)
    old_line = t[idx:end]

    new_lines = (
        "        _skip_reflection_results = (\n"
        '            "", "chat_fast_skipped", "chat_timeout",\n'
        '            "search_timeout", "tool_fast_skipped", "tool_timeout",\n'
        "        )\n"
        "        reflection_passed = (\n"
        '            "passed" in reflection_result\n'
        "            or reflection_result in _skip_reflection_results\n"
        "        )"
    )

    t = t[:idx] + new_lines + t[end:]
    p.write_text(t, encoding="utf-8")
    print("  reviewer_node.py: OK")


def fix_responder_node():
    p = ROOT / "backend_design" / "nexus" / "agent" / "nodes" / "responder_node.py"
    t = p.read_text(encoding="utf-8")
    count = t.count("_FAST_SYNTHESIS_MAX_LEN")
    t = t.replace("_FAST_SYNTHESIS_MAX_LEN", "_fast_synthesis_max_len")
    p.write_text(t, encoding="utf-8")
    print(f"  responder_node.py: OK ({count} replacements)")


def fix_reflection_node():
    p = ROOT / "backend_design" / "nexus" / "agent" / "nodes" / "reflection_node.py"
    t = p.read_text(encoding="utf-8")

    # N806: rename _TOOL_FAST_SKIP_MAX_LEN -> _tool_fast_skip_max_len
    count = t.count("_TOOL_FAST_SKIP_MAX_LEN")
    t = t.replace("_TOOL_FAST_SKIP_MAX_LEN", "_tool_fast_skip_max_len")

    # E501: L258 long docstring - find and replace
    # The docstring contains: 车控指令回复轻量反思 — 确定性校验，无 LLM 调用。作用：...
    marker = "车控指令回复轻量反思"
    idx = t.find(marker)
    assert idx != -1, "reflection_node.py: docstring marker not found"

    # Find the triple-quote start before this marker
    dq_start = t.rfind('"""', 0, idx)
    # Find the triple-quote end after this marker
    dq_end = t.find('"""', idx + len(marker))
    assert dq_start != -1 and dq_end != -1, "reflection_node.py: could not find docstring bounds"

    old_docstring = t[dq_start:dq_end + 3]
    new_docstring = (
        '        """车控指令回复轻量反思 — 确定性校验，无 LLM 调用。\n\n'
        "        作用：校验车控回复非空/无幻觉/失败提及；\n"
        "        场景：B3分支车控指令回复的快速校验。\n"
        '        """'
    )

    t = t[:dq_start] + new_docstring + t[dq_end + 3:]
    p.write_text(t, encoding="utf-8")
    print(f"  reflection_node.py: OK ({count} N806 replacements + docstring fix)")


def fix_vehicle_expert():
    p = ROOT / "backend_design" / "nexus" / "agent" / "experts" / "vehicle_expert.py"
    t = p.read_text(encoding="utf-8")

    # F541: remove f prefix from f-string without placeholders
    old_fstr = 'message=f"车控指令执行超时，设备可能离线，请稍后重试。",'
    new_fstr = 'message="车控指令执行超时，设备可能离线，请稍后重试。",'
    assert old_fstr in t, "vehicle_expert.py: F541 line not found"
    t = t.replace(old_fstr, new_fstr)

    # F841: remove unused `args = r["args"]` line
    lines = t.splitlines(keepends=True)
    new_lines = []
    skip_next_args = False
    for i, line in enumerate(lines):
        # Match the pattern: line with 'args = r["args"]' inside a for loop
        stripped = line.strip()
        if stripped == 'args = r["args"]':
            # Check previous line has tool_name and next line has result
            prev_stripped = lines[i - 1].strip() if i > 0 else ""
            next_stripped = lines[i + 1].strip() if i < len(lines) - 1 else ""
            if 'tool_name = r["tool_name"]' in prev_stripped and 'result: SkillResult = r["result"]' in next_stripped:
                continue  # skip this line
        new_lines.append(line)

    t = "".join(new_lines)
    p.write_text(t, encoding="utf-8")
    print("  vehicle_expert.py: OK")


if __name__ == "__main__":
    print("Fixing ruff lint errors...")
    fix_supervisor_node()
    fix_reviewer_node()
    fix_responder_node()
    fix_reflection_node()
    fix_vehicle_expert()
    print("All fixes applied.")
