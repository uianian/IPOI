from __future__ import annotations

import json
from pathlib import Path

from service.real_runner import progress_percent, read_batch_progress


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_read_batch_progress_sums_shards(tmp_path: Path) -> None:
    write(tmp_path / "status.json", {"stage": "PAGE_PARSING", "pagesTotal": 10})
    write(tmp_path / "shard0.json", {"stage": "PAGE_PARSING", "done": 4, "total": 5})
    write(tmp_path / "shard1.json", {"stage": "PAGE_PARSING", "done": 2, "total": 5})
    assert read_batch_progress(tmp_path) == {
        "stage": "PAGE_PARSING", "pagesDone": 6, "pagesTotal": 10
    }


def test_model_loading_and_stage_percentages(tmp_path: Path) -> None:
    write(tmp_path / "status.json", {"stage": "PAGE_PARSING", "pagesTotal": 8})
    write(tmp_path / "shard0.json", {"stage": "MODEL_LOADING", "done": 0, "total": 4})
    write(tmp_path / "shard1.json", {"stage": "MODEL_LOADING", "done": 0, "total": 4})
    assert read_batch_progress(tmp_path)["stage"] == "MODEL_LOADING"
    assert progress_percent("MODEL_LOADING", 0, 8) == 5
    assert progress_percent("PAGE_PARSING", 4, 8) == 46
    assert progress_percent("PAGE_PARSING", 8, 8) == 88
    assert progress_percent("MERGING", 8, 8) == 92
    assert progress_percent("QA", 8, 8) == 96
    assert progress_percent("COMPLETE", 8, 8) == 98


def test_corrupt_or_partial_shard_is_ignored(tmp_path: Path) -> None:
    write(tmp_path / "status.json", {"stage": "PAGE_PARSING", "pagesTotal": 3})
    (tmp_path / "shard0.json").write_text("{", encoding="utf-8")
    write(tmp_path / "shard1.json", {"stage": "PAGE_PARSING", "done": 2, "total": 3})
    progress = read_batch_progress(tmp_path)
    assert progress["pagesDone"] == 2
    assert progress["pagesTotal"] == 3
