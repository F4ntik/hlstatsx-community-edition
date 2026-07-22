from pathlib import Path


def test_worker_image_packages_canonical_geoip_backfill_command() -> None:
    repository = Path(__file__).resolve().parents[3]
    dockerfile = (
        repository / "scripts" / "replay_baseline" / "comparison" / "python" / "Dockerfile.worker"
    ).read_text(encoding="utf-8")

    assert "ENV PYTHONPATH=/app/scripts" in dockerfile
    assert "COPY scripts/hlstats_awards_py /app/scripts/hlstats_awards_py" in dockerfile
    assert "pip install --no-cache-dir /app/scripts/hlx_core" in dockerfile
    assert "pip install --no-cache-dir geoip2" in dockerfile
