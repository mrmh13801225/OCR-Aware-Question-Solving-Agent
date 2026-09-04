import { SOLVE_MODES, type ProviderInfo } from "../api";

export interface Overrides {
  ocr_provider: string;
  reasoning_provider: string;
  solve_mode: string;
}

export function SettingsPanel({
  providers,
  overrides,
  onChange,
}: {
  providers: ProviderInfo | null;
  overrides: Overrides;
  onChange: (next: Overrides) => void;
}) {
  return (
    <div className="flex flex-col gap-3 rounded border border-edge bg-panel p-4">
      <h3 className="font-mono text-xs uppercase tracking-widest text-muted">
        Providers (per-run override)
      </h3>
      <Picker
        label="OCR"
        value={overrides.ocr_provider}
        options={providers?.ocr ?? []}
        configured={providers?.configured.ocr}
        onSelect={(value) => onChange({ ...overrides, ocr_provider: value })}
      />
      <Picker
        label="Model"
        value={overrides.reasoning_provider}
        options={providers?.reasoning ?? []}
        configured={providers?.configured.reasoning}
        onSelect={(value) => onChange({ ...overrides, reasoning_provider: value })}
      />
      <label className="flex items-center gap-2 font-mono text-xs">
        <span className="w-12 text-muted">Solve</span>
        <select
          value={overrides.solve_mode}
          onChange={(e) => onChange({ ...overrides, solve_mode: e.target.value })}
          className="flex-1 rounded bg-codebg px-2 py-1 text-ink"
          aria-label="Solve mode"
        >
          <option value="">image_grounded (default)</option>
          {SOLVE_MODES.filter((mode) => mode !== "image_grounded").map((mode) => (
            <option key={mode} value={mode}>
              {mode}
            </option>
          ))}
        </select>
      </label>
      <p className="text-[11px] leading-relaxed text-muted">
        text_only: the solver judges the OCR text alone — the image is sent only when a
        correction or transcription re-reads it.
      </p>
    </div>
  );
}

function Picker({
  label,
  value,
  options,
  configured,
  onSelect,
}: {
  label: string;
  value: string;
  options: string[];
  configured?: string;
  onSelect: (value: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 font-mono text-xs">
      <span className="w-12 text-muted">{label}</span>
      <select
        value={value}
        onChange={(e) => onSelect(e.target.value)}
        className="flex-1 rounded bg-codebg px-2 py-1 text-ink"
      >
        <option value="">default{configured ? ` (${configured})` : ""}</option>
        {options.map((name) => (
          <option key={name} value={name}>
            {name}
            {name === configured ? " ●" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
