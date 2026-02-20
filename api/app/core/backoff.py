"""Backoff utilities.

Provides an async generator for exponential backoff strategies.
`exponential_backoff` yields the current delay for the caller to attempt an operation,
then sleeps for that delay before the next attempt. This allows consumers to easily
implement retry logic with exponential delays.
"""
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
