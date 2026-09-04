import { useCallback, useEffect, useRef, useState } from "react";
import {
  base64FromDataUrl,
  fetchProviders,
  solveBatch,
  solveBlock,
  type BlockResult,
  type ProviderInfo,
} from "./api";
import { followRun, randomRunId } from "./runStream";
import { NON_ATTEMPT_INDEX, RUN_STATE } from "./runStates";
import type { TimedRunEvent } from "./components/RetryLoopPanel";
import { BatchView, type BatchItem } from "./components/BatchView";
import { RetryLoopPanel } from "./components/RetryLoopPanel";
import { SettingsPanel, type Overrides } from "./components/SettingsPanel";
import { SourcePanel } from "./components/SourcePanel";
import { VerdictPanel } from "./components/VerdictPanel";

type RunState = "idle" | "drag-over" | "running" | "done" | "error";
type Mode = "single" | "batch";

export default function App() {
  const [runState, setRunState] = useState<RunState>("idle");
  const [mode, setMode] = useState<Mode>("single");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [result, setResult] = useState<BlockResult | null>(null);
  const [events, setEvents] = useState<TimedRunEvent[]>([]);
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo | null>(null);
  const [overrides, setOverrides] = useState<Overrides>({ ocr_provider: "", reasoning_provider: "" });
  const fileInput = useRef<HTMLInputElement>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);

  const apiBase = ""; // same origin; vite proxies /api to the backend

  useEffect(() => {
    fetchProviders(apiBase).then(setProviders);
  }, []);

  const abortStream = useCallback(() => {
    stopStreamRef.current?.();
    stopStreamRef.current = null;
  }, []);

  const resetToDropzone = useCallback(() => {
    abortStream();
    setMode("single");
    setImageBase64(null);
    setImageUrl(null);
    setFileName(null);
    setResult(null);
    setEvents([]);
    setBatchItems([]);
    setError(null);
    setRunState("idle");
  }, [abortStream]);

  const asOverrides = useCallback(
    () => ({
      ocr_provider: overrides.ocr_provider || null,
      reasoning_provider: overrides.reasoning_provider || null,
    }),
    [overrides],
  );

  const loadSingle = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = () => {
        abortStream();
        setMode("single");
        setImageBase64(base64FromDataUrl(reader.result as string));
        setImageUrl(reader.result as string);
        setFileName(file.name);
        setResult(null);
        setEvents([]);
        setBatchItems([]);
        setError(null);
        setRunState("idle");
      };
      reader.readAsDataURL(file);
    },
    [abortStream],
  );

  const loadFiles = useCallback(
    (files: File[]) => {
      if (files.length === 1) {
        loadSingle(files[0]);
        return;
      }
      abortStream();
      setMode("batch");
      setImageBase64(null);
      setResult(null);
      setEvents([]);
      setError(null);
      setRunState("idle");
      const items = files.map((file) => ({ id: crypto.randomUUID(), name: file.name }));
      setBatchItems(items);
      for (const [file, item] of files.map((file, index) => [file, items[index]] as const)) {
        const reader = new FileReader();
        reader.onload = () => {
          const imageBase64 = base64FromDataUrl(reader.result as string);
          setBatchItems((previous) =>
            previous.map((existing) =>
              existing.id === item.id ? { ...existing, imageBase64 } : existing,
            ),
          );
        };
        reader.readAsDataURL(file);
      }
    },
    [abortStream, loadSingle],
  );

  const runBatch = useCallback(async () => {
    const pending = batchItems.filter((item): item is BatchItem & { imageBase64: string } =>
      Boolean(item.imageBase64),
    );
    if (pending.length === 0) return;
    setRunState("running");
    const outcome = await solveBatch(
      apiBase,
      pending.map((item) => ({ id: item.id, imageBase64: item.imageBase64 })),
      asOverrides(),
    );
    if (outcome.ok && outcome.results) {
      // the endpoint returns results in input order; pending preserves submission order
      const resultById = new Map(
        pending.map((item, index) => [item.id, outcome.results![index]]),
      );
      setBatchItems((previous) =>
        previous.map((item) =>
          resultById.has(item.id) ? { ...item, result: resultById.get(item.id) } : item,
        ),
      );
      setRunState("done");
    } else {
      setError(outcome.error ?? "unknown error");
      setRunState("error");
    }
  }, [batchItems, asOverrides]);

  const runSingle = useCallback(async () => {
    if (!imageBase64 || !fileName) return;
    const runId = randomRunId();
    const startedAt = Date.now();
    // The OCR pass ran server-side; the chip marks step zero in the rail.
    const ocrChip: TimedRunEvent = {
      run_state: RUN_STATE.OCR,
      attempt_index: NON_ATTEMPT_INDEX,
      detail: fileName,
      arrivedAt: startedAt,
    };
    setEvents([ocrChip]);
    setError(null);
    setRunState("running");

    abortStream();
    stopStreamRef.current = followRun(apiBase, runId, (event) => {
      setEvents((previous) => [...previous, { ...event, arrivedAt: Date.now() }]);
    });

    const outcome = await solveBlock(apiBase, imageBase64, runId, asOverrides());
    abortStream();
    if (outcome.ok && outcome.result) {
      setResult(outcome.result);
      setRunState("done");
    } else {
      setError(outcome.error ?? "unknown error");
      setRunState("error");
    }
  }, [imageBase64, fileName, asOverrides, abortStream]);

  const openBatchItem = useCallback(
    (id: string) => {
      const item = batchItems.find((candidate) => candidate.id === id);
      if (!item?.imageBase64) return;
      const dataUrl = `data:image/png;base64,${item.imageBase64}`;
      abortStream();
      setMode("single");
      setImageBase64(item.imageBase64);
      setImageUrl(dataUrl);
      setFileName(item.name);
      setResult(item.result ?? null);
      setEvents([]);
      setError(null);
      setRunState(item.result ? "done" : "idle");
    },
    [batchItems, abortStream],
  );

  const run = mode === "batch" ? runBatch : runSingle;
  const busy = runState === "running";
  const hasContent = mode === "batch" ? batchItems.length > 0 : imageBase64 !== null;
  const elapsedSeconds = useElapsedSeconds(busy);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setRunState("idle");
      const files = Array.from(event.dataTransfer.files).filter((f) =>
        f.type.startsWith("image/"),
      );
      if (files.length) loadFiles(files);
    },
    [loadFiles],
  );

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center gap-3 border-b border-edge px-5 py-3">
        <ShamsaMark />
        {fileName && <span className="font-mono text-xs text-ink">{fileName}</span>}
        <span className="font-mono text-sm text-muted">
          OCR-Aware Question Solving Agent
        </span>
        <div className="ml-auto flex items-center gap-3">
          {providers && (
            <select
              value={overrides.ocr_provider}
              onChange={(e) => setOverrides({ ...overrides, ocr_provider: e.target.value })}
              className="rounded bg-codebg px-2 py-1 font-mono text-xs text-ink"
              aria-label="OCR provider"
            >
              <option value="">OCR: {providers.configured.ocr}</option>
              {providers.ocr.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}
          {providers && (
            <select
              value={overrides.reasoning_provider}
              onChange={(e) => setOverrides({ ...overrides, reasoning_provider: e.target.value })}
              className="rounded bg-codebg px-2 py-1 font-mono text-xs text-ink"
              aria-label="Reasoning model"
            >
              <option value="">Model: {providers.configured.reasoning}</option>
              {providers.reasoning.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={run}
            disabled={busy || (mode === "single" ? !imageBase64 : !batchItems.some((i) => i.imageBase64))}
            className="rounded bg-suspect px-4 py-1.5 text-sm font-medium text-bg disabled:opacity-40"
          >
            {busy
              ? `Solving… ${elapsedSeconds}s`
              : mode === "batch"
                ? `Solve ${batchItems.filter((i) => i.imageBase64).length}`
                : "Solve"}
          </button>
          {hasContent && (
            <button
              onClick={resetToDropzone}
              className="rounded bg-codebg px-3 py-1.5 font-mono text-xs text-muted hover:text-ink"
            >
              New
            </button>
          )}
        </div>
      </header>

      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[28fr_40fr_32fr]">
        {mode === "batch" ? (
          <div className="lg:col-span-2">
            <BatchView items={batchItems} onOpen={openBatchItem} />
          </div>
        ) : imageBase64 ? (
          <SourcePanel
            imageUrl={imageUrl}
            ocrText={result?.original_ocr_text ?? null}
            finalQuestionText={result?.question_text ?? null}
            fileName={fileName}
          />
        ) : (
          <DropZone
            onDrop={onDrop}
            dragging={runState === "drag-over"}
            onDragOver={() => setRunState("drag-over")}
            onDragLeave={() => setRunState("idle")}
            onPick={() => fileInput.current?.click()}
          />
        )}

        {mode === "single" && <RetryLoopPanel events={events} running={busy} result={result} />}

        {mode === "single" && result ? (
          <VerdictPanel result={result} />
        ) : (
          <PanelShell title="Verdict">
            <SettingsPanel providers={providers} overrides={overrides} onChange={setOverrides} />
          </PanelShell>
        )}
      </main>

      {error && (
        <div className="mx-4 mb-4 rounded border border-proof bg-panel p-3">
          <p className="font-mono text-sm text-proof">{error}</p>
          <p className="text-xs text-muted">
            Check that the API server is running (uvicorn api.main:app) and try again.
          </p>
        </div>
      )}

      <input
        ref={fileInput}
        type="file"
        multiple
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => e.target.files && loadFiles(Array.from(e.target.files))}
      />
    </div>
  );
}

function PanelShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="hidden rounded border border-edge bg-panel p-5 shadow-panel lg:block">
      <h2 className="font-mono text-xs uppercase tracking-widest text-muted">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Seconds since `active` became true, ticking once a second; resets when inactive. */
function useElapsedSeconds(active: boolean): number {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    setElapsedSeconds(0);
    const interval = setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [active]);
  return elapsedSeconds;
}

function DropZone({
  onDrop,
  dragging,
  onDragOver,
  onDragLeave,
  onPick,
}: {
  onDrop: (e: React.DragEvent) => void;
  dragging: boolean;
  onDragOver: () => void;
  onDragLeave: () => void;
  onPick: () => void;
}) {
  return (
    <div
      onDrop={onDrop}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver();
      }}
      onDragLeave={onDragLeave}
      className={`flex items-center justify-center rounded border-2 border-dashed p-8 ${
        dragging ? "border-suspect" : "border-edge"
      }`}
    >
      <div className="text-center">
        <p className="text-muted">Drop one or more question blocks to solve them</p>
        <button
          onClick={onPick}
          className="mt-3 rounded bg-codebg px-3 py-1.5 font-mono text-xs text-muted hover:text-ink"
        >
          or choose files
        </button>
      </div>
    </div>
  );
}

function ShamsaMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-7 w-7 text-suspect" aria-hidden="true">
      <g fill="currentColor">
        <path d="M12 2l1.8 6.2L20 6.4l-4.4 4.7L22 12l-6.4.9L20 17.6l-6.2-1.8L12 22l-1.8-6.2L4 17.6l4.4-4.7L2 12l6.4-.9L4 6.4l6.2 1.8z" />
      </g>
    </svg>
  );
}
