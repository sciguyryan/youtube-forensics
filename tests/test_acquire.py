"""Tests for acquisition helpers and the sealed acquisition workflow."""

import json
from pathlib import Path

import pytest

from youtube_forensics import acquire as acquire_module
from youtube_forensics.errors import ToolkitError
from youtube_forensics.models import CaseInfo, ToolResult, VerificationSummary


def make_case() -> CaseInfo:
    """Return a complete case record suitable for acquisition tests."""
    return CaseInfo(
        "CASE-1",
        "Preserve source",
        {
            "schema_version": 1,
            "operator_id": "jane.doe",
            "name": "Jane Doe",
            "public_contact": None,
            "organisation": "Example Unit",
            "role": "Examiner",
            "operator_key_fingerprint": "A" * 40,
            "operator_signing_subkey_fingerprint": "B" * 40,
        },
        "active_profile",
        "c" * 64,
        "jane",
        None,
        None,
    )


def test_video_id_supports_watch_and_short_urls() -> None:
    """Extract identifiers from standard and shortened YouTube URLs."""
    assert (
        acquire_module._video_id("https://www.youtube.com/watch?v=abc123") == "abc123"
    )
    assert acquire_module._video_id("https://youtu.be/xyz789") == "xyz789"
    assert acquire_module._video_id("https://example.test/video") is None


def test_acquire_happy_path(tmp_path: Path, monkeypatch) -> None:
    """Complete acquisition, sealing, signing, and self-verification."""
    monkeypatch.setattr(acquire_module, "require", lambda command: command)
    monkeypatch.setattr(acquire_module, "_id", lambda: "20260720-120000-deadbeef")
    monkeypatch.setattr(acquire_module, "_tool_versions", lambda: {"yt-dlp": "1"})
    monkeypatch.setattr(acquire_module, "ensure_key", lambda *args: "E" * 40)
    monkeypatch.setattr(
        acquire_module,
        "export_public_key",
        lambda identity, output: output.write_text("operator key", encoding="utf-8"),
    )
    monkeypatch.setattr(
        acquire_module,
        "sign",
        lambda *args: Path(args[2]).write_text("signature", encoding="utf-8"),
    )
    monkeypatch.setattr(
        acquire_module,
        "sign_with_operator",
        lambda *args: Path(args[2]).write_text("operator signature", encoding="utf-8"),
    )
    monkeypatch.setattr(acquire_module, "summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(acquire_module.shutil, "which", lambda command: None)

    def fake_run(argv, **kwargs):
        if argv[0] == "yt-dlp":
            output_template = Path(argv[argv.index("-o") + 1])
            evidence = output_template.parent
            (evidence / "abc-title.mkv").write_bytes(b"media")
            (evidence / "abc-title.info.json").write_text(
                json.dumps({"id": "abc", "title": "Title", "channel": "Channel"}),
                encoding="utf-8",
            )
        return ToolResult(argv, 0, "", "")

    def fake_archive(staging: Path, archive: Path) -> None:
        archive.write_bytes(b"sealed archive")

    def fake_verify(archive: Path, public_key: Path, report: Path):
        report.write_text("PASS\n", encoding="utf-8")
        return VerificationSummary(archive=archive)

    monkeypatch.setattr(acquire_module, "run", fake_run)
    monkeypatch.setattr(acquire_module, "create_archive", fake_archive)
    monkeypatch.setattr(acquire_module, "verify_archive", fake_verify)

    public_key = tmp_path / "pgp" / "evidence-public-key.asc"
    public_key.parent.mkdir(parents=True)
    public_key.write_text("evidence key", encoding="utf-8")

    archive = acquire_module.acquire(
        root=tmp_path,
        url="https://www.youtube.com/watch?v=abc",
        case=make_case(),
        live_chat=False,
    )

    assert archive.is_file()
    assert Path(f"{archive}.sha256").is_file()
    assert Path(f"{archive}.operator.asc").is_file()
    staging = next((tmp_path / "archived").glob(".staging-*"))
    case_record = json.loads((staging / "CASE_RECORD.json").read_text(encoding="utf-8"))
    assert case_record["source"]["title"] == "Title"
    assert not (staging / "INCOMPLETE").exists()


def test_acquire_reports_primary_download_failure(tmp_path: Path, monkeypatch) -> None:
    """Stop the workflow when the mandatory primary download fails."""
    monkeypatch.setattr(acquire_module, "require", lambda command: command)
    monkeypatch.setattr(acquire_module, "ensure_key", lambda *args: "E" * 40)
    monkeypatch.setattr(acquire_module, "_tool_versions", lambda: {})
    monkeypatch.setattr(
        acquire_module,
        "export_public_key",
        lambda identity, output: output.write_text("key", encoding="utf-8"),
    )
    monkeypatch.setattr(
        acquire_module, "run", lambda argv, **kwargs: ToolResult(argv, 1, "", "failed")
    )
    monkeypatch.setattr(acquire_module.shutil, "which", lambda command: None)
    public_key = tmp_path / "pgp" / "evidence-public-key.asc"
    public_key.parent.mkdir(parents=True)
    public_key.write_text("key", encoding="utf-8")

    with pytest.raises(ToolkitError, match="Primary yt-dlp acquisition failed"):
        acquire_module.acquire(
            root=tmp_path, url="https://youtu.be/abc", case=make_case()
        )
