"""Stub - Phase 1 follow-up. Should cover: cache hit within ttl skips the network
call, cache miss fetches and persists, retry/backoff triggers on 5xx and gives up
after MAX_RETRIES, and non-2xx responses are never cached.
"""
