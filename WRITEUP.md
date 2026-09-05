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

## Solve modes — and why the image grounding is measurable

The solve call ships the scan image next to the OCR text (`image_grounded`, the default):
the system prompt says to trust the image over the text, so the solver's answer reflects
what is *actually printed* — which is what makes a mismatch meaningful as evidence of an
OCR defect. The image also travels on every `correct()` and `transcribe()` call in both
modes; that is non-negotiable, since the brief's remedy is *re-reading the scan*.

A selectable `SOLVE_MODE=text_only` ships the OCR text alone on the solve call — the
image then reaches the model only when a correction or transcription re-reads it. This
exists as an ablation lever: image-grounded vs text-only accuracy is directly measurable
on the same blocks (env, per-request API field, CLI flag, or the web settings panel), and
it is the honest control experiment for the claim above. The deliverable run used the
default `image_grounded`.

## Observability — the audit trail

Every run logs a complete trail at `INFO` (stdlib `logging`; `LOG_LEVEL`/`LOG_FILE`
control it): the original OCR text as extracted, every LLM prompt and response for every
try (solve, correct, transcribe), and each correction the model made. This is what made
the real defects in this project visible — a sunset OCR endpoint's fragmented output, a
gateway returning null replies, a parser misreading LaTeX as option markers — each
surfaced as an exact log line before it surfaced as a wrong answer. Image payloads are
never logged.

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

Both brief-named vendors are implemented behind the same port and contract-tested against
recorded fixtures. The submitted sample output (`results/samples.jsonl`) was produced with
**`OCR_PROVIDER=datalab`** — over datalab.to's supported **`POST /api/v1/marker`**
pipeline with `mode=balanced, output_format=markdown` — and an OpenAI-compatible
reasoning gateway (a Gemini flash model via OpenRouter) as the solver.

**Why Datalab (and why balanced):** the four sample questions are math-typeset, and math
is where OCR pipelines diverge. Marker's balanced mode recovers the formulas as clean
LaTeX (`f(x) = mx^2 - nx - k`, `\log_{\frac{1}{2}} x`) that both the parser and the
vision solver can work with.

**A vendor migration happened mid-project, and it matters for evaluation:** the adapter
was originally built on datalab's `POST /api/v1/ocr` endpoint, whose response headers
carry `Deprecation: true` and `Sunset: 2026-08-31`. Past that date the legacy endpoint
still answers but serves a degraded pipeline — on these exact scans its per-line text
fragments (`VA (F`, `(1` with no body) and it carries no markdown field at all (verified
live with fresh `skip_cache` runs and every documented parameter permutation). The
dashboard-quality text only comes from the supported marker endpoint, so the adapter was
migrated: balanced mode, top-level markdown read, contract tests pinning the submit URL
and parameters so a future sunset cannot creep back silently.

**Comparison — the local alternative:** a `local_vlm` adapter (the OpenAI-compatible
client pointed at **dots.ocr** behind a Cloudflare tunnel) also ran all four samples
end-to-end during the earlier live pass, recovering the same math regions as LaTeX with
no per-token credit ceiling. Both paths solve the deliverable's input; the hosted vendor
was chosen for the submitted run as the brief's named option, with the local run retained
as the comparison. The trade-off observed live: the hosted path bills per token (a
correction call ships the scan image, ~48k prompt tokens on Gemini's counting) and is
subject to key spending limits; the local path is free but needs the tunnel and a served
model.

**Deliverable-run evidence** (4/4 samples, `results/samples.jsonl`):

| Sample | Answer | Correction pass | Note |
|---|---|---|---|
| q113 | C | no | balanced-mode LaTeX extraction parses on the first pass |
| q115 | B | **yes** (`changed: true`) | OCR dropped/mangled formula segments; one image-grounded correction recovered the block |
| q118 | A | no | |
| q121 | C | no | marker rendered the geometry diagram as an image-description placeholder (`![…]`); the solver answered from the labeled quantities in that description |

The q115 row shows the failure class the loop exists for: the first solve produced an
answer matching no option — evidence the OCR text was broken — and one minimal
image-grounded correction recovered it. The other three blocks solved directly;
`changed: false` is the honest signal that their text needed no repair. (One honest
limitation: on q121 the marker pipeline renders the *geometry diagram* as an
image-description placeholder rather than transcribed coordinates; the solver answered
from the labeled quantities inside that description. A geometry-aware OCR pass would be
the next improvement.)

## Correctness under change — how this codebase stayed honest

The suite is 266 mocked tests (contract tests replay recorded vendor fixtures through
injected HTTP transports, so the full suite runs with zero keys; `pytest -m live` is the
opt-in real-vendor pass), plus strict typing (mypy, zero errors) and lint (ruff) as
commit gates. Three live defects this session were each caught by a failing test before
the fix, in the red→green order the repo's policy mandates: a parser that read LaTeX
tuple syntax as option markers, a vendor sunset serving degraded output, and reasoning
gateways that emit null replies under token pressure — each now a typed, tested failure
instead of a crash or a silent wrong answer. The architecture (hexagonal: `core/` never
imports a vendor SDK or a delivery mechanism) is what made every one of those fixes a
single-file change.
