"""Utility functions for common programming tasks."""

import time
from collections.abc import Iterable, Iterator
from functools import wraps
from typing import Any, Callable, TypeVar


T = TypeVar("T")


def chunks(iterable: Iterable[T], size: int) -> Iterator[tuple[T, ...]]:
    """Split an iterable into chunks of specified size.

    Args:
        iterable: The input iterable to split.
        size: The maximum size of each chunk.

    Yields:
        Tuples of at most `size` elements from the iterable.

    Example:
        >>> list(chunks([1, 2, 3, 4, 5], 2))
        [(1, 2), (3, 4), (5,)]
    """
    it = iter(iterable)
    while chunk := tuple(iter(lambda: next(it, None), None) for _ in range(size)):
        if chunk[-1] is None:
            yield chunk[:-1]
            break
        yield chunk


def flatten(nested: Iterable[Iterable[T]]) -> Iterator[T]:
    """Flatten a nested iterable into a single flat iterator.

    Args:
        nested: An iterable of iterables to flatten.

    Yields:
        Individual elements from the nested iterables.

    Example:
        >>> list(flatten([[1, 2], [3, 4]]))
        [1, 2, 3, 4]
    """
    for item in nested:
        yield from item


def pairwise(iterable: Iterable[T]) -> Iterator[tuple[T, T]]:
    """Generate consecutive pairs from an iterable.

    Args:
        iterable: The input iterable.

    Yields:
        Tuples of consecutive pairs (s[i], s[i+1]).

    Example:
        >>> list(pairwise(['a', 'b', 'c']))
        [('a', 'b'), ('b', 'c')]
    """
    a, b = None, None
    for item in iterable:
        if a is not None:
            yield (a, item)
        a = item


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator to retry a function on failure.

    Args:
        max_attempts: Maximum number of retry attempts.
        delay: Delay in seconds between retries.
        exceptions: Tuple of exception types to catch.

    Returns:
        Decorated function that retries on failure.

    Example:
        >>> @retry(max_attempts=3, delay=0.1)
        ... def unreliable():
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay)
            return None
        return wrapper
    return decorator
