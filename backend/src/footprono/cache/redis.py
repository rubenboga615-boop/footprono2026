"""Client Redis partagé (cache, limitation de débit, verrous)."""

from redis.asyncio import Redis

from footprono.core.config import Settings


def create_redis(settings: Settings) -> Redis:
    client: Redis = Redis.from_url(
        str(settings.redis_url),
        decode_responses=True,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    return client


async def ping(client: Redis) -> None:
    if not await client.ping():
        raise ConnectionError("Redis n'a pas répondu au PING")
