import asyncio
import time
from src.algorithms.memory import FixedWindowState, SlidingWindowState
from src.rate_limiter.request import Rules
from src.rate_limiter.response import Response, get_response
from .base import Algorithm


class SlidingWindow(Algorithm):
    pass


class SlidingWindowInMemory(SlidingWindow):
    def __init__(self, rules: Rules):
        self.__rules = rules
        self.__request_count: dict[str, SlidingWindowState] = {}
        self.__lock = asyncio.Lock()

    def _generate_new_window_state(
        self, request_count: int, window_start_timestamp: float
    ) -> FixedWindowState:
        return FixedWindowState(
            request_count=request_count, window_start_timestamp=window_start_timestamp
        )

    def _generate_new_state(
        self, current_window: FixedWindowState, previous_window: FixedWindowState
    ) -> SlidingWindowState:
        return SlidingWindowState(
            current_window=current_window, previous_window=previous_window
        )

    async def execute(self, client_id: str) -> Response:
        """Execute the sliding window algorithm logic."""
        try:
            async with self.__lock:
                current_time = time.time()

                # Initialize or check if window has expired
                if client_id not in self.__request_count:
                    self.__request_count[client_id] = self._generate_new_state(
                        current_window=self._generate_new_window_state(
                            request_count=0, window_start_timestamp=current_time
                        ),
                        previous_window=self._generate_new_window_state(
                            request_count=0,
                            window_start_timestamp=current_time
                            - self.__rules.time_window,
                        ),
                    )
                else:
                    time_elapsed = (
                        current_time
                        - self.__request_count[client_id]["current_window"][
                            "window_start_timestamp"
                        ]
                    )
                    # Reset window if it has expired
                    if time_elapsed > self.__rules.time_window:
                        self.__request_count[client_id] = self._generate_new_state(
                            current_window=self._generate_new_window_state(
                                request_count=0, window_start_timestamp=current_time
                            ),
                            previous_window=self.__request_count[client_id][
                                "current_window"
                            ],
                        )

                current_window = self.__request_count[client_id]["current_window"]
                previous_window = self.__request_count[client_id]["previous_window"]

                time_elapsed = current_time - current_window["window_start_timestamp"]

                # Calculate weight of requests from the previous window that still count
                # Weight represents the fraction of the time window still overlapping with the previous window
                previous_window_weight = max(
                    0,
                    (self.__rules.time_window - time_elapsed)
                    / self.__rules.time_window,
                )

                # Calculate total requests considering both current and weighted previous window
                total_requests = (
                    current_window["request_count"]
                    + previous_window["request_count"] * previous_window_weight
                )

                # Check if request is allowed
                if total_requests < self.__rules.max_requests:
                    # Increment the current window count
                    self.__request_count[client_id]["current_window"][
                        "request_count"
                    ] += 1
                    # Calculate remaining requests after accepting this one
                    remaining_requests = max(
                        0, int(self.__rules.max_requests - total_requests - 1)
                    )
                    return get_response(
                        allowed=True,
                        remaining_requests=remaining_requests,
                        reset_time=0,
                    )
                time_until_reset = (total_requests - self.__rules.max_requests) * (
                    self.__rules.time_window / self.__rules.max_requests
                )
                return get_response(
                    allowed=False,
                    remaining_requests=0,
                    reset_time=time_until_reset,
                )
        except Exception as e:
            print(f"Error executing sliding window for client {client_id}: {e}")
            return get_response(allowed=False, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        try:
            async with self.__lock:
                self.__request_count.pop(client_id, None)
                return True
        except Exception as e:
            print(f"Error resetting client {client_id}: {e}")
            return False


class SlidingWindowInRedis(SlidingWindow):
    def __init__(self, rules: Rules):
        self.__rules = rules
        self.__request_count: dict[str, SlidingWindowState] = {}
        self.__lock = asyncio.Lock()

    async def execute(self, client_id: str) -> Response:
        # TODO(Phase 2): implement via Redis sorted set (ZREMRANGEBYSCORE + ZADD + ZCARD)
        return get_response(allowed=True, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        return True
