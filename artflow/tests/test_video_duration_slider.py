from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_video_generation_uses_duration_slider_bound_to_model_options() -> None:
    source = (ROOT / "webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")

    assert 'type="range"' in source
    assert 'aria-label="Длительность видео"' in source
    assert 'max={Math.max(0, durations.length - 1)}' in source
    assert 'const nextDuration = durations[Number(event.target.value)]' in source
    assert 'onChange({ duration: nextDuration })' in source


def test_duration_slider_shows_clickable_supported_duration_ticks() -> None:
    source = (ROOT / "webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")

    assert 'durations.map((duration) =>' in source
    assert 'onClick={() => onChange({ duration })}' in source
    assert '{duration} сек' in source
