# 2.0.0 field-validation checklist

Run this checklist on the intended GNU/Linux evidence workstation before treating the release candidate as production-ready.

1. Confirm `python3 --version` is 3.11 or newer.
2. Confirm `yt-dlp`, `ffprobe`, `gpg`, and `7z` or `7zz` are installed.
3. Run `youtube-forensic keygen` against a disposable test root, or confirm the existing evidence fingerprint is reused in the production root.
4. Acquire a short public video with captions and no live chat.
5. Acquire a video with available live-chat replay.
6. Repeat with `--no-live-chat`.
7. Repeat using a title containing spaces, Unicode, punctuation, and vertical-bar characters.
8. Confirm `INCOMPLETE` is absent from `FILELIST.txt`, `SHA256SUMS.txt`, and `SHA512SUMS.txt`.
9. Confirm `CASE_RECORD.json` and `CASE_RECORD.md` contain the supplied case comments.
10. Run independent verification from a separate working directory.
11. Tamper with a copied archive and confirm external hash and signature verification fail.
12. Tamper with an extracted evidence file, rebuild an unsigned test archive, and confirm the internal manifest fails.
13. Confirm cookies are not copied into staging or the archive.
14. Confirm a failed acquisition retains staging and an `INCOMPLETE` marker.
15. Confirm successful staging is retained without `INCOMPLETE`.

## Operator identity

Operator resolution uses the following precedence:

1. `--operator`
2. `YOUTUBE_FORENSIC_OPERATOR`
3. `ROOT/config.json`
4. current system username

Explicit values must contain non-whitespace text. The fallback system username is accepted with a prominent warning. `ROOT/config.json` must be a regular JSON file and is written with mode `0600` by `youtube-forensic init`.
