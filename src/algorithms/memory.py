from typing import TypedDict


class TokenBucketState(TypedDict):
    tokens: int
    last_refill_timestamp: float


class FixedWindowState(TypedDict):
    request_count: int
    window_start_timestamp: float


class SlidingWindowState(TypedDict):
    current_window: FixedWindowState
    previous_window: FixedWindowState
