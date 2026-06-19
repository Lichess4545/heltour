import json
from typing import AsyncIterator

from django.conf import settings
from redis.asyncio import Redis


async def subscribe(channel: str) -> AsyncIterator[dict]:
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for raw in pubsub.listen():
            if raw.get("type") != "message":
                continue
            data = raw.get("data")
            if not isinstance(data, str):
                continue
            yield json.loads(data)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()
