import type { BlockResult } from "../api";
import { RUN_STATE, TERMINAL_RUN_STATES } from "../runStates";
import type { RunEvent } from "../runStates";
import { DiffWords } from "./DiffWords";

export interface TimedRunEvent extends RunEvent {
  arrivedAt: number;
}

const STATE_LABELS: Record<string, string> = {
  [RUN_STATE.OCR]: "ocr extract",
  [RUN_STATE.SOLVE]: "solve",
  [RUN_STATE.VERIFY]: "verify",
  [RUN_STATE.CORRECT]: "correct",
  [RUN_STATE.DONE]: "done",
  [RUN_STATE.UNRESOLVED]: "unresolved",
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
    if (events[i].run_state === RUN_STATE.SOLVE) return events[i].detail;
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
  if (state === RUN_STATE.DONE) return "bg-verified";
  if (state === RUN_STATE.UNRESOLVED) return "bg-suspect";
  if (state === RUN_STATE.CORRECT) return "bg-proof";
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
  if (event.run_state === RUN_STATE.OCR) {
    return (
      <div className="mt-1 inline-flex items-center gap-1.5 rounded bg-codebg px-2 py-1">
        <DocumentIcon />
        <span dir="rtl" className="font-farsi text-xs text-ink">
          {event.detail}
        </span>
      </div>
    );
  }
  if (event.run_state === RUN_STATE.VERIFY) {
    return <p className="mt-0.5 font-mono text-[11px] text-muted">answered {event.detail}</p>;
  }
  if (event.run_state === RUN_STATE.CORRECT) {
    return (
      <div className="mt-1">
        <span className="inline-flex items-center gap-1 rounded bg-proof/10 px-2 py-0.5 font-mono text-[10px] text-proof">
          <XMark /> no option match
        </span>
        {previousText && (
          <DiffWords
            previous={previousText}
            current={event.detail}
            rtl
            className="mt-1 font-farsi text-xs leading-loose text-ink"
            removedClassName="text-proof line-through opacity-80"
            addedClassName="font-bold text-proof"
          />
        )}
      </div>
    );
  }
  if (isTerminal && result && TERMINAL_RUN_STATES.has(event.run_state)) {
    return (
      <div className="mt-1">
        <DiffWords
          previous={previousText ?? event.detail}
          current={result.question_text}
          rtl
          className="mt-1 font-farsi text-xs leading-loose text-ink"
          removedClassName="text-proof line-through opacity-80"
          addedClassName="font-bold text-proof"
        />
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
  if (result.changed) return `CHANGED · ${correctionCount(result)}`;
  return "UNCHANGED";
}

/** Corrections that ran: solve attempts minus the initial solve, floored at
 * zero for the honest unresolved-with-zero-attempts result. */
function correctionCount(result: BlockResult): number {
  return Math.max(0, result.attempts - 1);
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
