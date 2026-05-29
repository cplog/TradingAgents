import type { TopicCadence } from "../../api";

const CADENCE_OPTIONS: { value: TopicCadence; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "manual", label: "Manual only" },
];

type Props = {
  value: TopicCadence;
  onChange: (value: TopicCadence) => void;
  disabled?: boolean;
};

export function CadenceSelect({ value, onChange, disabled }: Props) {
  return (
    <select
      className="ui-input"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as TopicCadence)}
      aria-label="Refresh cadence"
    >
      {CADENCE_OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
