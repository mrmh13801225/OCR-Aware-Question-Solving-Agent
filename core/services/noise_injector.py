"""Seeded synthetic OCR noise: look-alike corruption of text bodies, never labels."""

import random
from dataclasses import replace

from core.domain.errors import NoiseError
from core.domain.models import Option, ParsedBlock
from core.services.block_parser import serialize

# Persian/Arabic scripts abound in visually confusable pairs; OCR engines
# swap exactly these. Each rule maps a character to a tuple of look-alikes.
RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "digit": {
        "۲": ("٣", "3"),
        "۳": ("٢", "2"),
        "۴": ("٤",),
        "٥": ("۴",),
        "۵": ("٠",),
        "۰": ("٥",),
        "۱": ("١",),
        "٦": ("۶",),
        "۷": ("٧",),
        "۸": ("٨",),
        "۹": ("٩",),
    },
    "letter": {
        "پ": ("ب",),
        "ب": ("پ",),
        "ژ": ("ز",),
        "ز": ("ژ",),
        "ک": ("ك",),
        "ك": ("ک",),
        "ی": ("ي",),
        "ي": ("ی",),
        "گ": ("ک",),
        "ج": ("چ",),
        "ح": ("خ",),
    },
    "diacritic": {
        "َ": ("",),
        "ُ": ("",),
        "ِ": ("",),
        "ّ": ("",),
        "ٰ": ("",),
        "ہ": ("ه",),
        "ة": ("ه",),
    },
}


def _corrupt(
    text: str, positions: list[int], table: dict[str, tuple[str, ...]], rng: random.Random
) -> str:
    chars = list(text)
    for i in positions:
        chars[i] = rng.choice(table[chars[i]])
    return "".join(chars)


class NoiseInjector:
    """Corrupt a ParsedBlock's text bodies at a declared character-level rate.

    Labels are structurally exempt: the injector never touches Option.label,
    so the parser's positional A/B/C/D assignment survives injection and the
    retry loop sees exactly what a genuinely noisy OCR pass would produce.

    The budget is computed block-wide (round(rate * total body characters))
    and spent wherever the look-alike tables have targets, so the effective
    rate matches the declared one even when bodies are short.
    """

    def __init__(
        self,
        rate: float,
        seed: int,
        rules: tuple[str, ...] = ("digit", "letter", "diacritic"),
    ) -> None:
        unknown = [r for r in rules if r not in RULES]
        if unknown:
            raise NoiseError(f"unknown noise rules: {', '.join(unknown)}")
        if not 0.0 <= rate <= 1.0:
            raise NoiseError(f"rate must be within [0, 1], got {rate}")
        self._rate = rate
        self._seed = seed
        self._rules = rules

    def corrupt(self, block: ParsedBlock) -> ParsedBlock:
        if self._rate == 0.0:
            return block
        rng = random.Random(self._seed)
        table: dict[str, tuple[str, ...]] = {}
        for rule in self._rules:
            table.update(RULES[rule])

        bodies = [block.question_text, *[o.text for o in block.options]]
        total_len = sum(len(b) for b in bodies)
        budget = round(self._rate * total_len)

        # Collect corruptible (body index, char index) targets, then spend the
        # budget across the whole block rather than per body.
        targets: list[tuple[int, int]] = [
            (bi, ci) for bi, body in enumerate(bodies) for ci, ch in enumerate(body) if ch in table
        ]
        chosen = rng.sample(targets, min(budget, len(targets)))

        per_body: dict[int, list[int]] = {}
        for bi, ci in chosen:
            per_body.setdefault(bi, []).append(ci)
        corrupted_bodies = [
            _corrupt(body, sorted(per_body.get(bi, [])), table, rng)
            for bi, body in enumerate(bodies)
        ]

        # bodies[0] is the question; the rest pair 1:1 with the block's options.
        question_text, *option_bodies = corrupted_bodies
        options = [
            Option(label=o.label, text=body)
            for o, body in zip(block.options, option_bodies, strict=True)
        ]
        corrupted_block = replace(block, question_text=question_text, options=options)
        return replace(corrupted_block, raw_text=serialize(corrupted_block))
