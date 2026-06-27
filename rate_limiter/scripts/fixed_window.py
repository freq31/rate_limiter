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
