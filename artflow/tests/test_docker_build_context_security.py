"""Guard against shipping production runtime state in ArtFlow Docker images.

No external systems or data files are read: validate build rules only.
"""

from pathlib import Path


ARTFLOW = Path(__file__).resolve().parents[1]


def test_dockerignore_excludes_runtime_state() -> None:
    entries = {
        line.strip()
        for line in (ARTFLOW / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    # These are production bind mounts, never reproducible source artifacts.
    assert "data/" in entries
    assert "static/upload" in entries
    assert ".env" in entries
    assert ".env.*" in entries

    # A negation could silently re-add sensitive files to the build context.
    assert not any(
        entry.startswith("!data") or entry.startswith("!static/upload")
        for entry in entries
    )


def test_image_build_fails_closed_on_baked_runtime_state() -> None:
    dockerfile = (ARTFLOW / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . ." in dockerfile
    assert "RUN test ! -e /app/data" in dockerfile
    assert "&& test ! -e /app/static/upload" in dockerfile
    assert "&& test ! -e /app/.env" in dockerfile
    assert "./data:/app/data" in (ARTFLOW / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
