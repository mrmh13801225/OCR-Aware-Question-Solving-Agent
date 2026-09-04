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

Nanonets and Datalab are implemented behind the same port and contract-tested against
recorded fixtures. The submitted sample output (`results/samples.jsonl`) was produced with
**`OCR_PROVIDER=local_vlm`** — the adapter reuses the OpenAI-compatible client pointed at
**dots.ocr** served behind a Cloudflare tunnel — with an OpenAI-compatible reasoning
gateway as the solver.

**Why a local model over the hosted vendors:** the four sample questions are math-typeset,
and that is exactly where the hosted engines broke down. Datalab mangled the
math-typeset option bodies (and serves no `/olm` endpoint — the live pass had to adopt
their real `POST /api/v1/ocr` submit-then-poll contract from their published OpenAPI spec).
dots.ocr recovered the same regions as clean LaTeX (`f(x) = mx^2 - nx - k`,
`\log_{\frac{1}{2}} x`), which both the parser and the vision solver can work with. On
plain prose Persian the hosted engines were fine; on this deliverable's actual input the
local vision model won decisively.

**Live-pass evidence** (4/4 samples, `results/samples.jsonl`):

| Sample | Answer | Correction pass | Note |
|---|---|---|---|
| q112 | B | no | math-typeset options extracted as LaTeX |
| q115 | D | **yes** (`changed: true`) | OCR misread "ریشه‌های" → "ر Appalachian", plus wrong log bases; one correction pass repaired it |
| q118 | D | no | |
| q121 | A | no | |

The q115 `original_ocr_text` shows the failure class the loop exists for: the OCR text was
objectively wrong, the first solve produced an answer matching no option, and the
image-grounded correction recovered the question. The other three blocks solved directly —
`changed: false` is the honest signal that their OCR text needed no repair.

The hosted engines were also exercised live during development (`pytest -m live`): both
mapped cleanly onto the port, but neither survived the math-typeset extraction above, so
the deliverable run uses the local adapter.
