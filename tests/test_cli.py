"""Tests for command-line argument parsing."""

import pytest

from youtube_forensics.cli import parser


def test_case_comment_is_required() -> None:
    """Require a case comment for every acquisition command."""
    with pytest.raises(SystemExit) as exc_info:
        parser().parse_args(["acquire", "--case-id", "CASE-1", "https://example.test"])

    assert exc_info.value.code == 2


def test_identity_override_available() -> None:
    """Accept a per-acquisition operator identity-file override."""
    args = parser().parse_args(
        [
            "acquire",
            "--case-id",
            "CASE-1",
            "--case-comment",
            "Purpose",
            "--identity-file",
            "jane.json",
            "https://example.test",
        ]
    )

    assert str(args.identity_file) == "jane.json"


def test_init_arguments() -> None:
    """Parse initialisation options supplied after the root directory."""
    args = parser().parse_args(["--root", "/evidence", "init", "--test-key"])

    assert args.command == "init"
    assert args.test_key is True
