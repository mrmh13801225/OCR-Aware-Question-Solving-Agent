# Write-up

## Retry cap

**Cap: 2 corrections (3 solve attempts total).**

> TODO: keep or revise this justification once you've seen real provider behavior:
> One grounded re-read against the image fixes the common single-error case; a second covers
> compounding errors (fixing one exposes another, or the first correction undershoots). Beyond
> two, correction quality tends to degrade — the model risks drifting the question text to force
> some option to match rather than making a minimal, plausible fix — and cost grows unbounded.
> Worst case per block: 3 solve calls + 2 correct calls.

## Unresolved case — how the best guess is picked

> TODO: confirm this matches the actual implementation in `core/services/best_guess.py`:
> 1. Fuzzy re-check (edit distance ≤1) of all attempts' raw answers against the options.
> 2. If still nothing, majority vote across all attempts' raw answers.
> 3. Otherwise, the first attempt's answer (least-mutated text = most grounded).
> Always flagged `unresolved: true` in the output.

## Synthetic OCR noise

> TODO: state the actual perturbation rate used (characters/words per block) once
> `core/services/noise_injector.py` is finalized, and roughly how many of the test blocks
> went through it vs. genuinely noisy OCR.

## OCR provider

> TODO: which of Nanonets / Datalab, and why (pricing, accuracy on this data, API ergonomics).
