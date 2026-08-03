# -*- coding: utf-8 -*-
"""Fix remaining ruff lint errors found in full CI check (idempotent)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "backend_design"


def _try_replace(t, old, new, label):
    """Replace old with new in t. Skip if old not found (already fixed)."""
    if old not in t:
        print(f"  {label}: already fixed, skip")
        return t
    return t.replace(old, new)


def fix_settings():
    p = B / "nexus" / "api" / "routes" / "settings.py"
    t = p.read_text(encoding="utf-8")
    old = '    """\u58f0\u7eb9\u9a8c\u8bc1\uff1a\u4f5c\u7528\uff1a\u58f0\u7eb9\u6bd4\u5bf9\u2192\u9a8c\u8bc1\u6210\u529f\u81ea\u52a8\u7b7e\u53d1JWT Token\uff1b\u573a\u666f\uff1a\u7528\u6237\u58f0\u7eb9\u767b\u5f55\uff0c\u524d\u7aef\u76f4\u63a5\u4f7f\u7528Token\u65e0\u9700\u518d\u8c03\u7528/auth/token\u3002"""'
    new = (
        '    """\u58f0\u7eb9\u9a8c\u8bc1\uff1a\u58f0\u7eb9\u6bd4\u5bf9\u2192\u9a8c\u8bc1\u6210\u529f\u81ea\u52a8\u7b7e\u53d1JWT Token\u3002\n\n'
        "    \u573a\u666f\uff1a\u7528\u6237\u58f0\u7eb9\u767b\u5f55\uff0c\u524d\u7aef\u76f4\u63a5\u4f7f\u7528Token\u65e0\u9700\u518d\u8c03\u7528/auth/token\u3002\n"
        '    """'
    )
    t = _try_replace(t, old, new, "settings.py")
    p.write_text(t, encoding="utf-8")
    print("  settings.py: OK")


def fix_heuristic():
    p = B / "nexus" / "intent" / "heuristic.py"
    t = p.read_text(encoding="utf-8")

    old147 = (
        '        if "\u6e29\u5ea6" in text and not any(k in text for k in '
        '("\u7a7a\u8c03", "\u8f66\u5185", "\u8f66\u91cc", "\u8c03\u9ad8", '
        '"\u8c03\u4f4e", "\u8bbe\u7f6e", "\u8bbe\u4e3a", "\u5f00\u5230", "\u8c03\u5230")):'
    )
    new147 = (
        '        _temp_context_keys = (\n'
        '            "\u7a7a\u8c03", "\u8f66\u5185", "\u8f66\u91cc", "\u8c03\u9ad8", "\u8c03\u4f4e",\n'
        '            "\u8bbe\u7f6e", "\u8bbe\u4e3a", "\u5f00\u5230", "\u8c03\u5230",\n'
        '        )\n'
        '        if "\u6e29\u5ea6" in text and not any(k in text for k in _temp_context_keys):'
    )
    t = _try_replace(t, old147, new147, "heuristic.py L147")

    old466 = (
        '        if not any(k in text for k in '
        '("\u97f3\u4e50", "\u64ad\u653e", "\u6682\u505c", "\u505c\u6b62", '
        '"\u4e0b\u4e00\u9996", "\u4e0a\u4e00\u9996", "\u97f3\u91cf", '
        '"\u5207\u6b4c", "\u542c\u6b4c", "\u6b4c\u66f2", "\u6b4c")):'
    )
    new466 = (
        '        _media_keys = (\n'
        '            "\u97f3\u4e50", "\u64ad\u653e", "\u6682\u505c", "\u505c\u6b62", "\u4e0b\u4e00\u9996",\n'
        '            "\u4e0a\u4e00\u9996", "\u97f3\u91cf", "\u5207\u6b4c", "\u542c\u6b4c", "\u6b4c\u66f2", "\u6b4c",\n'
        '        )\n'
        '        if not any(k in text for k in _media_keys):'
    )
    t = _try_replace(t, old466, new466, "heuristic.py L466")

    old471 = (
        '        media_segments = [s for s in segments if any(k in s for k in '
        '("\u97f3\u4e50", "\u64ad\u653e", "\u6682\u505c", "\u505c\u6b62", '
        '"\u4e0b\u4e00\u9996", "\u4e0a\u4e00\u9996", "\u97f3\u91cf", '
        '"\u5207\u6b4c", "\u542c\u6b4c", "\u6b4c\u66f2", "\u6b4c"))]'
    )
    new471 = (
        '        media_segments = [\n'
        '            s for s in segments\n'
        '            if any(k in s for k in _media_keys)\n'
        '        ]'
    )
    t = _try_replace(t, old471, new471, "heuristic.py L471")

    old667 = (
        '        if any(k in text for k in media_keywords) and "\u63a8\u8350" in text '
        'and not any(k in text for k in '
        '("\u7f8e\u98df", "\u9910\u5385", "\u9152\u65c5", "\u65c5\u6e38", "\u666f\u70b9")):'
    )
    new667 = (
        '        _food_keys = ("\u7f8e\u98df", "\u9910\u5385", "\u9152\u65c5", "\u65c5\u6e38", "\u666f\u70b9")\n'
        '        if (\n'
        '            any(k in text for k in media_keywords)\n'
        '            and "\u63a8\u8350" in text\n'
        '            and not any(k in text for k in _food_keys)\n'
        '        ):'
    )
    t = _try_replace(t, old667, new667, "heuristic.py L667")

    p.write_text(t, encoding="utf-8")
    print("  heuristic.py: OK")


def fix_llm_router():
    p = B / "nexus" / "intent" / "llm_router.py"
    t = p.read_text(encoding="utf-8")

    old_method = (
        "    def _parse_multi_json(self, content: str) -> list[dict[str, Any]] | None:\n"
        '        """\u89e3\u6790 LLM \u591a\u610f\u56fe\u8f93\u51fa\u4e3a\u51b3\u7b56\u5b57\u5178\u5217\u8868\u3002"""\n'
        "        decision = parse_multi_intent_decision(content)"
    )
    new_method = (
        "    def _parse_multi_json(self, content: str) -> list[dict[str, Any]] | None:\n"
        '        """\u89e3\u6790 LLM \u591a\u610f\u56fe\u8f93\u51fa\u4e3a\u51b3\u7b56\u5b57\u5178\u5217\u8868\u3002"""\n'
        "        from nexus.intent.schema import parse_multi_intent_decision\n\n"
        "        decision = parse_multi_intent_decision(content)"
    )
    t = _try_replace(t, old_method, new_method, "llm_router.py F821")

    old_import = "from nexus.intent.schema import parse_intent_decision, parse_multi_intent_decision"
    new_import = "from nexus.intent.schema import parse_intent_decision"
    t = _try_replace(t, old_import, new_import, "llm_router.py F401")

    p.write_text(t, encoding="utf-8")
    print("  llm_router.py: OK")


def fix_climate_state():
    p = B / "nexus" / "vehicle" / "mock" / "climate_state.py"
    t = p.read_text(encoding="utf-8")

    old102 = (
        "                message=f\"\u7a7a\u8c03\u72b6\u6001\uff1a\u6e29\u5ea6 {self.climate['temperature']} \u5ea6\uff0c"
        "\u98ce\u91cf {self.climate['fan_speed']} \u6863\uff0c"
        "\u6a21\u5f0f {self.climate['mode']}\u3002\","
    )
    new102 = (
        "                message=(\n"
        "                    f\"\u7a7a\u8c03\u72b6\u6001\uff1a\u6e29\u5ea6 {self.climate['temperature']} \u5ea6\uff0c\"\n"
        "                    f\"\u98ce\u91cf {self.climate['fan_speed']} \u6863\uff0c\"\n"
        "                    f\"\u6a21\u5f0f {self.climate['mode']}\u3002\"\n"
        "                ),"
    )
    t = _try_replace(t, old102, new102, "climate_state.py L102")

    old118 = (
        '                mode_names = {"auto": "\u81ea\u52a8", "cool": "\u5236\u51b7", '
        '"heat": "\u5236\u70ed", "defog": "\u9664\u96fe", '
        '"vent": "\u901a\u98ce", "defrost": "\u9664\u971c"}'
    )
    new118 = (
        '                mode_names = {\n'
        '                    "auto": "\u81ea\u52a8", "cool": "\u5236\u51b7",\n'
        '                    "heat": "\u5236\u70ed", "defog": "\u9664\u96fe",\n'
        '                    "vent": "\u901a\u98ce", "defrost": "\u9664\u971c",\n'
        '                }'
    )
    t = _try_replace(t, old118, new118, "climate_state.py L118")

    old123 = (
        "            parts.append(f\"\u7a7a\u8c03\u5df2\u5f00\u542f\uff0c\u5f53\u524d\u6e29\u5ea6 {self.climate['temperature']} \u5ea6\uff0c"
        "\u98ce\u91cf {self.climate['fan_speed']} \u6863\u3002\")"
    )
    new123 = (
        "            parts.append(\n"
        "                f\"\u7a7a\u8c03\u5df2\u5f00\u542f\uff0c\u5f53\u524d\u6e29\u5ea6 {self.climate['temperature']} \u5ea6\uff0c\"\n"
        "                f\"\u98ce\u91cf {self.climate['fan_speed']} \u6863\u3002\"\n"
        "            )"
    )
    t = _try_replace(t, old123, new123, "climate_state.py L123")

    p.write_text(t, encoding="utf-8")
    print("  climate_state.py: OK")


def fix_test_agent():
    p = B / "tests" / "test_agent.py"
    t = p.read_text(encoding="utf-8")

    old_imports = (
        "import hashlib\n"
        "import pytest\n"
        "from unittest.mock import AsyncMock, MagicMock, patch\n"
    )
    new_imports = (
        "import hashlib\n"
        "\n"
        "import pytest\n"
    )
    t = _try_replace(t, old_imports, new_imports, "test_agent.py imports")

    old182 = "        assert isinstance(side_effect_skills := side_effects, list)"
    new182 = "        assert isinstance(side_effects, list)"
    t = _try_replace(t, old182, new182, "test_agent.py L182")

    old_imports2 = (
        "        from nexus.skills.registry import SkillRegistry\n"
        "        from nexus.skills.base import SkillGroup"
    )
    new_imports2 = (
        "        from nexus.skills.base import SkillGroup\n"
        "        from nexus.skills.registry import SkillRegistry"
    )
    t = _try_replace(t, old_imports2, new_imports2, "test_agent.py L207")

    p.write_text(t, encoding="utf-8")
    print("  test_agent.py: OK")


if __name__ == "__main__":
    print("Fixing remaining ruff lint errors...")
    fix_settings()
    fix_heuristic()
    fix_llm_router()
    fix_climate_state()
    fix_test_agent()
    print("All remaining fixes applied.")
