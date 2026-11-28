"""Small helpers the tests share: scope drafts through the change set engine (core/change_sets.py)."""

from core.change_sets import apply, make_draft, validate


def make_scope_draft(conn, principal_id, project_id, records, title, via_mcp=False):
    return make_draft(conn, principal_id, project_id, {"project_input_scope": records}, title, via_mcp=via_mcp)


def apply_scope_draft(conn, principal_id, change_set_id, via_mcp=False):
    return apply(conn, principal_id, change_set_id, via_mcp=via_mcp)


def check_scope_draft(conn, principal_id, change_set_id, via_mcp=False):
    return validate(conn, principal_id, change_set_id, via_mcp=via_mcp)
