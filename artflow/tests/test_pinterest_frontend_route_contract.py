"""Prevent reintroducing the unmounted Pinterest trend endpoint.

These checks inspect code contracts only; they never launch paid requests.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_trend_runner_redirects_pinterest_to_dedicated_service() -> None:
    source = (ROOT / "webapp/src/features/trend-runner.tsx").read_text(encoding="utf-8")
    assert "isPinterestServiceTrend(next)" in source
    assert "openPinterestService();" in source
    assert "function PinterestTrendFlow" not in source
    assert "pinterest-run" not in source


def test_only_real_pinterest_service_owns_paid_route() -> None:
    service = (ROOT / "webapp/src/features/pinterest-service-runner.tsx").read_text(
        encoding="utf-8"
    )
    backend = (ROOT / "api/pinterest_service_routes.py").read_text(encoding="utf-8")
    assert '"/services/pinterest/upload"' in service
    assert '"/services/pinterest/run"' in service
    assert '@router.post("/run", status_code=202)' in backend
    assert "confirmed is not True" in backend
