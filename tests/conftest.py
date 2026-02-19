import os
import random
import time


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
