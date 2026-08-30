# OCR-Aware Question Solving Agent

> TODO once implemented: 1–2 sentence summary.

## Setup

```
# TODO: python venv/uv instructions
# TODO: npm install for web/
```

## Configuration

Copy `.env.example` to `.env` and fill in the keys for whichever providers you use. See `DESIGN.md` §12 for the full variable reference.

## Running

```
# TODO: uvicorn command
# TODO: cli usage
# TODO: web dev server command
```

## OCR provider used

> TODO: state which of Nanonets / Datalab was used for the submitted sample output, and why.

## Producing the required sample output

```
python scripts/run_samples.py --samples tests/fixtures/samples --out results/samples.jsonl
```

## Tests

```
pytest              # mocked suite, no API keys needed
pytest -m live       # live E2E against real provider keys
```

See `TESTING.md` for the full test policy.
