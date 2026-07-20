"""Tests for external command execution and transcript capture."""

import sys
from pathlib import Path

from youtube_forensics.commands import run


def test_run_writes_stdout_stderr_and_exit_to_transcript(tmp_path: Path) -> None:
    """Record command output streams and exit status in the transcript."""
    transcript = tmp_path / "acquisition.log"
    result = run(
        [
            sys.executable,
            "-c",
            "import sys; print('out-line'); print('err-line', file=sys.stderr)",
        ],
        transcript=transcript,
    )

    assert result.returncode == 0
    text = transcript.read_text(encoding="utf-8")
    assert "[COMMAND]" in text
    assert "[STDOUT] out-line" in text
    assert "[STDERR] err-line" in text
    assert "[EXIT] 0" in text


def test_run_does_not_write_transcript_unless_requested(tmp_path: Path) -> None:
    """Avoid creating a transcript unless the caller explicitly requests one."""
    transcript = tmp_path / "acquisition.log"

    run([sys.executable, "-c", "print('quiet')"])

    assert not transcript.exists()
