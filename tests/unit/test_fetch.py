import json

import pytest

from genericfinder.ingest.fetch import (
    Manifest,
    backoff_delay,
    file_stem,
    pick_ext,
    read_sources,
    retry_after_seconds,
    slug,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Hello World", "hello-world"),
        ("ABC_123", "abc-123"),
        ("---Python---", "python"),
        ("", "file"),
    ],
)
def test_slug(value, expected):
    assert slug(value) == expected


def test_file_stem_is_stable():
    url = "https://example.com/report.pdf"
    assert file_stem(url) == file_stem(url)


def test_file_stem_differs_for_different_urls():
    assert file_stem("https://example.com/a.pdf") != file_stem("https://example.com/b.pdf")


@pytest.mark.parametrize(
    ("url", "content_type", "expected"),
    [
        ("https://example.com/file.pdf", "application/pdf", ".pdf"),
        ("https://example.com/file", "application/pdf", ".pdf"),
        ("https://example.com/file", "text/html; charset=utf-8", ".html"),
    ],
)
def test_pick_ext(url, content_type, expected):
    assert pick_ext(url, content_type) == expected


def test_backoff_delay_stays_within_limit(monkeypatch):
    monkeypatch.setattr("genericfinder.ingest.fetch.random.uniform", lambda a, b: b)
    assert backoff_delay(2, base=1, cap=60) == 4


def test_backoff_delay_respects_cap(monkeypatch):
    monkeypatch.setattr("genericfinder.ingest.fetch.random.uniform", lambda a, b: b)
    assert backoff_delay(10, base=1, cap=5) == 5


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30", 30.0),
        ("", None),
        ("not-a-date", None),
    ],
)
def test_retry_after_seconds(value, expected):
    assert retry_after_seconds(value) == expected


def test_read_sources_valid_csv(tmp_path):
    csv_file = tmp_path / "sources.csv"
    csv_file.write_text(
        "url,source,licence,title\nhttps://example.com/a.pdf,example,Terms apply,Example PDF\n",
        encoding="utf-8",
    )

    sources = read_sources(csv_file)

    assert len(sources) == 1
    assert sources[0].url == "https://example.com/a.pdf"
    assert sources[0].source == "example"
    assert sources[0].licence == "Terms apply"


def test_read_sources_rejects_missing_licence(tmp_path):
    csv_file = tmp_path / "sources.csv"
    csv_file.write_text(
        "url,source,licence,title\nhttps://example.com/a.pdf,example,,Example PDF\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source and licence are required"):
        read_sources(csv_file)


def test_read_sources_rejects_invalid_url(tmp_path):
    csv_file = tmp_path / "sources.csv"
    csv_file.write_text(
        "url,source,licence,title\nftp://example.com/a.pdf,example,Terms apply,Example PDF\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not an http"):
        read_sources(csv_file)


def test_manifest_add_and_done(tmp_path):
    manifest_file = tmp_path / "manifest.jsonl"
    downloaded_file = tmp_path / "data" / "raw" / "example" / "report.pdf"
    downloaded_file.parent.mkdir(parents=True)
    downloaded_file.write_text("test document", encoding="utf-8")

    manifest = Manifest(manifest_file)
    record = {
        "url": "https://example.com/report.pdf",
        "status": "downloaded",
        "path": "data/raw/example/report.pdf",
    }

    manifest.add(record)

    assert manifest.done(record["url"], tmp_path)


def test_manifest_not_done_when_file_missing(tmp_path):
    manifest_file = tmp_path / "manifest.jsonl"
    manifest = Manifest(manifest_file)

    manifest.add(
        {
            "url": "https://example.com/report.pdf",
            "status": "downloaded",
            "path": "data/raw/example/report.pdf",
        }
    )

    assert not manifest.done("https://example.com/report.pdf", tmp_path)


def test_manifest_ignores_invalid_json_line(tmp_path):
    manifest_file = tmp_path / "manifest.jsonl"
    manifest_file.write_text(
        '{"url": "https://example.com/a.pdf", "status": "failed"}\ninvalid json line\n',
        encoding="utf-8",
    )

    manifest = Manifest(manifest_file)

    assert "https://example.com/a.pdf" in manifest.records


def test_manifest_repairs_missing_final_newline(tmp_path):
    manifest_file = tmp_path / "manifest.jsonl"
    record = {"url": "https://example.com/a.pdf", "status": "failed"}
    manifest_file.write_text(json.dumps(record), encoding="utf-8")

    Manifest(manifest_file)

    assert manifest_file.read_text(encoding="utf-8").endswith("\n")
