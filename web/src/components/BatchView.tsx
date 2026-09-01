import { verdictOf } from "./VerdictPanel";
import type { BlockResult } from "../api";

export interface BatchItem {
  name: string;
  imageBase64?: string;
  result?: BlockResult;
  error?: string;
}

export function BatchView({
  items,
  onOpen,
}: {
  items: BatchItem[];
  onOpen: (name: string) => void;
}) {
  return (
    <section className="flex h-full flex-col gap-3 rounded border border-edge bg-panel p-5 shadow-panel">
      <h2 className="font-mono text-xs uppercase tracking-widest text-muted">
        Batch — {items.length} blocks
      </h2>
      <div className="grid flex-1 auto-rows-min grid-cols-2 gap-3 overflow-auto xl:grid-cols-3">
        {items.map((item) => (
          <BatchCard key={item.name} item={item} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}

function BatchCard({ item, onOpen }: { item: BatchItem; onOpen: (name: string) => void }) {
  if (item.error || !item.result) {
    return (
      <button
        onClick={() => onOpen(item.name)}
        className="rounded border border-proof p-3 text-left"
      >
        <p className="font-mono text-xs text-proof">{item.name}</p>
        <p className="mt-1 text-[11px] text-muted">failed — click to inspect</p>
      </button>
    );
  }
  const verdict = verdictOf(item.result);
  const color =
    verdict === "UNCHANGED" ? "text-verified" : verdict === "CHANGED" ? "text-proof" : "text-suspect";
  return (
    <button
      onClick={() => onOpen(item.name)}
      className="rounded border border-edge p-3 text-left hover:border-suspect"
    >
      <p className="font-mono text-[11px] text-muted">{item.name}</p>
      <div className="mt-1 flex items-baseline justify-between">
        <span className={`text-2xl font-bold ${color}`}>{item.result.answer}</span>
        <span className={`font-mono text-[10px] tracking-widest ${color}`}>{verdict}</span>
      </div>
      <p className="mt-1 font-mono text-[10px] text-muted">{item.result.attempts} attempts</p>
    </button>
  );
}
