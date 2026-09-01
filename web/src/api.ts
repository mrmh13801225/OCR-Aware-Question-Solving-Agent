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

export async function solveBlock(
  apiBase: string,
  imageBase64: string,
  runId: string,
): Promise<SolveOutcome> {
  try {
    const response = await fetch(`${apiBase}/api/v1/blocks/solve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_base64: imageBase64, run_id: runId }),
    });
    if (!response.ok) {
      return { ok: false, error: `API error ${response.status}: ${await response.text()}` };
    }
    return { ok: true, result: (await response.json()) as BlockResult };
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
