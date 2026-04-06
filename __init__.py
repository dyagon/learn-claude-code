"""A utility package for common helper functions."""

__version__ = "0.1.0"

from .utils import (
    chunks,
    flatten,
    pairwise,
    retry,
)

__all__ = ["chunks", "flatten", "pairwise", "retry"]
