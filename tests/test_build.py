"""Tests for scripts/build.py (step 5b): the MCP upload works on its own, away from the repo.

The zip is unpacked in an empty folder and started there in a separate Python, the way App Service runs it from its
own folder, so a missing file or an import from outside the zip shows up here and not on Azure.
"""

import importlib.util
import json
import os
import stat
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("build", os.path.join(ROOT, "scripts", "build.py"))
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

START_FROM_ITS_OWN_FOLDER = """
import json, os, sys
os.environ.update(GDS_ENVIRONMENT="local", GDS_MCP_PUBLIC_URL="http://127.0.0.1:8001/mcp")
import app, core
from starlette.testclient import TestClient
with TestClient(app.create_app(), base_url="http://127.0.0.1:8001") as client:
    live = client.get("/health/live").json()
print(json.dumps({"live": live, "core": os.path.dirname(core.__file__)}))
"""


def test_mcp_zip_runs_from_its_own_folder_with_its_own_core(tmp_path):
    target = build.build_mcp(tmp_path / "dist")
    folder = tmp_path / "site"
    with zipfile.ZipFile(target) as archive:
        archive.extractall(folder)
        startup_mode = archive.getinfo("startup.sh").external_attr >> 16

    started = subprocess.run([sys.executable, "-c", START_FROM_ITS_OWN_FOLDER], cwd=folder, capture_output=True,
                             text=True, env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})

    assert started.returncode == 0, started.stderr
    answer = json.loads(started.stdout.strip().splitlines()[-1])
    assert answer["core"] == str((folder / "core").resolve())  # the zip's copy, not the repo's
    assert answer["live"]["status"] == "live"
    assert answer["live"]["version"] == (folder / "version.txt").read_text().strip()
    assert startup_mode & stat.S_IXUSR


def test_mcp_requirements_have_what_the_mcp_server_needs_and_not_the_web_app(tmp_path):
    with zipfile.ZipFile(build.build_mcp(tmp_path)) as archive:
        lines = archive.read("requirements.txt").decode().splitlines()
    names = {line.split("==")[0].split("[")[0] for line in lines if "==" in line and not line.startswith(" ")}
    hashes = sum(line.count("--hash=sha256:") for line in lines)

    assert {"mcp", "psycopg", "gunicorn", "uvicorn-worker"} <= names
    assert "fastapi" not in names
    assert hashes >= len(names)  # every package pinned by its hash, so App Service installs exactly these files


START_WEB_FROM_ITS_OWN_FOLDER = """
import json, os, re
# The settings app.yaml gives the App (only plain values; the DSN comes from a Databricks resource).
for name, value in re.findall(r"- name: (\\w+)\\n\\s+value: (\\S+)", open("app.yaml").read()):
    os.environ[name] = value
import app, core
from fastapi.testclient import TestClient
client = TestClient(app.app)
print(json.dumps({"health": client.get("/health").json(), "page": client.get("/").text,
                  "core": os.path.dirname(core.__file__)}))
"""


def test_web_folder_runs_from_its_own_folder_and_serves_the_built_page(tmp_path):
    folder = build.build_web(tmp_path)

    started = subprocess.run([sys.executable, "-c", START_WEB_FROM_ITS_OWN_FOLDER], cwd=folder, capture_output=True,
                             text=True, env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})

    assert started.returncode == 0, started.stderr
    answer = json.loads(started.stdout.strip().splitlines()[-1])
    assert answer["core"] == str((folder / "core").resolve())
    assert answer["health"]["version"] == (folder / "version.txt").read_text().strip()
    assert answer["health"]["environment"] == "production"
    assert "<title>GDS Workbench</title>" in answer["page"]
    assert "X-Forwarded-Email" not in "".join(p.read_text() for p in (folder / "static").rglob("*.js"))


def test_web_requirements_have_what_the_web_app_needs_and_not_the_mcp_server(tmp_path):
    lines = (build.build_web(tmp_path) / "requirements.txt").read_text().splitlines()
    names = {line.split("==")[0].split("[")[0] for line in lines if "==" in line and not line.startswith(" ")}

    assert {"fastapi", "uvicorn", "psycopg"} <= names
    assert not {"mcp", "gunicorn"} & names
