_TOKEN_BUCKET_LUA = """
local current = redis.call('HGET', KEYS[1], 'tokens')
local last_refill_timestamp = redis.call('HGET', KEYS[1], 'last_refill_timestamp')

local t = redis.call('TIME')
local current_time = tonumber(t[1]) + tonumber(t[2]) / 1000000

local current_tokens = 0

if current == false or last_refill_timestamp == false then
    current_tokens = tonumber(ARGV[1])
    last_refill_timestamp = current_time
else
    local elapsed_time = current_time - last_refill_timestamp
    local refill_tokens = tonumber( elapsed_time * ARGV[3] )
    current_tokens = tonumber(current) + refill_tokens
end

if current_tokens > tonumber(ARGV[1]) then
    current_tokens = tonumber(ARGV[1])
end

if current_tokens >= 1 then
    current_tokens = current_tokens - 1
    redis.call('HSET', KEYS[1], 'tokens', current_tokens)
    redis.call('HSET', KEYS[1], 'last_refill_timestamp', current_time)
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return {1, current_tokens, 0}
else
    redis.call('HSET', KEYS[1], 'tokens', current_tokens)
    redis.call('HSET', KEYS[1], 'last_refill_timestamp', current_time)
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    local tokens_needed = 1 - current_tokens
    local reset_time = tokens_needed / ARGV[3]
    return {0, 0, tostring(reset_time)}
end
"""
