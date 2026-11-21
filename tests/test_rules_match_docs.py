"""Every rule check in core/ must be an Approved rule in docs/rules/.

A check is a function named after its rule ID, for example `access_001` for ACCESS-001. This test finds them all
and fails if one has no Approved rule, so no check can be added quietly (docs/rules.md, "How this works").
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RULE_FUNCTION = re.compile(r"^def ((?:[a-z]+_)+\d{3})\(", re.MULTILINE)
RULE_HEADING = re.compile(r"^### ([A-Z-]+-\d{3}) · .*\n\*(.+)\*", re.MULTILINE)


def approved_rules():
    rules = {}
    for path in (ROOT / "docs" / "rules").glob("*.md"):
        for rule_id, level_and_status in RULE_HEADING.findall(path.read_text()):
            rules[rule_id] = "Approved" in level_and_status
    return rules


def rule_functions():
    found = {}
    for path in (ROOT / "core").rglob("*.py"):
        for name in RULE_FUNCTION.findall(path.read_text()):
            found[name.upper().replace("_", "-")] = path.relative_to(ROOT)
    return found


def test_core_has_rule_checks():
    assert rule_functions(), "no rule checks found in core/"


def test_every_rule_check_in_core_is_approved():
    rules = approved_rules()
    not_approved = {rule_id: str(path) for rule_id, path in rule_functions().items() if not rules.get(rule_id)}
    assert not not_approved, f"checks in core/ without an Approved rule in docs/rules/: {not_approved}"
