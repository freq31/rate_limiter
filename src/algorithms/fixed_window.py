import asyncio
import time

from redis.asyncio import Redis

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


# KEYS[1] = the per-client rate limit key, e.g. "rl:fixed_window:user-123"
# ARGV[1] = time_window in seconds
#
# INCR and EXPIRE must happen as a single atomic unit. If they were two
# separate round trips, two concurrent requests could both INCR before either
# sets a TTL, or a crash between the calls could leave a key that never
# expires. Redis runs a Lua script to completion on a single thread with no
# other command interleaved, so this whole block behaves as one atomic
# operation - no distributed lock needed across app processes.
_FIXED_WINDOW_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class FixedWindowInRedis(FixedWindow):
    def __init__(self, rules: Rules, redis_client: Redis):
        self.__rules = rules
        self.__redis = redis_client
        self.__script = self.__redis.register_script(_FIXED_WINDOW_LUA)

    def _key(self, client_id: str) -> str:
        return f"rl:fixed_window:{client_id}"

    async def execute(self, client_id: str) -> Response:
        """Execute the fixed window algorithm logic, atomically, in Redis."""
        try:
            current, ttl = await self.__script(
                keys=[self._key(client_id)],
                args=[int(self.__rules.time_window)],
            )
            # ttl is -1 only if the key somehow has no expiry set; fall back
            # to the full window so callers still get a sane reset_time.
            reset_time = ttl if ttl >= 0 else self.__rules.time_window

            if current <= self.__rules.max_requests:
                remaining_requests = int(self.__rules.max_requests - current)
                return get_response(
                    allowed=True,
                    remaining_requests=remaining_requests,
                    reset_time=reset_time,
                )
            return get_response(
                allowed=False, remaining_requests=0, reset_time=reset_time
            )
        except Exception as e:
            print(f"Error executing fixed window (redis) for client {client_id}: {e}")
            return get_response(allowed=False, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        try:
            await self.__redis.delete(self._key(client_id))
            return True
        except Exception as e:
            print(f"Error resetting client {client_id}: {e}")
            return False
