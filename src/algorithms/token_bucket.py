import asyncio
import time
from src.algorithms.memory import TokenBucketState
from src.rate_limiter.request import Rules
from src.rate_limiter.response import Response, get_response
from .base import Algorithm


class TokenBucket(Algorithm):
    pass


class TokenBucketInMemory(TokenBucket):
    def __init__(self, rules: Rules):
        self.__rules = rules
        self.__client_tokens: dict[str, TokenBucketState] = {}
        self.__lock = asyncio.Lock()

    async def execute(self, client_id: str) -> Response:
        """Execute the token bucket algorithm logic."""
        try:
            async with self.__lock:
                current_time = time.time()

                # Get or initialize token bucket state
                if client_id not in self.__client_tokens:
                    self.__client_tokens[client_id] = {
                        "tokens": self.__rules.max_requests,
                        "last_refill_timestamp": current_time,
                    }

                elapsed_time = (
                    current_time
                    - self.__client_tokens[client_id]["last_refill_timestamp"]
                )

                # Calculate refill tokens based on elapsed time
                refill_rate = self.__rules.max_requests / self.__rules.time_window
                refill_tokens = elapsed_time * refill_rate
                self.__client_tokens[client_id]["tokens"] = min(
                    self.__rules.max_requests,
                    self.__client_tokens[client_id]["tokens"] + refill_tokens,
                )
                self.__client_tokens[client_id]["last_refill_timestamp"] = current_time

                # Check if request is allowed
                if self.__client_tokens[client_id]["tokens"] >= 1:
                    self.__client_tokens[client_id]["tokens"] -= 1
                    remaining_requests = int(self.__client_tokens[client_id]["tokens"])
                    return get_response(
                        allowed=True,
                        remaining_requests=remaining_requests,
                        reset_time=0,
                    )
                # Calculate when next token will be available
                tokens_needed = 1 - self.__client_tokens[client_id]["tokens"]
                reset_time = tokens_needed / refill_rate
                return get_response(
                    allowed=False,
                    remaining_requests=0,
                    reset_time=reset_time,
                )
        except Exception:
            # Handle exceptions and return an appropriate response
            return get_response(allowed=False, remaining_requests=0, reset_time=0)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        try:
            async with self.__lock:
                self.__client_tokens.pop(client_id, None)
                return True
        except Exception as e:
            print(f"Error resetting client {client_id}: {e}")
            return False


class TokenBucketInRedis(TokenBucket):
    def __init__(self, rules: Rules):
        self.__rules = rules
        self.__client_tokens: dict[str, TokenBucketState] = {}
        self.__lock = asyncio.Lock()

    async def execute(self, client_id: str) -> Response:
        # Implement the fixed window algorithm logic here
        return Response(allowed=True)

    async def reset(self, client_id: str) -> bool:
        """Reset the request count for the given user."""
        return True
