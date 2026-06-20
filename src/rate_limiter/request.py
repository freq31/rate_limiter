from pydantic import BaseModel
from enum import Enum


class AlgorithmType(str, Enum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"


class RateLimiterType(str, Enum):
    IN_MEMORY = "in_memory"
    REDIS = "redis"


class Client(BaseModel):
    uId: str


class Rules(BaseModel):
    max_requests: float
    time_window: float  # in seconds
