"""Build the uploads for the apps into dist/ (step 5). Maaz uploads them by hand; nothing here deploys.

    uv run scripts/build.py mcp   # dist/mcp.zip for the MCP server's App Service (step 5b)

Each upload carries its own copy of core/ next to its app.py, so the app's `from core import ...` works the same as
from the repo root. It also carries:
- requirements.txt: exact versions, with hashes, of what core/ needs plus the app's own group in pyproject.toml,
  written by `uv export` from uv.lock. App Service installs them when the zip is deployed
  (SCM_DO_BUILD_DURING_DEPLOYMENT=1, v2's setting).
- version.txt: the git commit and the build time (UTC), shown by the app's health address. "-changed" after the commit
  means the folder had changes that were not committed.
"""

import argparse
import stat
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def version_text():
    commit = git("rev-parse", "--short", "HEAD")
    changed = "-changed" if git("status", "--porcelain") else ""
    return f"{commit}{changed} built {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"


def requirements(group):
    """Pinned versions with hashes: core/'s dependencies plus one app's group, from uv.lock."""
    return subprocess.run(
        ["uv", "export", "--frozen", "--no-default-groups", "--group", group, "--no-emit-project",
         "--format", "requirements-txt"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout


def python_files(folder):
    """Every .py file in a folder, as (path in the zip, file), without caches."""
    return [(path.relative_to(folder.parent).as_posix(), path) for path in sorted(folder.rglob("*.py"))
            if "__pycache__" not in path.parts]


def add(archive, name, content, executable=False):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    archive.writestr(info, content)


def build_mcp(dist=DIST):
    """dist/mcp.zip: app.py, startup.sh, core/, requirements.txt and version.txt at the top, as App Service expects."""
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / "mcp.zip"
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        add(archive, "app.py", (ROOT / "mcp_server" / "app.py").read_bytes())
        add(archive, "startup.sh", (ROOT / "mcp_server" / "startup.sh").read_bytes(), executable=True)
        for name, path in python_files(ROOT / "core"):
            add(archive, name, path.read_bytes())
        add(archive, "requirements.txt", requirements("mcp"))
        add(archive, "version.txt", version_text())
    return target


def main():
    parser = argparse.ArgumentParser(description="Build the uploads into dist/.")
    parser.add_argument("app", choices=["mcp"])
    args = parser.parse_args()
    target = {"mcp": build_mcp}[args.app]()
    print(f"Built {target.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
