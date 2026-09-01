export interface RunEvent {
  run_state: string;
  attempt_index: number;
  detail: string;
}

export type EventSink = (event: RunEvent) => void;

export function randomRunId(): string {
  return crypto.randomUUID();
}

/**
 * Stream-first: opens the SSE stream for runId immediately (the server
 * accepts unknown run ids and follows), invoking sink for every event
 * until the run terminates or the server sends its TIMEOUT event.
 * EventSource reconnects on transient drops; the sink ignores replays by
 * design (each event appends a node, and a reconnect replays the buffer —
 * acceptable for a dev-server app).
 */
export function followRun(apiBase: string, runId: string, sink: EventSink): () => void {
  const source = new EventSource(`${apiBase}/api/v1/blocks/${runId}/stream`);
  let finished = false;
  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as RunEvent;
      if (event.run_state === "TIMEOUT") {
        finished = true;
        source.close();
        return;
      }
      sink(event);
      if (event.run_state === "DONE" || event.run_state === "UNRESOLVED") {
        finished = true;
        // keep the stream open briefly to drain the buffer, then close
        setTimeout(() => source.close(), 300);
      }
    } catch {
      // malformed frame: skip, not fatal
    }
  };
  source.onerror = () => {
    if (finished) return; // expected close after terminal event
    sink({ run_state: "STREAM_ERROR", attempt_index: -1, detail: "stream disconnected" });
  };
  return () => source.close();
}
