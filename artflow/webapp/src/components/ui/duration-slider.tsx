interface DurationSliderProps {
  values: number[];
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  label?: string;
  className?: string;
}

function normalizedDurations(values: number[]): number[] {
  return [...new Set(values.map(Number).filter((value) => Number.isFinite(value) && value > 0))].sort((a, b) => a - b);
}

export function DurationSlider({
  values,
  value,
  onChange,
  disabled = false,
  label = "Длительность",
  className = "",
}: DurationSliderProps) {
  const options = normalizedDurations(values);
  if (!options.length) return null;

  const exactIndex = options.indexOf(Number(value));
  const selectedIndex = exactIndex >= 0 ? exactIndex : 0;
  const selected = options[selectedIndex];
  const hasChoice = options.length > 1;

  return (
    <div className={`apix-duration-control grid min-w-0 gap-2 ${className}`.trim()}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium">{label}</p>
        <span className="min-w-[4.5rem] rounded-lg border border-primary/25 bg-primary/10 px-2.5 py-1 text-center text-xs font-semibold text-primary">
          {selected} сек
        </span>
      </div>

      {hasChoice ? (
        <>
          <input
            type="range"
            min={0}
            max={options.length - 1}
            step={1}
            value={selectedIndex}
            disabled={disabled}
            aria-label={label}
            aria-valuetext={`${selected} секунд`}
            className="apix-duration-slider apix-focus-ring h-7 w-full cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
            onChange={(event) => {
              const index = Number(event.target.value);
              const next = options[index];
              if (next != null) onChange(next);
            }}
          />
          <div className="flex items-center justify-between text-[10px] font-medium text-muted-foreground">
            <span>{options[0]} сек</span>
            <span>{options[options.length - 1]} сек</span>
          </div>
        </>
      ) : (
        <p className="text-[11px] text-muted-foreground">У этой модели длительность фиксирована.</p>
      )}
    </div>
  );
}
