# Write-up

## Retry cap

**Cap: 2 corrections (3 solve attempts total).**

One grounded re-read against the image fixes the common single-error case: the noise model
we inject (and real Persian OCR errors) are a handful of look-alike character swaps, and one
image-grounded correction pass recovers them. A second correction covers compounding cases —
fixing one error exposes another, or the first correction undershoots. Beyond two, correction
quality degrades: the model risks drifting the question text to force *some* option to match
rather than making a minimal, plausible fix — which directly violates the correction-quality
criterion — and cost grows unbounded. Worst case per block is 3 solve calls + 2 correct
calls, bounded and predictable. The cap is enforced in `core/services/retry_loop.py` and
configurable via `RETRY_CAP`; the loop terminates against adversarial providers regardless.

## Unresolved case — how the best guess is picked

When the cap is exhausted with no match (`core/services/best_guess.py`):

1. **Fuzzy re-check** across all attempts' raw answers — strict normalization, then a
   drop-one-character re-check (stray marks), then a visually-confusable letter table
   (C↔G, O↔D, B↔E). Free-string edit distance is deliberately *not* used: every
   single-letter string would be within distance 1 of every one-letter label. Out-of-range
   strict mappings (a G for a 4-option block) fall through to the confusable table, because
   OCR reads C as G — not as option G.
2. **Majority vote** across all attempts' raw answers. Note a mappable letter cannot appear
   here — any answer matching an option would have ended the loop before cap-out — so a
   garbage majority degrades to the fallback below.
3. **First attempt's answer** — the least-mutated text is the most grounded read.

Every unresolved result carries `unresolved: true`.

## Synthetic OCR noise

The injector (`core/services/noise_injector.py`) corrupts **parsed blocks post-parse** at a
declared character-level rate of **5%** (`NOISE_RATE=0.05`), from three look-alike rule
families mirroring real Persian OCR confusions: digit swaps (۲↔٣, Persian↔Arabic-Indic
forms), letter look-alikes (پ↔ب, ژ↔ز, ک↔ك, ی↔ي), and diacritic/tashkeel loss. A seeded RNG
makes every corruption reproducible (`NOISE_SEED`); labels are structurally exempt, so the
positional A/B/C/D assignment always survives injection and the retry loop sees exactly what
a genuinely noisy OCR pass would produce. The perturbation rate is pinned statistically
(200-seed average within ±1.5 points) and the per-block change count is bounded.

In the unit suite, noise-injected blocks exercise the same retry paths as genuinely dirty
OCR; the live-pass comparison (below) uses the genuinely OCR-produced text.

## OCR provider

Both Nanonets and Datalab are implemented behind the same port and contract-tested. The
submitted sample output uses **[TO BE FILLED after the live pass]**.

**Live comparison evidence** (fill in from `pytest -m live` output on the 4 samples):

| Criterion | Nanonets | Datalab |
|---|---|---|
| Extraction success on 4/4 samples | | |
| Persian text quality (look-alike errors) | | |
| Latency per image | | |
| API ergonomics (auth, async polling, docs) | | |

**Chosen: [Nanonets / Datalab] — because [one or two sentences grounded in the table].**
