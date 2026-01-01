"""
Retry utilities with exponential backoff.
"""

import asyncio
import functools
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type, TypeVar, Union
import random

from whatpylib.utils.logger import get_logger

logger = get_logger("retry")

T = TypeVar("T")


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.
    
    Attributes:
        max_attempts: Maximum number of attempts (including first try)
        base_delay: Base delay between attempts in seconds
        max_delay: Maximum delay between attempts in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        jitter_factor: Maximum jitter as fraction of delay (0.0 to 1.0)
        retry_exceptions: Tuple of exception types to retry on
    """
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.1
    retry_exceptions: tuple[Type[Exception], ...] = (Exception,)
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt number.
        
        Args:
            attempt: Current attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = self.base_delay * (self.exponential_base ** attempt)
        
        # Cap at max delay
        delay = min(delay, self.max_delay)
        
        # Add jitter
        if self.jitter:
            jitter_range = delay * self.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying async functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay between attempts
        max_delay: Maximum delay between attempts
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter
        retry_exceptions: Exception types to retry on
        on_retry: Callback function called on each retry (exception, attempt)
        
    Returns:
        Decorated function
        
    Example:
        @retry(max_attempts=3, base_delay=1.0)
        async def fetch_data():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retry_exceptions=retry_exceptions,
    )
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retry_exceptions as e:
                    last_exception = e
                    
                    if attempt < config.max_attempts - 1:
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {config.max_attempts} attempts failed. Last error: {e}"
                        )
            
            # Re-raise the last exception
            raise last_exception  # type: ignore
        
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.retry_exceptions as e:
                    last_exception = e
                    
                    if attempt < config.max_attempts - 1:
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        import time
                        time.sleep(delay)
            
            raise last_exception  # type: ignore
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore
    
    return decorator


async def retry_async(
    func: Callable[..., T],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> T:
    """
    Retry an async function with the given configuration.
    
    Args:
        func: Async function to retry
        *args: Positional arguments for the function
        config: Retry configuration (uses defaults if not provided)
        **kwargs: Keyword arguments for the function
        
    Returns:
        Function result
        
    Raises:
        The last exception if all retries fail
    """
    config = config or RetryConfig()
    last_exception: Optional[Exception] = None
    
    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except config.retry_exceptions as e:
            last_exception = e
            
            if attempt < config.max_attempts - 1:
                delay = config.calculate_delay(attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
    
    raise last_exception  # type: ignore
