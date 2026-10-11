from yaatv.models import FFmpegResult


def test_same_return_code_and_tail_are_equal() -> None:
    # The dataclass generates `__eq__` into this class, so there is none on the parent to
    # defer to. Deferring reached `object.__eq__`, which is identity, and two results that
    # carried the same return code and tail compared unequal unless they were the same object.
    assert FFmpegResult(0, "x") == FFmpegResult(0, "x")
    assert not (FFmpegResult(0, "x") != FFmpegResult(0, "x"))


def test_different_return_code_is_not_equal() -> None:
    assert FFmpegResult(0, "x") != FFmpegResult(1, "x")


def test_different_tail_is_not_equal() -> None:
    assert FFmpegResult(1, "a") != FFmpegResult(1, "b")


def test_default_tail_matches_an_explicit_empty_tail() -> None:
    assert FFmpegResult(0) == FFmpegResult(0, "")


def test_comparison_with_an_int_reads_the_return_code() -> None:
    # The CLI relies on this arm, so it has to survive the field comparison above.
    assert FFmpegResult(0, "x") == 0
    assert FFmpegResult(0, "x") != 1
    assert int(FFmpegResult(7, "x")) == 7
    assert str(FFmpegResult(7, "x")) == "7"


def test_a_result_is_not_equal_to_an_unrelated_object() -> None:
    # Returning NotImplemented rather than raising is what lets Python fall back and answer
    # False, instead of a TypeError leaking out of a comparison.
    assert FFmpegResult(0, "x") != "0"
    assert FFmpegResult(0, "x") != None  # noqa: E711  - comparing to None is the point


def test_equal_results_hash_together() -> None:
    # Redefining `__eq__` clears the generated `__hash__`, and an inconsistent pair puts equal
    # results in different buckets: a set kept both and a dict lookup missed.
    a = FFmpegResult(0, "x")
    b = FFmpegResult(0, "x")
    assert hash(a) == hash(b)
    assert len({a, b}) == 1
    assert {a: "seen"}.get(b) == "seen"


def test_results_differing_in_a_field_do_not_collide_in_a_set() -> None:
    results = {FFmpegResult(0, "x"), FFmpegResult(1, "x"), FFmpegResult(0, "y")}
    assert len(results) == 3


def test_a_result_hashes_like_the_int_it_equals() -> None:
    # `__hash__` hashes only the return code, so the `== int` arm above is hash-consistent too.
    assert hash(FFmpegResult(0, "x")) == hash(0)
