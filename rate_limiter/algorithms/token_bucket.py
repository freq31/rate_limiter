import asyncio
import logging
import math
import time

from redis.asyncio import Redis
from rate_limiter.algorithms.memory import TokenBucketState
from rate_limiter.backend.request import Rules
from rate_limiter.backend.response import Response, get_response
from rate_limiter.scripts.token_bucket import _TOKEN_BUCKET_LUA
from .base import Algorithm


class TokenBucket(Algorithm):
    def __init__(self, rules: Rules):
        # Protected (single underscore), not private: subclasses access these.
        # Double underscore would name-mangle to the subclass and break.
        self._rules = rules
        self.logger = logging.getLogger(__name__)

    def _get_refill_rate(self) -> float:
        return float(self._rules.max_requests) / float(self._rules.time_window)

    def _get_current_tokens(self, elapsed_time: float, current_tokens: float) -> int:
        refill_rate = self._get_refill_rate()
        refill_tokens = elapsed_time * refill_rate
        return math.floor(
            min(float(self._rules.max_requests), current_tokens + refill_tokens)
        )


class TokenBucketInMemory(TokenBucket):
    def __init__(self, rules: Rules):
        super().__init__(rules)
        self.__client_tokens: dict[str, TokenBucketState] = {}
        self.__lock = asyncio.Lock()

    async def execute(self, client_id: str) -> Response:
        """Execute the token bucket algorithm logic."""
        try:
            async with self.__lock:
                self.logger.info(
                    f"Start -> Executing Token Bucket In Memory Rate Limiter for client {client_id}"
                )
                current_time = time.time()

                # Get or initialize token bucket state
                if client_id not in self.__client_tokens:
                    self.logger.info(
                        f"Client {client_id} not found. Initializing new token bucket state"
                    )
                    self.__client_tokens[client_id] = {
                        "tokens": self._rules.max_requests,
                        "last_refill_timestamp": current_time,
                    }

                elapsed_time = (
                    current_time
                    - self.__client_tokens[client_id]["last_refill_timestamp"]
                )

                self.__client_tokens[client_id]["tokens"] = self._get_current_tokens(
                    elapsed_time,
                    self.__client_tokens[client_id]["tokens"],
                )
                self.__client_tokens[client_id]["last_refill_timestamp"] = current_time

                # Check if request is allowed
                if self.__client_tokens[client_id]["tokens"] >= 1:
                    self.logger.info(f"End -> Request allowed for client {client_id}")
                    self.__client_tokens[client_id]["tokens"] -= 1
                    remaining_requests = self.__client_tokens[client_id]["tokens"]
                    return get_response(
                        allowed=True,
                        remaining_requests=remaining_requests,
                        reset_time=0,
                    )
                # Calculate when next token will be available
                tokens_needed = 1 - self.__client_tokens[client_id]["tokens"]
                reset_time = float(tokens_needed) / self._get_refill_rate()
                self.logger.info(
                    f"End -> Request denied for client {client_id}. Not enough tokens."
                )
                return get_response(
                    allowed=False,
                    remaining_requests=0,
                    reset_time=reset_time,
                )
        except Exception as e:
            self.logger.error(
                f"Error -> executing token bucket for client {client_id}, error: {e}"
            )
            # Handle exceptions and return an appropriate response
            return get_response(allowed=False, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        try:
            async with self.__lock:
                self.__client_tokens.pop(client_id, None)
                return True
        except Exception as e:
            self.logger.error(f"Error -> resetting client {client_id}, error: {e}")
            return False


class TokenBucketInRedis(TokenBucket):
    def __init__(self, rules: Rules, redis_client: Redis):
        super().__init__(rules)
        self.__redis = redis_client
        self.__script = self.__redis.register_script(_TOKEN_BUCKET_LUA)

    def _key(self, client_id: str) -> str:
        return f"rl:token_bucket:{client_id}"

    async def execute(self, client_id: str) -> Response:
        try:
            self.logger.info(
                f"Start -> Executing Token Bucket Redis Rate Limiter for client {client_id}"
            )
            allowed, remaining_requests, reset_time = await self.__script(
                keys=[self._key(client_id)],
                args=[
                    self._rules.max_requests,
                    self._rules.time_window,
                    self._get_refill_rate(),
                ],
            )

            self.logger.info(
                f"End -> Request {'allowed' if allowed else 'denied'} for client {client_id}."
            )
            return get_response(
                allowed=bool(allowed),
                remaining_requests=int(remaining_requests),
                reset_time=float(reset_time),
            )
        except Exception as e:
            self.logger.error(
                f"Error -> executing token bucket for client {client_id}, error: {e}"
            )
            return get_response(allowed=False, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        try:
            await self.__redis.delete(self._key(client_id))
            return True
        except Exception as e:
            self.logger.error(f"Error -> resetting client {client_id}, error: {e}")
            return False
