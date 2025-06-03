# ──────────────────────────────────────────────────────────────────────────────
# versioning.py  (you could put this at the top of main.py or in its own file)
# ──────────────────────────────────────────────────────────────────────────────

import subprocess
import shlex

# Only bump these when you deliberately want to release a new major/minor:
MAJOR = 0
MINOR = 1

# Fallback “build” if not in a Git repo (e.g. when you zip up or PyInstaller‐bundle).
# In that scenario, commit‐count detection will fail and we’ll use this.
__version__ = f"{MAJOR}.{MINOR}.0"


def get_local_version() -> str:
    """
    Try to get the current Git‐based build number via:
        git rev-list --count HEAD
    This returns an integer count of commits on HEAD. We build a version string:
        "<MAJOR>.<MINOR>.<commit_count>"
    If anything fails (no Git, or not in a repo), we fall back to __version__.
    """
    try:
        # This returns something like "57\n" if there have been 57 commits.
        p = subprocess.run(
            shlex.split("git rev-list --count HEAD"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True
        )
        build = p.stdout.strip()
        # Construct "MAJOR.MINOR.build"
        return f"{MAJOR}.{MINOR}.{build}"
    except Exception:
        # Either git isn’t installed or this isn’t a Git checkout.
        return __version__
