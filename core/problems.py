"""The two ways a request is refused, and a problem found in a draft.

Every problem names its rule ID (docs/rules.md).

The web app, MCP server and Bridge turn these into their own answers (for example HTTP 404 and 403).
"""

from dataclasses import dataclass


class Refused(Exception):
    """The request is not done. `rule_id` is the rule that stopped it, for example "ACCESS-002"."""

    def __init__(self, rule_id, message):
        super().__init__(f"{rule_id}: {message}")
        self.rule_id = rule_id
        self.message = message


class NotFound(Refused):
    """Refused as "not found", so someone without access cannot tell the thing exists (ACCESS-001)."""


@dataclass(frozen=True)
class Problem:
    """Something in a draft that breaks a rule. The draft is kept; the problem is shown before Apply.

    `record` is the position (from 0) of the record it is about in its part, or None for the whole draft or a row
    the draft did not touch. `part` is that part. `level` is `blocks_apply` or `warning` (docs/rules.md).
    """

    rule_id: str
    message: str
    record: int | None = None
    part: str | None = None
    level: str = "blocks_apply"

    def __str__(self):
        return f"{self.rule_id}: {self.message}"
