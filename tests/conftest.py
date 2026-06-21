import time

import pytest


@pytest.fixture
def clock(monkeypatch):
    """Freeze time.time() and let tests advance it explicitly."""
    state = {"t": 0.0}
    monkeypatch.setattr(time, "time", lambda: state["t"])

    def set_time(t: float) -> None:
        state["t"] = t

    return set_time
