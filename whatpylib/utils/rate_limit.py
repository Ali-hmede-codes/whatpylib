"""
Rate limiting utilities for WhatsApp message sending.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from whatpylib.utils.logger import get_logger

logger = get_logger("rate_limit")


@dataclass
class RateLimiter:
    """
    Token bucket rate limiter for controlling message sending rate.
    
    Attributes:
        rate: Maximum number of operations per period
        period: Time period in seconds
        burst: Maximum burst size (tokens that can accumulate)
    """
    rate: float = 60.0  # Operations per period
    period: float = 60.0  # Period in seconds
    burst: Optional[float] = None  # Max burst (defaults to rate)
    
    _tokens: float = field(init=False, default=0.0)
    _last_update: float = field(init=False, default=0.0)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    _timestamps: deque = field(init=False, default_factory=deque)
    
    def __post_init__(self) -> None:
        """Initialize the rate limiter."""
        if self.burst is None:
            self.burst = self.rate
        self._tokens = self.burst
        self._last_update = time.monotonic()
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now
        
        # Calculate tokens to add
        tokens_to_add = elapsed * (self.rate / self.period)
        self._tokens = min(self.burst, self._tokens + tokens_to_add)  # type: ignore
    
    async def acquire(self, tokens: float = 1.0) -> float:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            Time waited in seconds
        """
        async with self._lock:
            self._refill()
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            
            # Calculate wait time
            tokens_needed = tokens - self._tokens
            wait_time = tokens_needed * (self.period / self.rate)
            
            logger.debug(f"Rate limited, waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            
            # Refill after waiting
            self._refill()
            self._tokens -= tokens
            
            return wait_time
    
    def try_acquire(self, tokens: float = 1.0) -> bool:
        """
        Try to acquire tokens without waiting.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens were acquired, False otherwise
        """
        self._refill()
        
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
    
    @property
    def available_tokens(self) -> float:
        """Get the current number of available tokens."""
        self._refill()
        return self._tokens
    
    def reset(self) -> None:
        """Reset the rate limiter to full capacity."""
        self._tokens = self.burst  # type: ignore
        self._last_update = time.monotonic()


@dataclass
class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter that tracks actual request timestamps.
    
    More accurate than token bucket but uses more memory.
    
    Attributes:
        max_requests: Maximum requests allowed in the window
        window_seconds: Time window in seconds
    """
    max_requests: int = 60
    window_seconds: float = 60.0
    
    _timestamps: deque = field(init=False, default_factory=deque)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    
    def _cleanup(self) -> None:
        """Remove timestamps outside the current window."""
        cutoff = time.monotonic() - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
    
    async def acquire(self) -> float:
        """
        Acquire permission to make a request, waiting if necessary.
        
        Returns:
            Time waited in seconds
        """
        async with self._lock:
            self._cleanup()
            
            if len(self._timestamps) < self.max_requests:
                self._timestamps.append(time.monotonic())
                return 0.0
            
            # Calculate wait time until oldest timestamp expires
            wait_time = self._timestamps[0] + self.window_seconds - time.monotonic()
            if wait_time > 0:
                logger.debug(f"Rate limited, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            # Cleanup and record new timestamp
            self._cleanup()
            self._timestamps.append(time.monotonic())
            
            return max(0.0, wait_time)
    
    def try_acquire(self) -> bool:
        """
        Try to acquire permission without waiting.
        
        Returns:
            True if permission was granted, False otherwise
        """
        self._cleanup()
        
        if len(self._timestamps) < self.max_requests:
            self._timestamps.append(time.monotonic())
            return True
        return False
    
    @property
    def remaining_requests(self) -> int:
        """Get the remaining requests allowed in the current window."""
        self._cleanup()
        return max(0, self.max_requests - len(self._timestamps))
    
    @property
    def reset_time(self) -> float:
        """Get seconds until the oldest request expires from the window."""
        self._cleanup()
        if not self._timestamps:
            return 0.0
        return max(0.0, self._timestamps[0] + self.window_seconds - time.monotonic())
    
    def reset(self) -> None:
        """Reset the rate limiter, clearing all timestamps."""
        self._timestamps.clear()
