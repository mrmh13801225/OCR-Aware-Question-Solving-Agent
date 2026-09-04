# OCR-Aware Question Solving Agent

A hexagonal Python service that solves Persian multiple-choice questions from scanned exam
images. It runs OCR on the image, parses the question block, and asks a vision-capable LLM
for the answer — and when the answer matches none of the printed options, it treats that
mismatch as evidence the OCR text is broken: it re-reads the image, makes a minimal
image-grounded correction, and re-solves, up to a declared retry cap. See `WRITEUP.md` for
the design rationale.

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows (source .venv/bin/activate on POSIX)
pip install -e ".[dev]"
copy .env.example .env        # fill in the keys for the providers you use
```

Set `PYTHONUTF8=1` on Windows (the console encoding must handle Persian output).

## Configuration

Providers are selected via env vars (see `.env.example`): `OCR_PROVIDER` picks the OCR
adapter (Nanonets, Datalab, or a locally-served vision model), `REASONING_PROVIDER` picks
the solver (Claude, or any OpenAI-compatible endpoint such as vLLM/Ollama). `RETRY_CAP`
(default 2), `ANSWER_MAPPING`, `NOISE_RATE`, and `NOISE_SEED` tune the loop; `RESULTS_DIR`
is where solved blocks persist as flat JSON.

## Running

Start the API server (the CLI and web UI are thin clients of it):

```
uvicorn api.main:app --ws none
```

Terminal client:

```
python -m cli.main solve tests/fixtures/samples/q113.png --trace
python -m cli.main batch tests/fixtures/samples
python -m cli.main providers
```

Web UI:

```
cd web && npm install && npm run dev     # proxies /api to the server above
```

## OCR provider used

Nanonets and Datalab are both implemented and contract-tested. The submitted sample output
was produced with **`OCR_PROVIDER=local_vlm`** pointed at **dots.ocr** (behind a tunnel),
with an OpenAI-compatible reasoning gateway as the solver — the four sample questions are
math-typeset, and dots.ocr recovered them as LaTeX where the hosted engines mangled the
option bodies. The full comparison and per-sample evidence are in `WRITEUP.md`.

## Producing the required sample output

With the API server running:

```
python scripts/run_samples.py --samples tests/fixtures/samples --out results/samples.jsonl
```

One JSON object per sample block, exactly the brief's schema:
`{"answer", "question_text", "changed", "original_ocr_text"}`.

The committed `results/samples.jsonl` is the deliverable run's output (4 samples, B/D/D/A,
one correction pass on q115).

## Tests

```
pytest              # 208 mocked tests, no API keys needed
pytest -m live      # live E2E against real provider keys — run once before submitting
```

The contract suite replays recorded fixtures through injected HTTP transports, so CI runs
with zero keys; only `pytest -m live` touches the vendors.
