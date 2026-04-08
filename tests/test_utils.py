"""Tests for the utils module."""

import pytest

from utils import chunks, flatten, pairwise


class TestChunks:
    def test_chunks_with_exact_fit(self):
        assert list(chunks([1, 2, 3, 4], 2)) == [(1, 2), (3, 4)]

    def test_chunks_with_remainder(self):
        assert list(chunks([1, 2, 3, 4, 5], 2)) == [(1, 2), (3, 4), (5,)]

    def test_chunks_larger_than_iterable(self):
        assert list(chunks([1, 2], 5)) == [(1, 2)]

    def test_chunks_empty_iterable(self):
        assert list(chunks([], 2)) == []

    def test_chunks_single_element(self):
        assert list(chunks([1], 2)) == [(1,)]


class TestFlatten:
    def test_flatten_simple(self):
        assert list(flatten([[1, 2], [3, 4]])) == [1, 2, 3, 4]

    def test_flatten_with_strings(self):
        assert list(flatten([["a", "b"], ["c"]])) == ["a", "b", "c"]

    def test_flatten_empty_lists(self):
        assert list(flatten([[], [1], []])) == [1]

    def test_flatten_single_nested(self):
        assert list(flatten([[1]])) == [1]


class TestPairwise:
    def test_pairwise_basic(self):
        assert list(pairwise(["a", "b", "c"])) == [("a", "b"), ("b", "c")]

    def test_pairwise_two_elements(self):
        assert list(pairwise([1, 2])) == [(1, 2)]

    def test_pairwise_single_element(self):
        assert list(pairwise([1])) == []

    def test_pairwise_empty(self):
        assert list(pairwise([])) == []


class TestRetryEdgeCases:
    """Edge case tests for the retry decorator."""

    def test_retry_returns_on_success(self):
        """Test that retry returns the function's return value."""
        from utils import retry

        @retry(max_attempts=3, delay=0.01)
        def successful_func():
            return 42

        assert successful_func() == 42

    def test_retry_with_zero_delay(self):
        """Test retry decorator with zero delay."""
        from utils import retry

        call_count = 0

        @retry(max_attempts=3, delay=0.0)
        def zero_delay_fail():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("fail")
            return "success"

        result = zero_delay_fail()
        assert result == "success"
        assert call_count == 3

    def test_retry_preserves_exception_message(self):
        """Test that the original exception message is preserved."""
        from utils import retry

        @retry(max_attempts=1, delay=0.01)
        def fail_with_message():
            raise ValueError("specific error message")

        with pytest.raises(ValueError, match="specific error message"):
            fail_with_message()

    def test_retry_with_empty_exception_tuple(self):
        """Test that empty exception tuple only catches nothing."""
        from utils import retry

        @retry(max_attempts=3, delay=0.01, exceptions=())
        def always_raises():
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError):
            always_raises()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
