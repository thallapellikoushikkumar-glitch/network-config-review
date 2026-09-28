import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.subnet_utils import (
    overlaps,
    find_overlaps,
    find_next_available,
    summarize,
    fits_within,
)


def test_overlaps_true_when_subnets_intersect():
    assert overlaps("10.0.0.0/24", "10.0.0.128/25") is True


def test_overlaps_false_when_subnets_disjoint():
    assert overlaps("10.0.0.0/24", "10.0.1.0/24") is False


def test_find_overlaps_flags_the_colliding_pair_only():
    subnets = ["10.0.0.0/24", "10.0.1.0/24", "10.0.0.128/25"]
    result = find_overlaps(subnets)
    assert result == [("10.0.0.0/24", "10.0.0.128/25")]


def test_find_next_available_skips_allocated_blocks():
    result = find_next_available(
        supernet="10.0.0.0/22",
        prefix_len=24,
        already_allocated=["10.0.0.0/24", "10.0.1.0/24"],
    )
    assert result.subnet == "10.0.2.0/24"
    assert result.reason == "ok"


def test_find_next_available_reports_exhaustion():
    result = find_next_available(
        supernet="10.0.0.0/24",
        prefix_len=24,
        already_allocated=["10.0.0.0/24"],
    )
    assert result.subnet is None
    assert "fully allocated" in result.reason


def test_find_next_available_rejects_prefix_larger_than_supernet():
    result = find_next_available(
        supernet="10.0.0.0/24", prefix_len=22, already_allocated=[]
    )
    assert result.subnet is None
    assert "larger than supernet" in result.reason


def test_summarize_collapses_contiguous_subnets():
    result = summarize(["10.0.0.0/25", "10.0.0.128/25"])
    assert result == ["10.0.0.0/24"]


def test_fits_within_true_for_nested_subnet():
    assert fits_within("10.0.0.0/25", "10.0.0.0/24") is True


def test_fits_within_false_for_sibling_subnet():
    assert fits_within("10.0.1.0/25", "10.0.0.0/24") is False
