"""Run ffmpeg and ffprobe safely.

Every command is a **list** of arguments, never one long shell string.
Python hands that list straight to the program, so a path such as
``My Videos/clip (final).mp4`` is passed exactly as written: spaces,
brackets and quotes can't break the command or inject a new one.
"""

import logging
import shlex
import shutil
import subprocess

log = logging.getLogger("clipforge")


class FFmpegError(RuntimeError):
    """Raised when ffmpeg or ffprobe is missing or exits with an error."""


def require_tool(name: str) -> str:
    """Return the full path to ``name`` (ffmpeg or ffprobe) or raise a friendly error."""
    path = shutil.which(name)
    if path is None:
        raise FFmpegError(
            f"{name} was not found on your PATH. Install ffmpeg "
            "(Windows: winget install ffmpeg) and open a new terminal."
        )
    return path


def show_command(args: list[str]) -> str:
    """Return the command as one line of text, for logs and --dry-run only.

    This text is for humans to read. It is never executed.
    """
    return shlex.join(str(a) for a in args)


def run(args: list[str], dry_run: bool = False) -> subprocess.CompletedProcess | None:
    """Run a command and return its result (stdout and stderr as text).

    With ``dry_run=True`` the command is only printed, not run.
    """
    if dry_run:
        print(show_command(args))
        return None

    log.debug("running: %s", show_command(args))
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise FFmpegError(f"could not start {args[0]}: {exc}") from exc

    if result.returncode != 0:
        # ffmpeg writes a lot to stderr. The last few lines hold the real error.
        tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        raise FFmpegError(f"{args[0]} failed (exit code {result.returncode}):\n{tail}")
    return result
