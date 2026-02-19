import os
import random
import sys
import time
from pathlib import Path


def pytest_configure(config) -> None:
    """Ensure repository root is importable during test collection."""
    repo_root = Path(__file__).resolve().parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def pytest_sessionstart(session) -> None:
    """Enforce deterministic defaults for test runs."""
    random.seed(0)
    os.environ.setdefault("PYTHONHASHSEED", "0")
    os.environ.setdefault("TZ", "UTC")
    try:
        time.tzset()
    except AttributeError:
        # tzset is not available on all platforms.
        pass
