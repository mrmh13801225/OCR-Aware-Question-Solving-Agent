export interface BlockResult {
  answer: string;
  question_text: string;
  changed: boolean;
  original_ocr_text: string;
  unresolved: boolean;
  attempts: number;
}

export interface SolveOutcome {
  ok: boolean;
  result?: BlockResult;
  error?: string;
}

export interface SolveOverrides {
  ocr_provider?: string | null;
  reasoning_provider?: string | null;
  solve_mode?: string | null;
}

/** The solve modes the server accepts — mirrors config.SOLVE_MODES. */
export const SOLVE_MODES = ["image_grounded", "text_only"] as const;

/** The API surface this app talks to — one home for every path literal. */
export const API_ENDPOINTS = {
  solve: "/api/v1/blocks/solve",
  batch: "/api/v1/blocks/batch",
  providers: "/api/v1/providers",
  stream: (runId: string) => `/api/v1/blocks/${runId}/stream`,
} as const;

interface ApiOutcome<T> {
  ok: boolean;
  result?: T;
  results?: T[];
  error?: string;
}

/** Shared fetch-and-classify: the try/ok/catch shape solveBlock and
 * solveBatch both used to repeat. */
async function request<T>(
  path: string,
  body: unknown,
  transform: (payload: unknown) => ApiOutcome<T>,
): Promise<ApiOutcome<T>> {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      return { ok: false, error: `API error ${response.status}: ${await response.text()}` };
    }
    return transform(await response.json());
  } catch (err) {
    return { ok: false, error: `cannot reach the API: ${(err as Error).message}` };
  }
}

export async function solveBlock(
  apiBase: string,
  imageBase64: string,
  runId: string,
  overrides: SolveOverrides = {},
): Promise<SolveOutcome> {
  return request<BlockResult>(
    `${apiBase}${API_ENDPOINTS.solve}`,
    { image_base64: imageBase64, run_id: runId, ...overrides },
    (payload) => ({ ok: true, result: payload as BlockResult }),
  );
}

export async function solveBatch(
  apiBase: string,
  images: { id: string; imageBase64: string }[],
  overrides: SolveOverrides = {},
): Promise<{ ok: boolean; results?: BlockResult[]; error?: string }> {
  return request<BlockResult>(
    `${apiBase}${API_ENDPOINTS.batch}`,
    {
      blocks: images.map((image) => ({
        image_base64: image.imageBase64,
        run_id: `web-batch-${image.id}`,
        ...overrides,
      })),
    },
    (payload) => ({ ok: true, results: (payload as { results: BlockResult[] }).results }),
  );
}

export interface ProviderInfo {
  ocr: string[];
  reasoning: string[];
  models: Record<string, string>;
  configured: { ocr: string; reasoning: string };
}

export async function fetchProviders(apiBase: string): Promise<ProviderInfo | null> {
  try {
    const response = await fetch(`${apiBase}${API_ENDPOINTS.providers}`);
    if (!response.ok) return null;
    return (await response.json()) as ProviderInfo;
  } catch {
    return null;
  }
}

/** The base64 payload of a data: URL — the FileReader result's tail. */
export function base64FromDataUrl(dataUrl: string): string {
  return dataUrl.split(",")[1];
}
