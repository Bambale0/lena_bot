from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIDER = ROOT / "webapp/src/components/ui/duration-slider.tsx"
GENERATION = ROOT / "webapp/src/features/generation-screen.tsx"
REMIX = ROOT / "webapp/src/features/feed-remix-runner.tsx"


def test_duration_slider_uses_only_provider_supported_values():
    src = SLIDER.read_text(encoding="utf-8")
    assert 'type="range"' in src
    assert "max={options.length - 1}" in src
    assert "const next = options[index]" in src
    assert "if (next != null) onChange(next)" in src
    assert 'aria-valuetext={`${selected} секунд`}' in src


def test_canonical_video_generation_uses_duration_slider():
    src = GENERATION.read_text(encoding="utf-8")
    assert 'import { DurationSlider } from "@/components/ui/duration-slider"' in src
    assert "values={durations}" in src
    assert "value={draft.duration}" in src
    assert "onChange={(duration) => onChange({ duration })}" in src
    assert '<LabeledChips label="Длительность">' not in src


def test_feed_remix_uses_same_duration_slider():
    src = REMIX.read_text(encoding="utf-8")
    assert 'import { DurationSlider } from "@/components/ui/duration-slider"' in src
    assert "values={durations}" in src
    assert "value={duration}" in src
    assert "onChange={setDuration}" in src
