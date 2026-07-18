from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from heatmap_projection_calibrate import parse_args, write_preview


@pytest.mark.parametrize("scale", ["0", "-1", "nan"])
def test_calibration_rejects_non_positive_or_non_finite_scale(scale: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--configfile",
                "hlstats.conf",
                "--game",
                "cstrike",
                "--map",
                "de_dust2",
                "--scale",
                scale,
            ]
        )


def test_calibration_apply_requires_explicit_runtime_gate() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--configfile",
                "hlstats.conf",
                "--game",
                "cstrike",
                "--map",
                "de_dust2",
                "--apply",
            ]
        )


def test_calibration_preview_normalizes_interactive_transform_values() -> None:
    source = Path("scripts/heatmap_projection_calibrate.py").read_text(
        encoding="utf-8"
    )

    assert "function normalizeRotation(value)" in source
    assert "return rounded < 0 ? rounded + 4 : rounded;" in source
    assert "function normalizeScale(value)" in source
    assert "scale: normalizeScale(document.getElementById('scale_n').value)" in source
    assert "function rotatePoint(x, y, steps)" in source
    assert "function unrotatePoint(x, y, steps)" in source
    assert "const rotated = rotatePoint(x, y, c.rotate);" in source


def test_calibration_preview_emits_quarter_turn_helpers(tmp_path: Path) -> None:
    output = tmp_path / "preview.html"
    config = SimpleNamespace(
        xoffset=0,
        yoffset=0,
        scale=1.0,
        flipx=False,
        flipy=False,
        rotate=0,
        cropx1=0,
        cropy1=0,
        cropx2=0,
        cropy2=0,
        game="cstrike",
        code="cstrike",
        map_name="de_dust2",
    )

    write_preview(
        output,
        image_path=Path("de_dust2.jpg"),
        image_size_value=(100, 80),
        points=[],
        config=config,
    )

    html = output.read_text(encoding="utf-8")
    assert "function rotatePoint(x, y, steps)" in html
    assert "return {x: -y, y: x};" in html
    assert "return {x: -x, y: -y};" in html
    assert "return {x: y, y: -x};" in html
    assert "function unrotatePoint(x, y, steps)" in html
