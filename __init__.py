"""A utility package for common helper functions."""

__version__ = "0.1.0"

try:
    from .utils import (
        chunks,
        flatten,
        pairwise,
        retry,
    )
except ImportError:
    # When running tests, the package might not be properly installed
    from utils import (
        chunks,
        flatten,
        pairwise,
        retry,
    )

__all__ = ["chunks", "flatten", "pairwise", "retry"]
