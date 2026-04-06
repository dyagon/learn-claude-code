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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
