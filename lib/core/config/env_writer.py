"""Write a secret back into ``.env.<env>`` from a running test.

Why this exists: most secrets are authored by hand and only ever read (see
``env_config``). A few are *minted at run time* — a login module authenticates against
the system under test and receives a bearer token that every later module needs. That
token has to outlive the process that produced it, so it is written back into the same
``.env.<env>`` file the rest of the config comes from, keeping one source of truth
instead of a second side-channel file.

This is deliberately shared rather than living inside the module that mints the token:
any module that produces a credential needs exactly this behaviour, and duplicating
dotenv rewriting per module is the failure mode CLAUDE.md warns about.

Four properties matter, and are why this isn't a one-line ``open(...).write()``:

1. **The file is hand-maintained.** It carries section comments and a deliberate key
   order that a human reads. Writes replace a single ``KEY=`` line in place and leave
   every byte of the rest of the file — comments, blank lines and the file's existing
   line terminators — untouched. The terminator part is easy to get wrong: reading and
   writing with Python's defaults silently converts an LF-authored file to CRLF on
   Windows, changing every line in the next diff.
2. **Writers race.** An orchestrator fans its test cases out concurrently, and
   ``pytest-xdist`` can run several subsidiaries as separate processes against the same
   file. Writes are serialised with a cross-process advisory lock.
3. **A partial write is unrecoverable.** This file holds every database and AWS
   credential, is gitignored, and has no upstream copy. Writes go to a temp file and are
   renamed into place, so a crash mid-write leaves the old contents intact rather than a
   truncated file.
4. **The value is untrusted.** It originates in a response header from the system under
   test, so it is validated before being written — a newline in a value would otherwise
   end the assignment and inject arbitrary further variables.

Values are never logged here. ``logging_config._RedactFilter`` is a weak backstop — it
matches only on a log call's *format string*, so it cannot catch a secret that arrives
through an argument — and is not the defence for a module whose whole job is handling
secrets.

Note one deliberate trade-off: :func:`set_secret` also sets ``os.environ[key]``, which
means a value written while targeting one environment outranks the dotenv file of any
other environment resolved later **in the same process** (``env_config`` layers the real
process environment above the file). That is what makes a freshly minted token visible to
the rest of the run; it is not appropriate for a process that deliberately resolves two
environments at once.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

from lib.core.config import env_config
from lib.core.config.env_config import ConfigError, env_file_for

logger = logging.getLogger(__name__)

# How long to wait for another process to release the dotenv lock before giving up.
# Generous relative to the work under the lock (one small file rewrite), so hitting it
# means a stale lock file rather than genuine contention.
_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.05

# Runtime-written keys are appended under this marker when they aren't already present,
# so a human opening the file can tell which values a test run produced.
_RUNTIME_SECTION_HEADER = "# --- written at run time by lib/core/config/env_writer.py ---"

# Shell-style identifier: what a dotenv file can actually represent as a variable name.
_KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class EnvWriteError(RuntimeError):
    """Raised when a secret could not be written back to ``.env.<env>``."""


def _acquire_lock(lock_path: Path) -> None:
    """Take the advisory lock guarding one dotenv file, blocking until it's free.

    Uses exclusive file creation (``O_CREAT | O_EXCL``) rather than a library lock so
    this works across processes on every platform the suite runs on, with no extra
    dependency. The lock file records the owning PID purely to make a stale lock
    diagnosable by a human.

    Args:
        lock_path: Path of the lock file to create.

    Returns:
        None.

    Raises:
        EnvWriteError: If the lock is still held after ``_LOCK_TIMEOUT_SECONDS`` — the
            usual cause is a crashed run leaving the file behind, in which case deleting
            the named file is the fix.
    """
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise EnvWriteError(
                    f"Timed out after {_LOCK_TIMEOUT_SECONDS}s waiting for {lock_path}. "
                    "If no other test run is active, delete that file — it is stale."
                ) from None
            time.sleep(_LOCK_POLL_SECONDS)
            continue
        # Once the file exists the lock is held, so any failure from here must remove it
        # again — otherwise a transient write error (full disk, sync filter) leaves a
        # lock nobody owns and every later run stalls until a human deletes it.
        try:
            try:
                os.write(fd, str(os.getpid()).encode("ascii"))
            finally:
                os.close(fd)
        except Exception:
            _release_lock(lock_path)
            raise
        return


def _release_lock(lock_path: Path) -> None:
    """Release the advisory lock, tolerating a lock file that's already gone.

    Args:
        lock_path: Path of the lock file to remove.

    Returns:
        None.
    """
    try:
        lock_path.unlink()
    except FileNotFoundError:
        logger.debug("Lock file %s was already removed", lock_path)


def _replace_or_append(lines: list[str], key: str, value: str) -> list[str]:
    """Return ``lines`` with ``key`` set to ``value``, preserving everything else.

    Replaces the last uncommented assignment to ``key`` — last, because that's the one
    ``dotenv_values`` itself would have won with, so the file's parsed meaning and its
    visible text stay in agreement. When the key is absent entirely it's appended under
    ``_RUNTIME_SECTION_HEADER`` instead, so run-time-written values are visibly grouped
    rather than scattered into a hand-authored section.

    Commented-out lines (``# KEY=...``) are left alone: they're documentation of a
    default, not an assignment.

    Args:
        lines: File contents split into lines, without trailing newlines.
        key: The environment variable name, e.g. ``"BE_API_TOKEN_MJP"``.
        value: The new value, written verbatim after ``=``.

    Returns:
        A new list of lines. The input list is not mutated.
    """
    updated = list(lines)
    prefix = f"{key}="
    target = None
    for index, line in enumerate(updated):
        if line.lstrip().startswith(prefix):
            target = index

    if target is not None:
        updated[target] = f"{key}={value}"
        return updated

    if updated and updated[-1].strip():
        updated.append("")
    if _RUNTIME_SECTION_HEADER not in updated:
        updated.append(_RUNTIME_SECTION_HEADER)
    updated.append(f"{key}={value}")
    return updated


def set_secret(env: str, key: str, value: str) -> None:
    """Persist ``key=value`` into ``.env.<env>`` and make it visible to this process.

    Why both: writing the file alone would not affect the current run, because
    ``get_config`` is cached and the process environment outranks the file anyway
    (see ``env_config``'s precedence rules). So this does three things in order —
    rewrite the file, set ``os.environ[key]``, then call ``env_config.refresh()`` so the
    next ``get_config()`` observes the new value rather than a cached pre-write one.

    The file rewrite is surgical: only the line assigning ``key`` changes, and comments,
    blank lines and key order are preserved. Concurrent writers (async fan-out within a
    run, or ``pytest-xdist`` across subsidiaries) are serialised by an advisory lock.

    Args:
        env: One of "dev", "stg", "prod" — selects which ``.env.<env>`` file is written.
        key: Variable name to set, e.g. ``"BE_API_TOKEN_MJP"``.
        value: Value to store. Written verbatim, so any needed quoting is the caller's
            responsibility. Never logged.

    Returns:
        None.

    Raises:
        ConfigError: If ``env`` is not a known environment.
        EnvWriteError: If the dotenv file does not exist, or the advisory lock could not
            be acquired within the timeout.
    """
    if env not in env_config.ENVIRONMENTS:
        raise ConfigError(
            f"Unknown ENV '{env}'. Expected one of: {', '.join(env_config.ENVIRONMENTS)}"
        )

    env_path = env_file_for(env)
    if not env_path.is_file():
        raise EnvWriteError(
            f"Cannot write {key}: {env_path} does not exist. "
            f"Copy .env.example to .env.{env} first (see docs/setup/getting-started.md)."
        )

    _validate_key(key)
    _validate_value(key, value)

    lock_path = env_path.with_suffix(env_path.suffix + ".lock")
    _acquire_lock(lock_path)
    try:
        # newline="" so the terminators arrive verbatim and are not normalised to "\n";
        # that's what lets the file be rewritten in its own style rather than the
        # platform's. Reading with the default would silently convert a LF-authored file
        # to CRLF on Windows, changing every line in the diff.
        original = env_path.read_text(encoding="utf-8", newline="")
        terminator = _detect_terminator(original)
        updated = _replace_or_append(original.splitlines(), key, value)
        _atomic_write(env_path, terminator.join(updated) + terminator)
    finally:
        _release_lock(lock_path)

    os.environ[key] = value
    env_config.refresh()
    logger.info("Persisted %s to %s", key, env_path.name)


def _validate_key(key: str) -> None:
    """Reject key names a dotenv file cannot represent.

    Args:
        key: The proposed variable name.

    Returns:
        None.

    Raises:
        EnvWriteError: If ``key`` isn't a valid shell-style identifier.
    """
    if not _KEY_PATTERN.fullmatch(key):
        raise EnvWriteError(
            f"Invalid environment variable name {key!r}: expected letters, digits and "
            "underscores, not starting with a digit."
        )


def _validate_value(key: str, value: str) -> None:
    """Reject values that would corrupt the file or inject extra variables.

    Why this is not paranoia: the value written here comes from a **response header of the
    system under test**. A value containing a newline would end the assignment and make
    every following line a new variable — letting a buggy or hostile response set, say,
    ``POSTGRES_PASSWORD_GDB`` or ``AWS_BASTION_KEY_FILE``, which the next run then uses.
    Verified: ``K=abc\\nEVIL=1`` parses as two variables.

    Args:
        key: The variable being set, for the error message.
        value: The proposed value.

    Returns:
        None.

    Raises:
        EnvWriteError: If ``value`` contains a carriage return or newline.
    """
    if "\n" in value or "\r" in value:
        raise EnvWriteError(
            f"Refusing to write {key}: the value contains a newline, which would inject "
            "additional variables into the dotenv file."
        )


def _detect_terminator(text: str) -> str:
    """Return the line terminator a file already uses, defaulting to LF.

    Args:
        text: File contents read with ``newline=""`` so terminators are preserved.

    Returns:
        ``"\\r\\n"`` if the first line break in the file is a CRLF, otherwise ``"\\n"``.
        An empty or single-line file gets LF, matching ``.env.example``.
    """
    return "\r\n" if "\r\n" in text else "\n"


def _atomic_write(path: Path, content: str) -> None:
    """Replace a file's contents without ever leaving it truncated.

    Why: the naive ``write_text`` truncates the file and then writes. A crash, kill or
    sync-filter error in between leaves ``.env.<env>`` empty or half-written — and that
    file holds every database and AWS credential, is gitignored, and is hand-maintained,
    so there is nothing to restore from. Writing a sibling temp file and renaming makes
    the swap atomic: readers see either the old contents or the new ones.

    Args:
        path: File to replace.
        content: Full new contents, terminators included.

    Returns:
        None.

    Raises:
        OSError: If the temp file could not be written or renamed into place.
    """
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        # newline="" so `content`'s terminators are written through unchanged.
        temp_path.write_text(content, encoding="utf-8", newline="")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
