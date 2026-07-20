# YouTube Forensic Toolkit 2.0

A Python 3 toolkit for acquiring, documenting, hashing, archiving, signing, and independently verifying YouTube evidence on GNU/Linux.

The orchestration layer is Python; specialist work remains delegated to established command-line tools such as `yt-dlp`, `ffprobe`, `mediainfo`, `curl`, `gpg`, and `7z`/`7zz`.

## Acquisition logging

The main acquisition log records toolkit status messages and transcripts for the primary yt-dlp acquisition, best-effort live-chat capture, and supplemental HTTP capture. Each transcript contains the command, stdout, stderr, and exit status. Exact unprefixed yt-dlp output is also retained in the evidence package under `reports/`.

## Requirements

- Python 3.11 or newer
- yt-dlp
- FFmpeg/ffprobe
- GnuPG
- 7-Zip (`7zz` or `7z`)
- curl and MediaInfo are recommended

## Run immediately without pip or virtual-environment activation

The toolkit has no third-party Python runtime dependencies. From the extracted source directory, you can test it directly without installing anything into Python:

```bash
PYTHONPATH=src python3 -m youtube_forensic --help
```

This is the recommended first test and works from Bash, Zsh, and fish.

## Optional installation into a virtual environment

A working `venv` and `pip` installation is required only when you want the generated `youtube-forensic` console command.

On Debian or Ubuntu, install the supporting Python packages first when necessary:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

On Fedora:

```bash
sudo dnf install python3-pip
```

On Arch Linux:

```bash
sudo pacman -S python-pip
```

Create the virtual environment:

```bash
python3 -m venv .venv
```

Activate it in **Bash or Zsh**:

```bash
source .venv/bin/activate
python3 -m pip install .
```

Activate it in **fish**:

```fish
source .venv/bin/activate.fish
python3 -m pip install .
```

Do not source `.venv/bin/activate` from fish; that file uses POSIX-shell `case ... esac` syntax.

Confirm the installed command:

```bash
youtube-forensic --help
```

For editable development and tests, after activating the correct shell-specific environment:

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest
```

## Copy/paste acquisition test

The following uses case ID `CASE-0031`, the previously identified YouTube URL, and the toolkit data root used in the earlier examples.

## Operator identification

The toolkit resolves the human operator in this order:

1. `--operator "Full Name"`
2. `YOUTUBE_FORENSIC_OPERATOR`
3. `ROOT/config.json`, created by the `init` command
4. Current GNU/Linux login username, accompanied by a prominent warning

For a persistent toolkit-root default:

```bash
PYTHONPATH=src python3 -m youtube_forensic \
  --root /mnt/storage/Projects/youtube-forensic \
  init \
  --operator "Jane Smith"
```

The configuration is stored as `ROOT/config.json` with mode `0600`. Use `--force` to deliberately replace an existing configuration. A one-off `--operator` always takes precedence. The environment variable is convenient on a managed workstation:

```bash
export YOUTUBE_FORENSIC_OPERATOR="Jane Smith"
```

Every case record separately captures the resolved operator, its source, the underlying login username, and the hostname.

```bash
youtube-forensic \
  --root /mnt/storage/Projects/youtube-forensic \
  acquire \
  --case-id CASE-0031 \
  --operator "Jane Smith" \
  --matter-title "Weekly Pokémon GO coin publication" \
  --case-comment "Preservation of the identified YouTube publication concerning weekly Pokémon GO coin availability, including associated metadata, available captions, HTTP response material, and any available live-chat replay." \
  'https://www.youtube.com/watch?v=np4GAFN9Jyo'
```

Recommended copy/paste test from the source checkout—no activation or pip required:

```bash
PYTHONPATH=src python3 -m youtube_forensic \
  --root /mnt/storage/Projects/youtube-forensic \
  acquire \
  --case-id CASE-0031 \
  --operator "Jane Smith" \
  --matter-title "Weekly Pokémon GO coin publication" \
  --case-comment "Preservation of the identified YouTube publication concerning weekly Pokémon GO coin availability, including associated metadata, available captions, HTTP response material, and any available live-chat replay." \
  'https://www.youtube.com/watch?v=np4GAFN9Jyo'
```

For longer comments, place the text in a file and substitute:

```bash
--case-comment-file case-comments.md
```

for the `--case-comment` option. Exactly one of those options is required.

The first acquisition automatically starts interactive creation of a dedicated passphrase-protected RSA-4096 GPG signing key when one is absent.

## Verification

After acquisition, use the exact archive path printed in the completion summary. For example:

```bash
youtube-forensic \
  --root /mnt/storage/Projects/youtube-forensic \
  verify \
  /mnt/storage/Projects/youtube-forensic/archived/CASE-0031_YYYYMMDD_HASH.7z
```

The verifier enforces the current evidence-package contract and rejects incomplete documentation layouts.

## Evidence package

A 2.x archive contains, among other acquired files:

- `CASE_RECORD.json` — canonical structured case record
- `CASE_RECORD.md` — human-readable rendering
- `TOOLKIT.json` — Python and external-tool versions
- `EVIDENCESET-SHA256.txt` — canonical acquired-payload manifest
- `FILELIST.txt`
- `SHA256SUMS.txt`
- `SHA512SUMS.txt`
- `acquisition.txt`
- `acquisition.log`
- `VERIFICATION.txt`
- `evidence-public-key.asc`
- `evidence/`, `reports/`, and `http/`

The transient `INCOMPLETE` state marker is operational metadata and is never included in evidence inventories or checksum manifests.

## Transaction boundary

Finalization follows this order:

1. Complete all mandatory and best-effort captures.
2. Finalize acquisition log and generated records.
3. Remove the transient incomplete marker.
4. Generate evidence-set identity, file inventory, and internal manifests.
5. Create the archive.
6. Generate external SHA-256 and SHA-512 sidecars.
7. Create the detached GPG signature.
8. Verify in an isolated temporary directory.
9. Report the acquisition as sealed only if every mandatory stage passes.

Staging is intentionally retained after success and failure.

## Security notes

- Cookie files are used in place and are not copied into the evidence package.
- The verifier rejects absolute paths, drive-prefixed paths, traversal members, and extracted symlinks.
- GPG verification is performed in an isolated temporary keyring.
- No downloaded media is transcoded by the toolkit.

## License

LGPL-2.1-or-later.

## Dedicated GnuPG keyring management

The toolkit stores its evidence-signing keyring under:

```text
ROOT/pgp/keyring
```

For the examples below, the root is `/mnt/storage/Projects/youtube-forensic`.
The public key is safe to distribute. The secret-key export and ownertrust file
must be protected as sensitive evidence-system credentials.

### Show the evidence-key fingerprint

```bash
gpg \
  --homedir /mnt/storage/Projects/youtube-forensic/pgp/keyring \
  --with-colons --fingerprint --list-secret-keys
```

The toolkit also writes the selected fingerprint to:

```text
/mnt/storage/Projects/youtube-forensic/pgp/evidence-key-fingerprint.txt
```

### Export the public key

```bash
FPR="$(tr -d '[:space:]' < /mnt/storage/Projects/youtube-forensic/pgp/evidence-key-fingerprint.txt)"

gpg \
  --homedir /mnt/storage/Projects/youtube-forensic/pgp/keyring \
  --armor --export "$FPR" \
  > youtube-forensic-evidence-public-key.asc
```

This public key may be supplied to another verifier without exposing the
private signing key.

### Export an encrypted backup of the private key

```bash
FPR="$(tr -d '[:space:]' < /mnt/storage/Projects/youtube-forensic/pgp/evidence-key-fingerprint.txt)"

umask 077
gpg \
  --homedir /mnt/storage/Projects/youtube-forensic/pgp/keyring \
  --armor --export-secret-keys "$FPR" \
  > youtube-forensic-evidence-secret-key.asc
```

GnuPG will invoke pinentry when required. Store this file offline in protected,
encrypted storage. Do not place it inside an evidence archive or transmit it
with the public key.

### Export ownertrust

```bash
gpg \
  --homedir /mnt/storage/Projects/youtube-forensic/pgp/keyring \
  --export-ownertrust \
  > youtube-forensic-ownertrust.txt
```

Ownertrust is not the secret key, but it reveals trust configuration and should
still be handled as administrative backup material.

### Restore the keypair into a fresh toolkit root

Create and secure the destination keyring first:

```bash
mkdir -p /new/toolkit/root/pgp/keyring
chmod 700 /new/toolkit/root/pgp/keyring
```

Import the public and private key material:

```bash
gpg \
  --homedir /new/toolkit/root/pgp/keyring \
  --import youtube-forensic-evidence-public-key.asc

gpg \
  --homedir /new/toolkit/root/pgp/keyring \
  --import youtube-forensic-evidence-secret-key.asc
```

Restore ownertrust when the backup is available:

```bash
gpg \
  --homedir /new/toolkit/root/pgp/keyring \
  --import-ownertrust youtube-forensic-ownertrust.txt
```

Confirm that the secret key and fingerprint are present:

```bash
gpg \
  --homedir /new/toolkit/root/pgp/keyring \
  --list-secret-keys --fingerprint
```

After restoration, run the toolkit's key preflight. It will reuse the imported
key and regenerate the public-key and fingerprint sidecars:

```bash
PYTHONPATH=src python3 -m youtube_forensic \
  --root /new/toolkit/root \
  keygen
```

## Operator identity setup (rc9)

Run `youtube-forensic --root ROOT init` in an interactive terminal. The wizard creates `ROOT/operators/<operator-id>.json`, stores only public identity metadata and full GnuPG fingerprints, and selects a usable secret signing key from the normal system keyring. Private key material is never copied into the toolkit root.

Routine acquisitions use the active profile automatically. Use `acquire --identity-file FILE` for a one-case override. A configured operator key is mandatory: acquisition fails if the personal archive signature cannot be created.
