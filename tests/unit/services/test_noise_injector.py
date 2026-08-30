"""T1.5 — seeded noise injector: look-alike corruption, labels always safe."""

from statistics import mean

from core.domain.models import Option, ParsedBlock
from core.services.block_parser import parse
from core.services.noise_injector import NoiseInjector

SAMPLE = parse("کدام گزینه درست است؟\n۱) تهران\n۲) مشهد پایتخت\n۳) اصفهان\n۴) تبریز")


def _all_text(block: ParsedBlock) -> str:
    return block.question_text + "".join(o.text for o in block.options)


def test_same_seed_produces_identical_output() -> None:
    first = NoiseInjector(rate=0.2, seed=7).corrupt(SAMPLE)
    second = NoiseInjector(rate=0.2, seed=7).corrupt(SAMPLE)
    assert first == second


def test_zero_rate_returns_equal_block() -> None:
    assert NoiseInjector(rate=0.0, seed=1).corrupt(SAMPLE) == SAMPLE


def test_rate_respected_statistically() -> None:
    rates: list[float] = []
    for seed in range(200):
        corrupted = NoiseInjector(rate=0.10, seed=seed).corrupt(SAMPLE)
        before = sum(len(o.text) for o in SAMPLE.options) + len(SAMPLE.question_text)
        changes = sum(
            1 for a, b in zip(_all_text(SAMPLE), _all_text(corrupted), strict=True) if a != b
        )
        rates.append(changes / before)
    assert 0.085 <= mean(rates) <= 0.115


def test_labels_are_never_corrupted() -> None:
    for seed in range(100):
        corrupted = NoiseInjector(rate=1.0, seed=seed).corrupt(SAMPLE)
        assert [o.label for o in corrupted.options] == ["A", "B", "C", "D"]
    assert [o.label for o in NoiseInjector(rate=1.0, seed=0).corrupt(SAMPLE).options] == [
        "A",
        "B",
        "C",
        "D",
    ]


def test_digit_lookalike_rule_applies() -> None:
    injector = NoiseInjector(rate=1.0, seed=0, rules=["digit"])
    block = ParsedBlock(
        question_text="سؤال",
        options=[Option("A", "۲"), Option("B", "۳"), Option("C", "۴"), Option("D", "۵")],
        raw_text="raw",
    )
    corrupted = injector.corrupt(block)
    assert _all_text(corrupted) != _all_text(block)
    assert any(ch in "٣٠١٢٣٤٥٦٧٨٩" for ch in _all_text(corrupted))


def test_letter_lookalike_rule_applies() -> None:
    injector = NoiseInjector(rate=1.0, seed=0, rules=["letter"])
    block = ParsedBlock(
        question_text="سؤال",
        options=[Option("A", "پ"), Option("B", "ژ"), Option("C", "ک"), Option("D", "ی")],
        raw_text="raw",
    )
    corrupted = injector.corrupt(block)
    assert _all_text(corrupted) != _all_text(block)


def test_diacritic_and_tashkeel_loss_rule_applies() -> None:
    injector = NoiseInjector(rate=1.0, seed=0, rules=["diacritic"])
    block = ParsedBlock(
        question_text="سؤال",
        options=[Option("A", "مُعَلِّم"), Option("B", "کِتاب"), Option("C", "خانہ"), Option("D", "دَرس")],
        raw_text="raw",
    )
    corrupted = injector.corrupt(block)
    assert _all_text(corrupted) != _all_text(block)


def test_change_count_bounded_per_block() -> None:
    long_block = ParsedBlock(
        question_text="این یک سؤال آزمایشی طولانی است " * 4,
        options=[
            Option("A", "متن گزینه اول اینجا قرار دارد"),
            Option("B", "متن گزینه دوم اینجا قرار دارد"),
            Option("C", "متن گزینه سوم اینجا قرار دارد"),
            Option("D", "متن گزینه چهارم اینجا قرار دارد"),
        ],
        raw_text="raw",
    )
    for seed in range(50):
        corrupted = NoiseInjector(rate=0.05, seed=seed).corrupt(long_block)
        total_len = len(_all_text(long_block))
        changes = sum(
            1 for a, b in zip(_all_text(long_block), _all_text(corrupted), strict=True) if a != b
        )
        assert changes <= int(0.05 * total_len) + 2


def test_output_still_parses() -> None:
    for seed in range(50):
        corrupted = NoiseInjector(rate=0.05, seed=seed).corrupt(SAMPLE)
        reparsed = parse(corrupted.raw_text)
        assert len(reparsed.options) == 4


def test_unknown_rule_name_raises() -> None:
    import pytest

    from core.domain.errors import NoiseError

    with pytest.raises(NoiseError):
        NoiseInjector(rate=0.1, seed=1, rules=["nonexistent"])
