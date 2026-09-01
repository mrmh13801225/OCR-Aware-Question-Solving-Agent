import type { BlockResult } from "../api";
import type { RunEvent } from "../runStream";
import { hasChanges, wordDiff } from "../wordDiff";

export interface TimedRunEvent extends RunEvent {
  arrivedAt: number;
}

const STATE_LABELS: Record<string, string> = {
  OCR: "ocr extract",
  SOLVE: "solve",
  VERIFY: "verify",
  CORRECT: "correct",
  DONE: "done",
  UNRESOLVED: "unresolved",
};

export function RetryLoopPanel({
  events,
  running,
  result,
}: {
  events: TimedRunEvent[];
  running: boolean;
  result: BlockResult | null;
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
          <TraceNode
            key={index}
            event={event}
            runStart={events[0]?.arrivedAt ?? 0}
            previousText={previousQuestionText(events, index)}
            result={index === events.length - 1 ? result : null}
            isTerminal={index === events.length - 1 && !running}
          />
        ))}
      </ol>
    </section>
  );
}

/** The question text a correction edited: the SOLVE event's detail before this node. */
function previousQuestionText(events: TimedRunEvent[], index: number): string | null {
  for (let i = index - 1; i >= 0; i--) {
    if (events[i].run_state === "SOLVE") return events[i].detail;
  }
  return null;
}

function TraceNode({
  event,
  runStart,
  previousText,
  result,
  isTerminal,
}: {
  event: TimedRunEvent;
  runStart: number;
  previousText: string | null;
  result: BlockResult | null;
  isTerminal: boolean;
}) {
  const label = STATE_LABELS[event.run_state] ?? event.run_state.toLowerCase();

  return (
    <li className="relative">
      <span className={`absolute -left-[27px] top-1.5 h-2.5 w-2.5 rounded-full ${dotColor(event.run_state)}`} />
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-xs uppercase tracking-wide text-ink">{label}</span>
        {event.attempt_index >= 0 && (
          <span className="font-mono text-[10px] text-muted">·{event.attempt_index}</span>
        )}
        <span className="ml-auto font-mono text-[10px] text-muted">{arrivalLabel(event, runStart)}</span>
      </div>
      <EventBody event={event} previousText={previousText} result={result} isTerminal={isTerminal} />
    </li>
  );
}

function dotColor(state: string): string {
  if (state === "DONE") return "bg-verified";
  if (state === "UNRESOLVED") return "bg-suspect";
  if (state === "CORRECT") return "bg-proof";
  return "bg-edge";
}

function arrivalLabel(event: TimedRunEvent, runStart: number): string {
  if (!runStart) return "";
  return `+${((event.arrivedAt - runStart) / 1000).toFixed(1)}s`;
}

function EventBody({
  event,
  previousText,
  result,
  isTerminal,
}: {
  event: TimedRunEvent;
  previousText: string | null;
  result: BlockResult | null;
  isTerminal: boolean;
}) {
  if (event.run_state === "OCR") {
    return (
      <div className="mt-1 inline-flex items-center gap-1.5 rounded bg-codebg px-2 py-1">
        <DocumentIcon />
        <span dir="rtl" className="font-farsi text-xs text-ink">
          {event.detail}
        </span>
      </div>
    );
  }
  if (event.run_state === "VERIFY") {
    return <p className="mt-0.5 font-mono text-[11px] text-muted">answered {event.detail}</p>;
  }
  if (event.run_state === "CORRECT") {
    return (
      <div className="mt-1">
        <span className="inline-flex items-center gap-1 rounded bg-proof/10 px-2 py-0.5 font-mono text-[10px] text-proof">
          <XMark /> no option match
        </span>
        {previousText && <DiffText previous={previousText} current={event.detail} rtl />}
      </div>
    );
  }
  if (isTerminal && result && (event.run_state === "DONE" || event.run_state === "UNRESOLVED")) {
    return (
      <div className="mt-1">
        <DiffText previous={previousText ?? event.detail} current={result.question_text} rtl />
        <span className="stamp-rotate mt-2 inline-block rounded border-2 px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest text-proof border-proof">
          {stampLabel(result)}
        </span>
      </div>
    );
  }
  return event.detail ? (
    <p dir="auto" className="mt-0.5 line-clamp-2 font-mono text-[11px] text-muted">
      {event.detail}
    </p>
  ) : null;
}

function stampLabel(result: BlockResult): string {
  if (result.unresolved) return "UNRESOLVED";
  if (result.changed) return `CHANGED · ${result.attempts - 1}`;
  return "UNCHANGED";
}

/**
 * Red-ink proofreading marks: struck-through original, red replacement.
 * Renders plain text when the two sides are identical or a side is missing.
 */
function DiffText({
  previous,
  current,
  rtl,
}: {
  previous: string;
  current: string;
  rtl?: boolean;
}) {
  const changes = wordDiff(previous, current);
  if (!hasChanges(changes)) {
    return (
      <p dir={rtl ? "rtl" : "auto"} className="mt-0.5 line-clamp-2 font-farsi text-xs text-muted">
        {current}
      </p>
    );
  }
  return (
    <p dir={rtl ? "rtl" : "auto"} className="mt-1 font-farsi text-xs leading-loose text-ink">
      {changes.map((change, index) => {
        if (change.type === "same") {
          return <span key={index}>{change.text} </span>;
        }
        if (change.type === "removed") {
          return (
            <span key={index} className="text-proof line-through opacity-80">
              {change.text}{" "}
            </span>
          );
        }
        return (
          <span key={index} className="font-bold text-proof">
            {change.text}{" "}
          </span>
        );
      })}
    </p>
  );
}

function DocumentIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-3 w-3 text-muted" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}

function XMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="3">
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}
