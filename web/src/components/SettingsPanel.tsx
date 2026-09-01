import type { ProviderInfo } from "../api";

export interface Overrides {
  ocr_provider: string;
  reasoning_provider: string;
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
