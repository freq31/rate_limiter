import asyncio
import logging
import time

from redis.asyncio import Redis

from rate_limiter.algorithms.memory import FixedWindowState
from rate_limiter.backend.request import Rules
from rate_limiter.backend.response import Response, get_response
from rate_limiter.scripts.fixed_window import _FIXED_WINDOW_LUA
from .base import Algorithm


class FixedWindow(Algorithm):
    pass


class FixedWindowInMemory(FixedWindow):
    def __init__(self, rules: Rules):
        self.__rules = rules
        self.__request_count: dict[str, FixedWindowState] = {}
        self.__lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)

    def _generate_new_state(self, current_time: float) -> FixedWindowState:
        return FixedWindowState(request_count=0, window_start_timestamp=current_time)

    async def execute(self, client_id: str) -> Response:
        """Execute the fixed window algorithm logic."""
        try:
            async with self.__lock:
                current_time = time.time()
                self.logger.info(
                    f"Start -> Executing Fixed Window In Memory Rate Limiter for client {client_id}"
                )

                # Initialize or check if window has expired
                if client_id not in self.__request_count:
                    self.logger.info(
                        f"Client {client_id} not found. Initializing new state"
                    )
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
                        self.logger.info(
                            f"Window expired for client {client_id}. Resetting state"
                        )
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
                    remaining_requests = (
                        self.__rules.max_requests
                        - self.__request_count[client_id]["request_count"]
                    )

                    self.logger.info(f"End -> Request allowed for client {client_id}.")
                    return get_response(
                        allowed=True,
                        remaining_requests=remaining_requests,
                        reset_time=time_until_reset,
                    )
                self.logger.info(
                    f"End -> Request denied for client {client_id}. Max requests reached"
                )
                return get_response(
                    allowed=False, remaining_requests=0, reset_time=time_until_reset
                )
        except Exception as e:
            self.logger.error(
                f"Error -> executing fixed window for client {client_id}, error:  {e}"
            )
            return get_response(allowed=False, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        try:
            async with self.__lock:
                self.logger.info(f"Resetting request count for client {client_id}")
                self.__request_count.pop(client_id, None)
                return True
        except Exception as e:
            self.logger.error(f"Error -> resetting client {client_id}, error: {e}")
            return False


class FixedWindowInRedis(FixedWindow):
    def __init__(self, rules: Rules, redis_client: Redis):
        self.__rules = rules
        self.__redis = redis_client
        self.__script = self.__redis.register_script(_FIXED_WINDOW_LUA)
        self.logger = logging.getLogger(__name__)

    def _key(self, client_id: str) -> str:
        return f"rl:fixed_window:{client_id}"

    async def execute(self, client_id: str) -> Response:
        """Execute the fixed window algorithm logic, atomically, in Redis."""
        try:
            self.logger.info(
                f"Start -> Executing Fixed Window In Redis Rate Limiter for client {client_id}"
            )
            current, ttl = await self.__script(
                keys=[self._key(client_id)],
                args=[self.__rules.time_window],
            )
            # ttl is -1 only if the key somehow has no expiry set; fall back
            # to the full window so callers still get a sane reset_time.
            reset_time = ttl if ttl >= 0 else self.__rules.time_window

            if current <= self.__rules.max_requests:
                remaining_requests = self.__rules.max_requests - int(current)
                self.logger.info(f"End -> Request allowed for client {client_id}")
                return get_response(
                    allowed=True,
                    remaining_requests=remaining_requests,
                    reset_time=reset_time,
                )
            self.logger.info(
                f"End -> Request denied for client {client_id}. Max requests reached"
            )
            return get_response(
                allowed=False, remaining_requests=0, reset_time=reset_time
            )
        except Exception as e:
            self.logger.error(
                f"Error -> executing fixed window (redis) for client {client_id}, error: {e}"
            )
            return get_response(allowed=False, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        try:
            self.logger.info(f"Resetting request count for client {client_id}")
            await self.__redis.delete(self._key(client_id))
            return True
        except Exception as e:
            self.logger.error(f"Error -> resetting client {client_id}, error: {e}")
            return False
