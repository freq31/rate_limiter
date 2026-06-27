_SLIDING_WINDOW_LUA = """
local removed = redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])

local current = redis.call('ZCARD', KEYS[1])

if current < tonumber(ARGV[1]) then
    redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4])
    redis.call('EXPIRE', KEYS[1], ARGV[5])
    return {1, current + 1, 0}
else
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local oldest_timestamp = oldest[2]
    return {0, current, oldest_timestamp}
end
"""
