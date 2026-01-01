"""
Event emitter for handling WhatsApp events.

This provides an async-first event system similar to Node.js EventEmitter
but designed for Python's async patterns.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional, TypeVar, Union
import functools

from whatpylib.utils.logger import get_logger

logger = get_logger("events")

# Type for event handlers
EventHandler = Callable[..., Union[None, Coroutine[Any, Any, None]]]
T = TypeVar("T")


@dataclass
class EventListener:
    """
    Represents a registered event listener.
    
    Attributes:
        handler: The callback function
        once: Whether this listener should only fire once
        priority: Listener priority (higher = called first)
    """
    handler: EventHandler
    once: bool = False
    priority: int = 0
    
    def __hash__(self) -> int:
        return hash(id(self.handler))
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, EventListener):
            return self.handler is other.handler
        return False


class EventEmitter:
    """
    Async-compatible event emitter for WhatsApp events.
    
    Example:
        emitter = EventEmitter()
        
        @emitter.on("message")
        async def handle_message(msg):
            print(f"Received: {msg}")
        
        await emitter.emit("message", TextMessage(...))
    """
    
    def __init__(self, max_listeners: int = 100) -> None:
        """
        Initialize the event emitter.
        
        Args:
            max_listeners: Maximum listeners per event (warns if exceeded)
        """
        self._listeners: dict[str, list[EventListener]] = defaultdict(list)
        self._max_listeners = max_listeners
    
    def on(
        self,
        event: str,
        handler: Optional[EventHandler] = None,
        priority: int = 0,
    ) -> Union[EventHandler, Callable[[EventHandler], EventHandler]]:
        """
        Register an event listener.
        
        Can be used as a decorator or called directly:
        
            @emitter.on("message")
            async def handler(msg): ...
            
            # OR
            
            emitter.on("message", handler)
        
        Args:
            event: Event name to listen for
            handler: Optional handler function (if not using as decorator)
            priority: Listener priority (higher = called first)
            
        Returns:
            The handler (for decorator use)
        """
        def register(h: EventHandler) -> EventHandler:
            self.add_listener(event, h, once=False, priority=priority)
            return h
        
        if handler is not None:
            return register(handler)
        return register
    
    def once(
        self,
        event: str,
        handler: Optional[EventHandler] = None,
        priority: int = 0,
    ) -> Union[EventHandler, Callable[[EventHandler], EventHandler]]:
        """
        Register a one-time event listener.
        
        The listener will be removed after it fires once.
        
        Args:
            event: Event name to listen for
            handler: Optional handler function
            priority: Listener priority
            
        Returns:
            The handler (for decorator use)
        """
        def register(h: EventHandler) -> EventHandler:
            self.add_listener(event, h, once=True, priority=priority)
            return h
        
        if handler is not None:
            return register(handler)
        return register
    
    def add_listener(
        self,
        event: str,
        handler: EventHandler,
        once: bool = False,
        priority: int = 0,
    ) -> None:
        """
        Add an event listener.
        
        Args:
            event: Event name
            handler: Callback function
            once: Whether to remove after first call
            priority: Listener priority
        """
        listener = EventListener(handler=handler, once=once, priority=priority)
        listeners = self._listeners[event]
        
        # Check max listeners
        if len(listeners) >= self._max_listeners:
            logger.warning(
                f"Max listeners ({self._max_listeners}) exceeded for event '{event}'. "
                "This may indicate a memory leak."
            )
        
        # Insert in priority order (higher priority first)
        listeners.append(listener)
        listeners.sort(key=lambda l: -l.priority)
    
    def remove_listener(self, event: str, handler: EventHandler) -> bool:
        """
        Remove an event listener.
        
        Args:
            event: Event name
            handler: The handler to remove
            
        Returns:
            True if the listener was found and removed
        """
        listeners = self._listeners.get(event, [])
        for i, listener in enumerate(listeners):
            if listener.handler is handler:
                listeners.pop(i)
                return True
        return False
    
    def off(self, event: str, handler: EventHandler) -> bool:
        """Alias for remove_listener."""
        return self.remove_listener(event, handler)
    
    def remove_all_listeners(self, event: Optional[str] = None) -> None:
        """
        Remove all listeners for an event or all events.
        
        Args:
            event: Event name (if None, removes all listeners for all events)
        """
        if event is None:
            self._listeners.clear()
        elif event in self._listeners:
            del self._listeners[event]
    
    async def emit(self, event: str, *args: Any, **kwargs: Any) -> bool:
        """
        Emit an event, calling all registered listeners.
        
        Args:
            event: Event name
            *args: Arguments to pass to listeners
            **kwargs: Keyword arguments to pass to listeners
            
        Returns:
            True if any listeners were called
        """
        listeners = self._listeners.get(event, [])
        if not listeners:
            return False
        
        # Track listeners to remove (for `once`)
        to_remove: list[EventListener] = []
        
        for listener in listeners:
            try:
                result = listener.handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in event handler for '{event}': {e}")
                # Emit error event (but don't re-emit if already handling error)
                if event != "error":
                    await self.emit("error", e, event)
            
            if listener.once:
                to_remove.append(listener)
        
        # Remove one-time listeners
        for listener in to_remove:
            if listener in listeners:
                listeners.remove(listener)
        
        return True
    
    def emit_sync(self, event: str, *args: Any, **kwargs: Any) -> bool:
        """
        Emit an event synchronously (for sync handlers only).
        
        Warning: This will not await async handlers!
        
        Args:
            event: Event name
            *args: Arguments to pass to listeners
            **kwargs: Keyword arguments to pass to listeners
            
        Returns:
            True if any listeners were called
        """
        listeners = self._listeners.get(event, [])
        if not listeners:
            return False
        
        to_remove: list[EventListener] = []
        
        for listener in listeners:
            try:
                result = listener.handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    # Schedule coroutine but don't await
                    asyncio.create_task(result)
            except Exception as e:
                logger.error(f"Error in sync event handler for '{event}': {e}")
            
            if listener.once:
                to_remove.append(listener)
        
        for listener in to_remove:
            if listener in listeners:
                listeners.remove(listener)
        
        return True
    
    def listener_count(self, event: str) -> int:
        """Get the number of listeners for an event."""
        return len(self._listeners.get(event, []))
    
    def event_names(self) -> list[str]:
        """Get list of event names that have listeners."""
        return list(self._listeners.keys())
    
    async def wait_for(
        self,
        event: str,
        check: Optional[Callable[..., bool]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Wait for an event to be emitted.
        
        Args:
            event: Event name to wait for
            check: Optional function to filter events
            timeout: Optional timeout in seconds
            
        Returns:
            The event data
            
        Raises:
            asyncio.TimeoutError: If timeout is reached
        """
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        
        def handler(*args: Any, **kwargs: Any) -> None:
            if check is None or check(*args, **kwargs):
                if not future.done():
                    if len(args) == 1 and not kwargs:
                        future.set_result(args[0])
                    else:
                        future.set_result((args, kwargs))
        
        self.once(event, handler)
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self.remove_listener(event, handler)
            raise
