from pydantic import BaseModel


class Response(BaseModel):
    allowed: bool
    remaining_requests: int
    reset_time: float


def get_response(allowed: bool, remaining_requests: int, reset_time: float) -> Response:
    return Response(
        allowed=allowed,
        remaining_requests=remaining_requests,
        reset_time=reset_time,
    )
