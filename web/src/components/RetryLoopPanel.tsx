import type { RunEvent } from "../runStream";

const STATE_LABELS: Record<string, string> = {
  SOLVE: "solve",
  VERIFY: "verify",
  CORRECT: "correct",
  DONE: "done",
  UNRESOLVED: "unresolved",
};

export function RetryLoopPanel({
  events,
  running,
}: {
  events: RunEvent[];
  running: boolean;
}) {
  return (
    <section className="flex h-full flex-col gap-4 rounded border border-edge bg-panel p-5 shadow-panel">
      <h2 className="font-mono text-xs uppercase tracking-widest text-muted">Retry loop</h2>
      {events.length === 0 && !running && (
        <p className="text-sm text-muted">The live trace appears here during a run.</p>
      )}
      {running && events.length === 0 && (
        <p className="animate-pulse text-sm text-muted">Waiting for the loop…</p>
      )}
      <ol className="relative ml-3 flex flex-col gap-4 border-l border-edge pl-5">
        {events.map((event, index) => (
          <TraceNode key={index} event={event} last={index === events.length - 1 && !running} />
        ))}
      </ol>
    </section>
  );
}

function TraceNode({ event, last }: { event: RunEvent; last: boolean }) {
  const label = STATE_LABELS[event.run_state] ?? event.run_state.toLowerCase();
  const terminal = event.run_state === "DONE" || event.run_state === "UNRESOLVED";
  const matched = event.run_state === "DONE";
  const failed = event.run_state === "CORRECT" || event.run_state === "UNRESOLVED";
  const dotColor = terminal ? (matched ? "bg-verified" : "bg-suspect") : failed ? "bg-proof" : "bg-edge";
  return (
    <li className="relative">
      <span className={`absolute -left-[27px] top-1.5 h-2.5 w-2.5 rounded-full ${dotColor}`} />
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-xs uppercase tracking-wide text-ink">{label}</span>
        {event.attempt_index >= 0 && (
          <span className="font-mono text-[10px] text-muted">·{event.attempt_index}</span>
        )}
      </div>
      {event.detail && (
        <p
          dir="auto"
          className="mt-0.5 line-clamp-2 font-mono text-[11px] text-muted"
        >
          {event.detail}
        </p>
      )}
      {last && (
        <span
          className={`mt-2 inline-block -rotate-3 rounded border-2 px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest ${
            matched ? "border-verified text-verified" : "border-suspect text-suspect"
          }`}
        >
          {matched ? "MATCHED" : "UNRESOLVED"}
        </span>
      )}
    </li>
  );
}
