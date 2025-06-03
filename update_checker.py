# ──────────────────────────────────────────────────────────────────────────────
# update_checker.py  (fold this into main.py or import it)
# ──────────────────────────────────────────────────────────────────────────────

import requests
import webbrowser
from tkinter import messagebox

# Fill in your GitHub “owner/repo” here:
GITHUB_REPO = "YourUsername/YourRepo"


def check_for_updates(local_version: str, repo: str) -> None:
    """
    1. Hits GitHub’s API: /repos/{repo}/releases/latest  
    2. Reads the "tag_name" of the latest release (e.g. "v1.2.60" or "1.2.60").  
    3. Strips any leading "v" and compares semver (major, minor, patch) tuples.  
    4. If GitHub’s version > local_version, prompts user to open the Releases page.
    """
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        resp = requests.get(api_url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "").lstrip("v")
    except Exception:
        return  # silently do nothing on network or JSON errors

    def to_tuple(v: str):
        parts = [int(x) for x in v.split(".") if x.isdigit()]
        return tuple(parts)

    try:
        if to_tuple(tag) > to_tuple(local_version):
            answer = messagebox.askyesno(
                "Update Available",
                f"A newer release ({tag}) is available on GitHub.\n"
                f"You’re currently on {local_version}.\n\n"
                "Would you like to open the Releases page?"
            )
            if answer:
                webbrowser.open(
                    data.get("html_url", f"https://github.com/{repo}/releases/latest")
                )
    except Exception:
        pass
