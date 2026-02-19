import asyncio
from typing import AsyncIterator


async def exponential_backoff(
    initial_delay: float,
    max_delay: float,
    multiplier: float,
    max_attempts: int,
) -> AsyncIterator[float]:
    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        yield delay
        if attempt < max_attempts:
            delay = min(delay * multiplier, max_delay)
            await asyncio.sleep(delay)
