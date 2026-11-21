"""GDS Workbench core: all the logic, shared by the web app, the MCP server and the Bridge.

Rules for this folder:
- It never imports from web_app/ or mcp_server/. It does not know who is calling it.
- It never reads settings or secrets. The caller opens the database connection and passes it in.
"""
