import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pkb.cli.main import app
from pkb.ingest.idea import IdeaCardError, IdeaCardImporter
from pkb.storage import RawStorage


runner = CliRunner()


def test_idea_card_preserves_utf8_content_and_optional_fields(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    content = "不要把工具熟练误当成问题解决能力。\n保留原始换行。"

    document = IdeaCardImporter(raw_dir=raw_dir).create(
        content,
        source_url="https://example.test/article",
        tags=["AI", "写作"],
        note="回看时补充一个真实案例。",
    )

    paths = RawStorage(raw_dir).paths_for(document.id)
    metadata = json.loads(paths.metadata_file.read_text(encoding="utf-8"))
    assert document.content == content
    assert document.content_type == "idea"
    assert document.source_type == "manual"
    assert document.source_url == "https://example.test/article"
    assert document.tags == ["AI", "写作"]
    assert document.metadata["note"] == "回看时补充一个真实案例。"
    assert paths.original_file.name == "original.txt"
    assert paths.original_file.read_bytes() == content.encode("utf-8")
    assert paths.extracted_text_file == paths.original_file
    assert metadata["source_url"] == "https://example.test/article"
    assert metadata["tags"] == ["AI", "写作"]
    assert metadata["metadata"]["note"] == "回看时补充一个真实案例。"
    assert "content" not in metadata


def test_same_idea_card_is_idempotent_and_raw_is_not_overwritten(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    importer = IdeaCardImporter(raw_dir=raw_dir)
    first = importer.create(
        "同一张卡片只应有一个 Raw。",
        source_url="https://example.test/source",
        tags=["one", "two"],
        note="first note",
    )
    original_before = Path(first.original_file).read_bytes()
    metadata_before = Path(first.metadata["metadata_file"]).read_bytes()

    second = importer.create(
        "同一张卡片只应有一个 Raw。",
        source_url="https://example.test/source",
        tags=["one", "two"],
        note="first note",
    )

    assert second == first
    assert Path(first.original_file).read_bytes() == original_before
    assert Path(first.metadata["metadata_file"]).read_bytes() == metadata_before
    assert sorted(raw_dir.glob("*/metadata.json")) == [
        raw_dir / first.id / "metadata.json"
    ]


def test_idea_card_rejects_blank_content_without_creating_raw(tmp_path):
    raw_dir = tmp_path / "data" / "raw"

    with pytest.raises(IdeaCardError, match="正文不能为空"):
        IdeaCardImporter(raw_dir=raw_dir).create(" \n\t")

    assert not raw_dir.exists()


def test_cli_add_idea_saves_synthetic_card_in_configured_raw_directory(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PKB_DATA_DIR", str(data_dir))

    result = runner.invoke(
        app,
        [
            "add-idea",
            "合成验收卡片：先完成最小闭环。",
            "--source",
            "https://example.test/cli",
            "--tags",
            "验收,最小切片",
            "--note",
            "CLI 合成资料",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "status: saved" in result.output
    assert "content_type: idea" in result.output
    assert "source_type: manual" in result.output
    assert len(list((data_dir / "raw").glob("*/original.txt"))) == 1
