"""The two ways a request is refused. Every problem names its rule ID (docs/rules.md).

The web app, MCP server and Bridge turn these into their own answers (for example HTTP 404 and 403).
"""


class Refused(Exception):
    """The request is not done. `rule_id` is the rule that stopped it, for example "ACCESS-002"."""

    def __init__(self, rule_id, message):
        super().__init__(f"{rule_id}: {message}")
        self.rule_id = rule_id
        self.message = message


class NotFound(Refused):
    """Refused as "not found", so someone without access cannot tell the thing exists (ACCESS-001)."""
