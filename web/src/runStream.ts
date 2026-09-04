import { NON_ATTEMPT_INDEX, RUN_STATE, TERMINAL_RUN_STATES } from "./runStates";
import type { RunEvent } from "./runStates";

export type { RunEvent } from "./runStates";

export type EventSink = (event: RunEvent) => void;

export function randomRunId(): string {
  return crypto.randomUUID();
}

/** Milliseconds the stream stays open after a terminal event, draining the
 * buffer before the client closes it. */
const DRAIN_CLOSE_MS = 300;

/** Stream-first: opens the SSE stream for runId immediately (the server
 * accepts unknown run ids and follows), invoking sink for every event
 * until the run terminates or the server sends its TIMEOUT event.
 * EventSource reconnects on transient drops; the sink ignores replays by
 * design (each event appends a node, and a reconnect replays the buffer —
 * acceptable for a dev-server app). */
export function followRun(apiBase: string, runId: string, sink: EventSink): () => void {
  const source = new EventSource(`${apiBase}/api/v1/blocks/${runId}/stream`);
  let finished = false;
  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as RunEvent;
      if (event.run_state === RUN_STATE.TIMEOUT) {
        finished = true;
        source.close();
        return;
      }
      sink(event);
      if (TERMINAL_RUN_STATES.has(event.run_state)) {
        finished = true;
        // keep the stream open briefly to drain the buffer, then close
        setTimeout(() => source.close(), DRAIN_CLOSE_MS);
      }
    } catch {
      // malformed frame: skip, not fatal
    }
  };
  source.onerror = () => {
    if (finished) return; // expected close after terminal event
    sink({
      run_state: RUN_STATE.STREAM_ERROR,
      attempt_index: NON_ATTEMPT_INDEX,
      detail: "stream disconnected",
    });
  };
  return () => source.close();
}
