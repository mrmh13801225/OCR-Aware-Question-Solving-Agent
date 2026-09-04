/** One vocabulary for run states and events — mirrors core.domain.models
 * and core.domain.ports on the server. */

export interface RunEvent {
  run_state: string;
  attempt_index: number;
  detail: string;
}

export const RUN_STATE = {
  OCR: "OCR", // client-added step-zero chip, not a server state
  SOLVE: "SOLVE",
  VERIFY: "VERIFY",
  CORRECT: "CORRECT",
  DONE: "DONE",
  UNRESOLVED: "UNRESOLVED",
  TIMEOUT: "TIMEOUT",
  STREAM_ERROR: "STREAM_ERROR",
} as const;

export type RunStateName = (typeof RUN_STATE)[keyof typeof RUN_STATE];

/** A run ends the moment one of these arrives; the stream closes after. */
export const TERMINAL_RUN_STATES: ReadonlySet<string> = new Set([
  RUN_STATE.DONE,
  RUN_STATE.UNRESOLVED,
]);

/** Events outside any single solve attempt carry this sentinel index. */
export const NON_ATTEMPT_INDEX = -1;
