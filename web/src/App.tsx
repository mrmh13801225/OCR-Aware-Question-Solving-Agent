import { useCallback, useRef, useState } from "react";
import {
  fetchProviders,
  solveBatch,
  solveBlock,
  type BlockResult,
  type ProviderInfo,
} from "./api";
import { followRun, randomRunId, type RunEvent } from "./runStream";
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
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo | null>(null);
  const [overrides, setOverrides] = useState<Overrides>({ ocr_provider: "", reasoning_provider: "" });
  const fileInput = useRef<HTMLInputElement>(null);

  const apiBase = ""; // same origin; vite proxies /api to the backend

  if (providers === null) {
    fetchProviders(apiBase).then(setProviders);
  }

  const asOverrides = useCallback(
    () => ({
      ocr_provider: overrides.ocr_provider || null,
      reasoning_provider: overrides.reasoning_provider || null,
    }),
    [overrides],
  );

  const loadSingle = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      setMode("single");
      setImageBase64((reader.result as string).split(",")[1]);
      setImageUrl(reader.result as string);
      setFileName(file.name);
      setResult(null);
      setEvents([]);
      setError(null);
      setRunState("idle");
    };
    reader.readAsDataURL(file);
  }, []);

  const loadFiles = useCallback((files: File[]) => {
    if (files.length === 1) {
      loadSingle(files[0]);
      return;
    }
    setMode("batch");
    setImageBase64(null);
    setResult(null);
    setEvents([]);
    setError(null);
    setRunState("idle");
    setBatchItems(files.map((file) => ({ name: file.name })));
    for (const file of files) {
      const reader = new FileReader();
      reader.onload = () => {
        const imageBase64 = (reader.result as string).split(",")[1];
        setBatchItems((previous) =>
          previous.map((item) => (item.name === file.name ? { ...item, imageBase64 } : item)),
        );
      };
      reader.readAsDataURL(file);
    }
  }, [loadSingle]);

  const runBatch = useCallback(async () => {
    const pending = batchItems.filter((item): item is BatchItem & { imageBase64: string } =>
      Boolean(item.imageBase64),
    );
    if (pending.length === 0) return;
    setRunState("running");
    const outcome = await solveBatch(
      apiBase,
      pending.map((item) => ({ name: item.name, imageBase64: item.imageBase64 })),
      asOverrides(),
    );
    if (outcome.ok && outcome.results) {
      // the batch endpoint returns results in input order; pending preserves that order
      const resultByName = new Map(
        pending.map((item, index) => [item.name, outcome.results![index]]),
      );
      setBatchItems((previous) =>
        previous.map((item) =>
          resultByName.has(item.name) ? { ...item, result: resultByName.get(item.name) } : item,
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
    setEvents([]);
    setError(null);
    setRunState("running");

    const stopStream = followRun(apiBase, runId, (event) => {
      setEvents((previous) => [...previous, event]);
    });

    const outcome = await solveBlock(apiBase, imageBase64, runId, asOverrides());
    stopStream();
    if (outcome.ok && outcome.result) {
      setResult(outcome.result);
      setRunState("done");
    } else {
      setError(outcome.error ?? "unknown error");
      setRunState("error");
    }
  }, [imageBase64, fileName, asOverrides]);

  const run = mode === "batch" ? runBatch : runSingle;
  const busy = runState === "running";

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setRunState("idle");
      const files = Array.from(event.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
      if (files.length) loadFiles(files);
    },
    [loadFiles],
  );

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center gap-3 border-b border-edge px-5 py-3">
        <ShamsaMark />
        <span className="font-mono text-sm text-muted">
          OCR-Aware Question Solving Agent
        </span>
        <div className="ml-auto flex items-center gap-3">
          <span className="font-mono text-xs text-muted">
            OCR: {overrides.ocr_provider || providers?.configured.ocr || "—"}
          </span>
          <span className="font-mono text-xs text-muted">
            Model: {overrides.reasoning_provider || providers?.configured.reasoning || "—"}
          </span>
          <button
            onClick={run}
            disabled={busy || (mode === "single" ? !imageBase64 : !batchItems.some((i) => i.imageBase64))}
            className="rounded bg-suspect px-4 py-1.5 text-sm font-medium text-bg disabled:opacity-40"
          >
            {busy ? "Solving…" : mode === "batch" ? `Solve ${batchItems.filter((i) => i.imageBase64).length}` : "Solve"}
          </button>
        </div>
      </header>

      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[28fr_40fr_32fr]">
        {mode === "batch" ? (
          <div className="lg:col-span-2">
            <BatchView items={batchItems} onOpen={() => {}} />
          </div>
        ) : imageBase64 ? (
          <SourcePanel
            imageUrl={imageUrl}
            ocrText={result?.original_ocr_text ?? null}
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

        {mode === "single" && (
          <RetryLoopPanel events={events} running={busy} />
        )}

        {mode === "single" ? (
          result ? (
            <VerdictPanel result={result} />
          ) : (
            <section className="hidden rounded border border-edge bg-panel p-5 shadow-panel lg:block">
              <h2 className="font-mono text-xs uppercase tracking-widest text-muted">Verdict</h2>
              <div className="mt-4">
                <SettingsPanel providers={providers} overrides={overrides} onChange={setOverrides} />
              </div>
            </section>
          )
        ) : (
          <section className="rounded border border-edge bg-panel p-5 shadow-panel">
            <h2 className="font-mono text-xs uppercase tracking-widest text-muted">Verdict</h2>
            <div className="mt-4">
              <SettingsPanel providers={providers} overrides={overrides} onChange={setOverrides} />
            </div>
          </section>
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
