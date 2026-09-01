function ShamsaMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-7 w-7 text-suspect" aria-hidden="true">
      <g fill="currentColor">
        <path d="M12 2l1.8 6.2L20 6.4l-4.4 4.7L22 12l-6.4.9L20 17.6l-6.2-1.8L12 22l-1.8-6.2L4 17.6l4.4-4.7L2 12l6.4-.9L4 6.4l6.2 1.8z" />
      </g>
    </svg>
  );
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center gap-3 border-b border-edge px-5 py-3">
        <ShamsaMark />
        <span className="font-mono text-sm text-muted">OCR-Aware Question Solving Agent</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="font-mono text-xs text-muted">OCR: —</span>
          <span className="font-mono text-xs text-muted">Model: —</span>
          <button
            className="rounded bg-suspect px-4 py-1.5 text-sm font-medium text-bg disabled:opacity-40"
            disabled
          >
            Solve
          </button>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center p-8">
        <div className="rounded border border-dashed border-edge p-12 text-center">
          <p className="text-muted">Drop a question block to solve it</p>
        </div>
      </main>
    </div>
  );
}
