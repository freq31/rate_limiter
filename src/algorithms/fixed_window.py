import asyncio
import time
from src.algorithms.memory import FixedWindowState
from src.rate_limiter.request import Rules
from src.rate_limiter.response import Response, get_response
from .base import Algorithm


class FixedWindow(Algorithm):
    pass


class FixedWindowInMemory(FixedWindow):
    def __init__(self, rules: Rules):
        self.__rules = rules
        self.__request_count: dict[str, FixedWindowState] = {}
        self.__lock = asyncio.Lock()

    def _generate_new_state(self, current_time: float) -> FixedWindowState:
        return FixedWindowState(request_count=0, window_start_timestamp=current_time)

    async def execute(self, client_id: str) -> Response:
        """Execute the fixed window algorithm logic."""
        try:
            async with self.__lock:
                current_time = time.time()

                # Initialize or check if window has expired
                if client_id not in self.__request_count:
                    self.__request_count[client_id] = self._generate_new_state(
                        current_time
                    )
                else:
                    time_elapsed = (
                        current_time
                        - self.__request_count[client_id]["window_start_timestamp"]
                    )
                    # Reset window if it has expired
                    if time_elapsed > self.__rules.time_window:
                        self.__request_count[client_id] = self._generate_new_state(
                            current_time
                        )

                time_until_reset = max(
                    0,
                    self.__rules.time_window
                    - (
                        current_time
                        - self.__request_count[client_id]["window_start_timestamp"]
                    ),
                )

                # Check if request is allowed
                if (
                    self.__request_count[client_id]["request_count"]
                    < self.__rules.max_requests
                ):
                    self.__request_count[client_id]["request_count"] += 1
                    remaining_requests = int(
                        self.__rules.max_requests
                        - self.__request_count[client_id]["request_count"]
                    )
                    return get_response(
                        allowed=True,
                        remaining_requests=remaining_requests,
                        reset_time=time_until_reset,
                    )
                return get_response(
                    allowed=False, remaining_requests=0, reset_time=time_until_reset
                )
        except Exception as e:
            print(f"Error executing fixed window for client {client_id}: {e}")
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


class FixedWindowInRedis(FixedWindow):
    def __init__(self, rules: Rules):
        self.__rules = rules
        self.__request_count: dict[str, FixedWindowState] = {}
        self.__lock = asyncio.Lock()

    async def execute(self, client_id: str) -> Response:
        # TODO(Phase 2): implement via atomic Redis Lua script (INCR + EXPIRE)
        return get_response(allowed=True, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        return True
