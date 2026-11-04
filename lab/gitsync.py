"""Git helpers for Colab. The GitHub token is NEVER written to .git/config and never printed:
it is put in the push URL only for the duration of the command, and scrubbed from any output."""
import shutil
import subprocess
from pathlib import Path

from .paths import ensure_dirs

GIT_NAME = "deriv-lab"
GIT_EMAIL = "deriv-lab@users.noreply.github.com"


def scrub(text, token):
    return text.replace(token, "***") if token else text


def remote_url(repo, token=None):
    """'user/repo' -> authenticated https URL. A local path (used by tests) is returned unchanged."""
    if repo.startswith(("/", "file://", ".")):
        return repo
    if token:
        return f"https://x-access-token:{token}@github.com/{repo}.git"
    return f"https://github.com/{repo}.git"


def git(args, cwd, token=None, check=True):
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    out = scrub((p.stdout or "") + (p.stderr or ""), token).strip()
    if check and p.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {out}")
    return p.returncode, out


def init_repo(repo_dir, branch="main"):
    repo_dir = Path(repo_dir)
    if not (repo_dir / ".git").exists():
        git(["init", "-b", branch], repo_dir)
    git(["config", "user.name", GIT_NAME], repo_dir)
    git(["config", "user.email", GIT_EMAIL], repo_dir)


def has_commits(repo_dir):
    code, _ = git(["rev-parse", "--verify", "HEAD"], repo_dir, check=False)
    return code == 0


def commit_all(repo_dir, message):
    git(["add", "-A"], repo_dir)
    code, _ = git(["diff", "--cached", "--quiet"], repo_dir, check=False)
    if code == 0:
        return False  # nothing to commit
    git(["commit", "-m", message], repo_dir)
    return True


def push(repo_dir, repo, token, message="update", branch="main"):
    """Commit everything and push. Returns 'pushed' or 'nothing to push'."""
    init_repo(repo_dir, branch)
    changed = commit_all(repo_dir, message)
    if not has_commits(repo_dir):
        return "nothing to push"
    git(["push", remote_url(repo, token), f"HEAD:{branch}"], repo_dir, token)
    return "pushed" if changed else "pushed (no new changes, remote brought up to date)"


def pull(repo_dir, repo, token, branch="main"):
    git(["pull", "--ff-only", remote_url(repo, token), branch], repo_dir, token)


def clone(repo, token, dest, branch="main"):
    dest = Path(dest)
    git(["clone", "--branch", branch, remote_url(repo, token), str(dest)], dest.parent, token)
    # git stores the clone URL as 'origin': replace it with the token-free URL so nothing secret stays on disk
    git(["remote", "set-url", "origin", remote_url(repo, None)], dest)
    init_repo(dest, branch)
    return dest


def remote_reachable(repo, token):
    code, out = git(["ls-remote", remote_url(repo, token), "HEAD"], Path.cwd(), token, check=False)
    return code == 0, out


def sync_journal(repo_dir, repo, token, root=None, message="journal sync"):
    """Copy the authoritative Drive journal into the repo, render JOURNAL.md, commit and push."""
    from .journal import Journal
    repo_dir = Path(repo_dir)
    j = Journal(root)
    dest = repo_dir / "journal"
    dest.mkdir(parents=True, exist_ok=True)
    if j.path.exists():
        shutil.copy2(j.path, dest / "journal.jsonl")
    (dest / "JOURNAL.md").write_text(j.render_markdown(), encoding="utf-8")
    return push(repo_dir, repo, token, message)
