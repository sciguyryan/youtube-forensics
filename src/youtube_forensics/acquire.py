"""Acquire, preserve, sign, and verify forensic copies of online video evidence.

This module coordinates the end-to-end acquisition workflow. It captures the
primary media and associated metadata, records operator and tool information,
generates cryptographic manifests, creates a sealed archive, signs the result,
and performs mandatory self-verification before reporting success.
"""

from __future__ import annotations

import json
import platform
import shutil
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .archive import create_archive
from .commands import require, run, version
from .console import log, summary
from .errors import ToolkitError
from .hashing import digest, write_filelist, write_manifest
from .identity import OperatorIdentity, export_public_key, sign_with_operator
from .keys import ensure_key, sign
from .models import CaseInfo, iso_utc
from .records import initial_record, write_record
from .verify import verify_archive


def _id() -> str:
    """Return a timestamped identifier suitable for an acquisition run."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _video_id(url: str) -> str | None:
    """Extract a YouTube video identifier from a supported URL.

    Args:
        url: The source URL supplied for acquisition.

    Returns:
        The video identifier when present, otherwise ``None``.
    """

    parsed = urlparse(url)
    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/") or None

    return parse_qs(parsed.query).get("v", [None])[0]


def _tool_versions() -> dict[str, str]:
    """Return versions for supported command-line tools found on the system."""

    names = ["yt-dlp", "ffprobe", "mediainfo", "curl", "gpg"]
    return {name: version(name) for name in names if shutil.which(name)}


def acquire(
    *,
    root: Path,
    url: str,
    case: CaseInfo,
    cookies: Path | None = None,
    subtitle_langs: str = "en.*,orig.*",
    live_chat: bool = True,
    sleep_requests: str = "3",
    sleep_subtitles: str = "8",
    min_sleep: str = "5",
    max_sleep: str = "12",
    rate_limit: str = "5M",
) -> Path:
    """Acquire and seal a forensic archive for an online video source.

    The workflow captures the source media and related metadata, records the
    acquisition environment, generates evidence manifests, creates and signs a
    7-Zip archive, and verifies the completed archive before returning it.

    Args:
        root: Toolkit working directory. Archive, log, and key directories are
            created beneath this path as required.
        url: Source video URL to acquire.
        case: Case and operator information for the acquisition record.
        cookies: Optional cookies file passed to ``yt-dlp``.
        subtitle_langs: ``yt-dlp`` subtitle language selector.
        live_chat: Whether to attempt a best-effort live-chat replay capture.
        sleep_requests: Delay, in seconds, between extraction requests.
        sleep_subtitles: Delay, in seconds, before subtitle requests.
        min_sleep: Minimum random delay between downloads.
        max_sleep: Maximum random delay between downloads.
        rate_limit: Maximum download rate accepted by ``yt-dlp``.

    Returns:
        The path to the verified and sealed archive.

    Raises:
        ToolkitError: If the primary acquisition or mandatory verification
            fails.
    """

    for command in ("yt-dlp", "ffprobe", "gpg"):
        require(command)

    root = root.resolve()
    archive_dir = root / "archived"
    log_dir = root / "logs"
    pgp_dir = root / "pgp"

    for directory in (archive_dir, log_dir, pgp_dir):
        directory.mkdir(parents=True, exist_ok=True)

    acquisition_id = _id()
    stage = archive_dir / f".staging-{case.case_id}-{acquisition_id}"
    stage.mkdir()

    incomplete = stage / "INCOMPLETE"
    incomplete.write_text(
        "Acquisition has not completed mandatory verification.\n",
        encoding="utf-8",
    )

    for directory_name in ("evidence", "reports", "http"):
        (stage / directory_name).mkdir()

    log_path = log_dir / f"{case.case_id}-{acquisition_id}.log"

    def note(level: str, text: str) -> None:
        """Write a message to both the console and acquisition log."""

        log(level, text)
        with log_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(f"[{iso_utc()}] [{level}] {text}\n")

    public_key = pgp_dir / "evidence-public-key.asc"
    fingerprint_file = pgp_dir / "evidence-key-fingerprint.txt"
    gnupg_home = pgp_dir / "keyring"

    fingerprint = ensure_key(gnupg_home, public_key, fingerprint_file)
    tools = _tool_versions()
    record = initial_record(case, acquisition_id, url, tools)
    identity = OperatorIdentity(**case.operator_identity)

    note(
        "INFO",
        (
            f"Operator identified as {identity.name!r} "
            f"({identity.operator_id}) via {case.operator_source}; "
            f"login username: {case.operator_username}"
        ),
    )

    record.source["video_id"] = _video_id(url)
    record.evidence["key_fingerprint"] = fingerprint
    record.evidence["live_chat_status"] = "Pending" if live_chat else "Skipped"
    write_record(stage, record)

    shutil.copy2(public_key, stage / "evidence-public-key.asc")
    (stage / "operator-identity.json").write_text(
        json.dumps(identity.public_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    export_public_key(identity, stage / "operator-public-key.asc")

    output = str(stage / "evidence" / "%(id)s-%(title)s.%(ext)s")
    ytdlp = [
        "yt-dlp",
        "--newline",
        "--no-progress",
        "--ignore-config",
        "--write-info-json",
        "--write-description",
        "--write-thumbnail",
        "--write-all-thumbnails",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        subtitle_langs,
        "--write-comments",
        "--write-desktop-link",
        "--merge-output-format",
        "mkv",
        "--sleep-requests",
        sleep_requests,
        "--sleep-subtitles",
        sleep_subtitles,
        "--sleep-interval",
        min_sleep,
        "--max-sleep-interval",
        max_sleep,
        "--limit-rate",
        rate_limit,
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--retry-sleep",
        "http:exp=2:60",
        "--retry-sleep",
        "fragment:exp=2:30",
        "-o",
        output,
    ]
    if cookies:
        ytdlp += ["--cookies", str(cookies)]

    note("INFO", "Starting primary yt-dlp acquisition")
    result = run(ytdlp + [url], check=False, transcript=log_path)
    (stage / "reports" / "yt-dlp-primary.stdout.txt").write_text(
        result.stdout,
        encoding="utf-8",
    )
    (stage / "reports" / "yt-dlp-primary.stderr.txt").write_text(
        result.stderr,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise ToolkitError(
            f"Primary yt-dlp acquisition failed with exit {result.returncode}"
        )

    if live_chat:
        chat = [
            "yt-dlp",
            "--ignore-config",
            "--skip-download",
            "--write-subs",
            "--sub-langs",
            "live_chat",
            "-o",
            output,
        ]
        if cookies:
            chat += ["--cookies", str(cookies)]

        note("INFO", "Starting best-effort live-chat acquisition")
        chat_result = run(chat + [url], check=False, transcript=log_path)
        status = (
            "Complete" if chat_result.returncode == 0 else "Partial or unavailable"
        )
        record.evidence["live_chat_status"] = status
        (stage / "reports" / "live-chat-capture.txt").write_text(
            (
                f"Status: {status}\n"
                f"Exit status: {chat_result.returncode}\n\n"
                f"STDOUT\n{chat_result.stdout}\n"
                f"STDERR\n{chat_result.stderr}\n"
            ),
            encoding="utf-8",
        )

        if chat_result.returncode != 0:
            record.observations.append(
                "Live-chat replay acquisition was partial or unavailable; "
                "retained output is best-effort evidence."
            )
            note("WARN", "Live-chat replay was partial or unavailable")

    curl = shutil.which("curl")
    if curl:
        headers = stage / "http" / "response-headers.txt"
        page = stage / "http" / "watch-page.html"
        note("INFO", "Starting supplemental HTTP capture")
        curl_result = run(
            [
                curl,
                "--location",
                "--silent",
                "--show-error",
                "--dump-header",
                str(headers),
                "--output",
                str(page),
                "--write-out",
                "%{url_effective}",
                url,
            ],
            check=False,
            transcript=log_path,
        )
        (stage / "http" / "effective-url.txt").write_text(
            curl_result.stdout + "\n",
            encoding="utf-8",
        )
        (stage / "http" / "retrieved-utc.txt").write_text(
            iso_utc() + "\n",
            encoding="utf-8",
        )
        record.source["effective_url"] = curl_result.stdout.strip() or None

    info_files = list((stage / "evidence").glob("*.info.json"))
    if info_files:
        try:
            info = json.loads(info_files[0].read_text(encoding="utf-8"))
            record.source.update(
                {
                    "title": info.get("title"),
                    "channel": info.get("channel"),
                    "published_date": info.get("upload_date"),
                    "video_id": info.get("id"),
                }
            )
        except (OSError, json.JSONDecodeError):
            record.observations.append(
                "Primary yt-dlp metadata JSON could not be parsed for the "
                "case record."
            )

    media_files = (
        list((stage / "evidence").glob("*.mkv"))
        + list((stage / "evidence").glob("*.mp4"))
        + list((stage / "evidence").glob("*.webm"))
    )
    for media in media_files:
        probe = run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(media),
            ],
            check=False,
        )
        (stage / "reports" / f"{media.name}.ffprobe.json").write_text(
            probe.stdout,
            encoding="utf-8",
        )

        if shutil.which("mediainfo"):
            media_info = run(
                ["mediainfo", "--Output=JSON", str(media)],
                check=False,
            )
            (stage / "reports" / f"{media.name}.mediainfo.json").write_text(
                media_info.stdout,
                encoding="utf-8",
            )

    note("INFO", "Media acquisition and supplemental capture complete")
    record.acquisition["completed_utc"] = iso_utc()
    record.evidence["signature_status"] = "Pending"
    record.evidence["verification_status"] = "Pending"
    write_record(stage, record)

    note("INFO", "Finalising evidence records and internal manifests")
    shutil.copy2(log_path, stage / "acquisition.log")
    (stage / "acquisition.txt").write_text(
        (
            f"Toolkit version: {__version__}\n"
            f"Acquisition ID: {acquisition_id}\n"
            f"Case ID: {case.case_id}\n"
            f"Operator: {identity.name}\n"
            f"Operator ID: {identity.operator_id}\n"
            f"Operator source: {case.operator_source}\n"
            f"Operator profile SHA-256: {case.operator_profile_sha256}\n"
            "Operator signing key: "
            f"{identity.operator_signing_subkey_fingerprint}\n"
            f"Login username: {case.operator_username}\n"
            f"Source URL: {url}\n"
            f"Evidence-key fingerprint: {fingerprint}\n"
        ),
        encoding="utf-8",
    )

    toolkit_details = {
        "toolkit": "YouTube Forensic Toolkit",
        "version": __version__,
        "python": platform.python_version(),
        "tools": tools,
        "runtime": {
            "operator_identity": case.operator_identity,
            "operator_source": case.operator_source,
            "operator_profile_sha256": case.operator_profile_sha256,
            "operator_username": case.operator_username,
            "hostname": socket.gethostname(),
        },
    }
    (stage / "TOOLKIT.json").write_text(
        json.dumps(toolkit_details, indent=2) + "\n",
        encoding="utf-8",
    )
    (stage / "VERIFICATION.txt").write_text(
        "Use youtube-forensic verify ARCHIVE.7z to verify this package.\n",
        encoding="utf-8",
    )

    incomplete.unlink(missing_ok=True)

    # The canonical evidence-set identity covers only acquired payloads and
    # technical reports. Excluding the case record and checksum manifests avoids
    # introducing a self-reference into the evidence-set hash.
    evidence_manifest = stage / "EVIDENCESET-SHA256.txt"
    payload_lines: list[str] = []
    for top_level_name in ("evidence", "reports", "http"):
        base = stage / top_level_name
        payload_paths = sorted(
            (
                path
                for path in base.rglob("*")
                if path.is_file() and not path.is_symlink()
            ),
            key=lambda path: path.relative_to(stage).as_posix(),
        )
        for path in payload_paths:
            relative_path = path.relative_to(stage).as_posix()
            payload_lines.append(f"{digest(path, 'sha256')}  {relative_path}")

    evidence_manifest.write_text(
        "\n".join(payload_lines) + "\n",
        encoding="utf-8",
    )
    evidence_set_hash = digest(evidence_manifest, "sha256")
    archive_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    archive = (
        archive_dir
        / f"{case.case_id}_{archive_date}_{evidence_set_hash[:16]}.7z"
    )

    record.evidence["evidence_set_sha256"] = evidence_set_hash
    record.evidence["archive_filename"] = archive.name
    record.custody_events.append(
        {
            "utc": iso_utc(),
            "released_by": "",
            "received_by": identity.name,
            "purpose": "Initial acquisition and preservation",
            "media_seal_id": archive.name,
            "signature": "",
        }
    )
    write_record(stage, record)
    write_filelist(stage, stage / "FILELIST.txt")
    write_manifest(stage, stage / "SHA256SUMS.txt", "sha256")
    write_manifest(stage, stage / "SHA512SUMS.txt", "sha512")
    create_archive(stage, archive)

    sha256 = digest(archive, "sha256")
    sha512 = digest(archive, "sha512")
    Path(f"{archive}.sha256").write_text(
        f"{sha256}  {archive.name}\n",
        encoding="ascii",
    )
    Path(f"{archive}.sha512").write_text(
        f"{sha512}  {archive.name}\n",
        encoding="ascii",
    )

    signature = Path(f"{archive}.asc")
    sign(gnupg_home, archive, signature, fingerprint)

    operator_signature = Path(f"{archive}.operator.asc")
    sign_with_operator(identity, archive, operator_signature)

    verification_report = Path(f"{archive}.verification.txt")
    verified = verify_archive(archive, public_key, verification_report)
    if not verified.passed:
        (stage / "INCOMPLETE").write_text(
            "Mandatory self-verification failed.\n",
            encoding="utf-8",
        )
        raise ToolkitError(
            "Mandatory self-verification failed. Evidence retained but not "
            f"sealed: {archive}"
        )

    rows = [
        ("Case ID", case.case_id, "INFO"),
        ("Acquisition ID", acquisition_id, "INFO"),
        ("Operator", identity.name, "INFO"),
        ("Operator ID", identity.operator_id, "INFO"),
        ("Operator signature", "PRESENT", "PASS"),
        ("Source URL", url, "INFO"),
        ("Archive", str(archive), "PASS"),
        ("Archive SHA-256", sha256, "PASS"),
        ("Archive SHA-512", sha512, "PASS"),
        ("Detached signature", "PRESENT", "PASS"),
        ("Self-verification", "PASS", "PASS"),
        ("Evidence sealed", "YES", "PASS"),
        ("Staging retained", str(stage), "INFO"),
        ("Verification report", str(verification_report), "INFO"),
    ]
    summary("FORENSIC ACQUISITION COMPLETE", rows, True)
    return archive
