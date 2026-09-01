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
}

export async function solveBlock(
  apiBase: string,
  imageBase64: string,
  runId: string,
  overrides: SolveOverrides = {},
): Promise<SolveOutcome> {
  try {
    const response = await fetch(`${apiBase}/api/v1/blocks/solve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_base64: imageBase64, run_id: runId, ...overrides }),
    });
    if (!response.ok) {
      return { ok: false, error: `API error ${response.status}: ${await response.text()}` };
    }
    return { ok: true, result: (await response.json()) as BlockResult };
  } catch (err) {
    return { ok: false, error: `cannot reach the API: ${(err as Error).message}` };
  }
}

export async function solveBatch(
  apiBase: string,
  images: { id: string; imageBase64: string }[],
  overrides: SolveOverrides = {},
): Promise<{ ok: boolean; results?: BlockResult[]; error?: string }> {
  try {
    const response = await fetch(`${apiBase}/api/v1/blocks/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        blocks: images.map((image) => ({
          image_base64: image.imageBase64,
          run_id: `web-batch-${image.id}`,
          ...overrides,
        })),
      }),
    });
    if (!response.ok) {
      return { ok: false, error: `API error ${response.status}: ${await response.text()}` };
    }
    const body = (await response.json()) as { results: BlockResult[] };
    return { ok: true, results: body.results };
  } catch (err) {
    return { ok: false, error: `cannot reach the API: ${(err as Error).message}` };
  }
}

export interface ProviderInfo {
  ocr: string[];
  reasoning: string[];
  models: Record<string, string>;
  configured: { ocr: string; reasoning: string };
}

export async function fetchProviders(apiBase: string): Promise<ProviderInfo | null> {
  try {
    const response = await fetch(`${apiBase}/api/v1/providers`);
    if (!response.ok) return null;
    return (await response.json()) as ProviderInfo;
  } catch {
    return null;
  }
}
