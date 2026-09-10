from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_video_generation_uses_duration_slider_bound_to_model_options() -> None:
    source = (ROOT / "webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")

    assert 'type="range"' in source
    assert 'aria-label="Длительность видео"' in source
    assert 'max={Math.max(0, durations.length - 1)}' in source
    assert 'const nextDuration = durations[Number(event.target.value)]' in source
    assert 'onChange({ duration: nextDuration })' in source


def test_duration_slider_keeps_model_minimum_and_maximum_visible() -> None:
    source = (ROOT / "webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")

    assert '<span>{durations[0]} сек</span>' in source
    assert '<span>{durations[durations.length - 1]} сек</span>' in source
