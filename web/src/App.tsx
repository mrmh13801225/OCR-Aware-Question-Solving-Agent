import { useCallback, useRef, useState } from "react";
import { fetchProviders, solveBlock, type BlockResult, type ProviderInfo } from "./api";
import { SourcePanel } from "./components/SourcePanel";
import { VerdictPanel } from "./components/VerdictPanel";

type RunState = "idle" | "drag-over" | "running" | "done" | "error";

export default function App() {
  const [runState, setRunState] = useState<RunState>("idle");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [result, setResult] = useState<BlockResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const apiBase = ""; // same origin; vite proxies /api to the backend

  if (providers === null) {
    fetchProviders(apiBase).then(setProviders);
  }

  const loadFile = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      setImageBase64((reader.result as string).split(",")[1]);
      setImageUrl(reader.result as string);
      setFileName(file.name);
      setResult(null);
      setError(null);
      setRunState("idle");
    };
    reader.readAsDataURL(file);
  }, []);

  const run = useCallback(async () => {
    if (!imageBase64 || !fileName) return;
    setRunState("running");
    const outcome = await solveBlock(apiBase, imageBase64, `web-${fileName}`);
    if (outcome.ok && outcome.result) {
      setResult(outcome.result);
      setRunState("done");
    } else {
      setError(outcome.error ?? "unknown error");
      setRunState("error");
    }
  }, [imageBase64, fileName]);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setRunState("idle");
      const file = event.dataTransfer.files[0];
      if (file) loadFile(file);
    },
    [loadFile],
  );

  const busy = runState === "running";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center gap-3 border-b border-edge px-5 py-3">
        <ShamsaMark />
        <span className="font-mono text-sm text-muted">
          OCR-Aware Question Solving Agent
        </span>
        <div className="ml-auto flex items-center gap-3">
          <span className="font-mono text-xs text-muted">
            OCR: {providers?.configured.ocr ?? "—"}
          </span>
          <span className="font-mono text-xs text-muted">
            Model: {providers?.configured.reasoning ?? "—"}
          </span>
          <button
            onClick={run}
            disabled={!imageBase64 || busy}
            className="rounded bg-suspect px-4 py-1.5 text-sm font-medium text-bg disabled:opacity-40"
          >
            {busy ? "Solving…" : "Solve"}
          </button>
        </div>
      </header>

      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[28fr_40fr_32fr]">
        {imageBase64 ? (
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

        <section className="hidden rounded border border-edge bg-panel p-5 shadow-panel lg:flex lg:flex-col">
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted">Retry loop</h2>
          {runState === "running" && <p className="mt-4 text-sm text-muted">Running…</p>}
          {runState === "idle" && (
            <p className="mt-4 text-sm text-muted">The live trace appears here during a run.</p>
          )}
        </section>

        {result ? (
          <VerdictPanel result={result} />
        ) : (
          <section className="hidden rounded border border-edge bg-panel p-5 shadow-panel lg:block">
            <h2 className="font-mono text-xs uppercase tracking-widest text-muted">Verdict</h2>
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
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && loadFile(e.target.files[0])}
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
        <p className="text-muted">Drop a question block to solve it</p>
        <button
          onClick={onPick}
          className="mt-3 rounded bg-codebg px-3 py-1.5 font-mono text-xs text-muted hover:text-ink"
        >
          or choose a file
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
