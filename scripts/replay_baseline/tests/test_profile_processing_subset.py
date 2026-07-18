from __future__ import annotations

import json

from replay_baseline import profile_processing_subset as profile


def test_profiles_bounded_preserved_subset_without_db(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "b.log").write_text(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "ready"\ninvalid\n',
        encoding="utf-8",
    )
    (logs / "a.log").write_text(
        'L 01/02/2024 - 03:04:06: "Bob<3><STEAM_1:3><TERRORIST>" say "go"\n',
        encoding="utf-8",
    )
    output = tmp_path / "profile"

    assert profile.main([str(logs), "--max-files", "1", "--backends", "python", "native", "--output-dir", str(output)]) == 0

    summary = json.loads((output / "processing-profile.json").read_text(encoding="utf-8"))
    assert summary["db_touched"] is False
    assert summary["input_files"] == [str(logs / "a.log")]
    assert [(item["backend"], item["parsed"], item["parse_errors"]) for item in summary["results"]] == [
        ("python", 1, 0),
        ("native", 1, 0),
    ]
    assert (output / "processing-python.pstats").is_file()
    assert (output / "processing-native-top-30.txt").is_file()
