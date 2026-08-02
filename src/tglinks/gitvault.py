"""Keeps the vault repo in sync from the server side.

The fly machine clones the vault, appends notes and pushes. Obsidian on the
laptop pulls via the Obsidian Git plugin. No inbound access needed.
"""

import asyncio
import logging
import os
import stat
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

log = logging.getLogger(__name__)

AUTHOR = ("tg-links-bot", "bot@users.noreply.github.com")

KEY_PATH = Path(os.getenv("SSH_KEY_PATH", "/data/.ssh/id_ed25519"))


def install_ssh_key(private_key: str) -> str:
    """Write the deploy key to disk and return a GIT_SSH_COMMAND using it.

    A deploy key is scoped to a single repository, unlike a personal token.
    """
    if not private_key:
        return ""
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = private_key.replace("\\n", "\n").strip() + "\n"
    KEY_PATH.write_text(body)
    KEY_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return (
        f"ssh -i {KEY_PATH} -o IdentitiesOnly=yes"
        " -o StrictHostKeyChecking=accept-new"
        f" -o UserKnownHostsFile={KEY_PATH.parent / 'known_hosts'}"
    )


def authed_remote(repo_url: str, token: str) -> str:
    """Inject the token into an https remote so pushes need no interaction."""
    if not token or not repo_url.startswith("https://"):
        return repo_url
    parts = urlsplit(repo_url)
    return urlunsplit((parts.scheme, f"x-access-token:{token}@{parts.netloc}",
                       parts.path, parts.query, parts.fragment))


def _env() -> dict:
    env = dict(os.environ)
    ssh_cmd = env.get("GIT_SSH_COMMAND", "")
    if ssh_cmd:
        env["GIT_SSH_COMMAND"] = ssh_cmd
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return env


async def _git(root: Path, *args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(root), *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env=_env(),
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="replace").strip()


async def ensure_clone(root: Path, repo_url: str, token: str) -> bool:
    remote = authed_remote(repo_url, token)
    if (root / ".git").exists():
        code, out = await _git(root, "remote", "set-url", "origin", remote)
        if code:
            log.warning("git remote set-url failed: %s", out)
        return True

    root.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", remote, str(root),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env=_env(),
    )
    out, _ = await proc.communicate()
    if proc.returncode:
        log.error("git clone failed: %s", out.decode(errors="replace")[:400])
        return False
    return True


async def commit_push(root: Path, message: str) -> bool:
    """Commit whatever changed and push, rebasing once on rejection."""
    await _git(root, "config", "user.name", AUTHOR[0])
    await _git(root, "config", "user.email", AUTHOR[1])

    code, _ = await _git(root, "add", "-A")
    if code:
        return False

    code, out = await _git(root, "status", "--porcelain")
    if not out:
        return True

    code, out = await _git(root, "commit", "-m", message)
    if code:
        log.warning("git commit failed: %s", out[:300])
        return False

    code, out = await _git(root, "push", "origin", "HEAD")
    if code == 0:
        return True

    log.info("push rejected, rebasing: %s", out[:200])
    code, out = await _git(root, "pull", "--rebase", "--autostash", "origin", "HEAD")
    if code:
        log.error("rebase failed: %s", out[:300])
        return False
    code, out = await _git(root, "push", "origin", "HEAD")
    if code:
        log.error("push failed after rebase: %s", out[:300])
    return code == 0
