"""
utils.py
--------
General-purpose helper functions used across the YouTube Downloader app:
URL validation, formatting helpers, filesystem helpers, and environment checks.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from typing import Optional

logger = logging.getLogger("youtube_downloader.utils")

# Regex covering the common YouTube URL formats:
# youtube.com/watch?v=..., youtu.be/..., youtube.com/shorts/..., m.youtube.com, youtube-nocookie.com
YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.|m\.)?"
    r"(youtube\.com|youtube-nocookie\.com|youtu\.be)/"
    r"(watch\?v=|shorts/|embed/|v/)?[a-zA-Z0-9_\-]{6,}",
    re.IGNORECASE,
)


def is_valid_youtube_url(url: str) -> bool:
    """
    Validate whether a given string looks like a YouTube URL.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL matches a known YouTube URL pattern, False otherwise.
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    return bool(YOUTUBE_URL_PATTERN.match(url))


def format_bytes(num_bytes: Optional[float]) -> str:
    """
    Convert a byte count into a human-readable string (e.g. 1.2 MB).

    Args:
        num_bytes: Number of bytes. Can be None if unknown.

    Returns:
        A human-readable file size string, or "Unknown" if num_bytes is None.
    """
    if num_bytes is None:
        return "Unknown"
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "Unknown"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_duration(seconds: Optional[int]) -> str:
    """
    Convert a duration in seconds into HH:MM:SS or MM:SS format.

    Args:
        seconds: Duration in seconds.

    Returns:
        Human-readable duration string, or "Unknown" if seconds is None.
    """
    if seconds is None:
        return "Unknown"
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "Unknown"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_number(num: Optional[int]) -> str:
    """
    Format large integers with thousands separators (e.g. 1,234,567).

    Args:
        num: Integer value (e.g. view count).

    Returns:
        Formatted string, or "Unknown" if num is None.
    """
    if num is None:
        return "Unknown"
    try:
        return f"{int(num):,}"
    except (TypeError, ValueError):
        return "Unknown"


def format_upload_date(date_str: Optional[str]) -> str:
    """
    Convert a yt-dlp upload_date string (YYYYMMDD) into YYYY-MM-DD.

    Args:
        date_str: Raw upload date string from yt-dlp metadata.

    Returns:
        Formatted date string, or "Unknown" if unavailable/invalid.
    """
    if not date_str or len(date_str) != 8:
        return "Unknown"
    try:
        return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
    except Exception:
        return "Unknown"


def sanitize_filename(filename: str) -> str:
    """
    Remove characters that are unsafe for filenames on most operating systems.

    Args:
        filename: The raw filename (often derived from a video title).

    Returns:
        A sanitized filename safe to use on disk.
    """
    if not filename:
        return "download"
    # Remove characters illegal on Windows/Mac/Linux filesystems.
    sanitized = re.sub(r'[\\/*?:"<>|]', "", filename)
    sanitized = sanitized.strip().strip(".")
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized[:150] if sanitized else "download"


def generate_unique_id() -> str:
    """Generate a short unique identifier used to namespace temp download folders."""
    return uuid.uuid4().hex[:12]


def is_ffmpeg_installed() -> bool:
    """
    Check whether FFmpeg is available on the system PATH.

    Returns:
        True if the `ffmpeg` executable can be located, False otherwise.
    """
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_version() -> str:
    """
    Retrieve the installed FFmpeg version string, if available.

    Returns:
        A short version string, or "Not found" if FFmpeg is not installed.
    """
    if not is_ffmpeg_installed():
        return "Not found"
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else "Unknown"
        # Example first line: "ffmpeg version 6.0 Copyright (c) ..."
        match = re.search(r"ffmpeg version (\S+)", first_line)
        return match.group(1) if match else first_line
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not determine FFmpeg version: %s", exc)
        return "Unknown"


def get_python_version() -> str:
    """Return the running Python interpreter version as a string."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def ensure_directory(path: str) -> None:
    """
    Create a directory (and parents) if it does not already exist.

    Args:
        path: Directory path to ensure exists.
    """
    os.makedirs(path, exist_ok=True)


def clear_directory(path: str) -> None:
    """
    Delete a directory and all of its contents, if it exists.

    Args:
        path: Directory path to remove.
    """
    if os.path.isdir(path):
        try:
            shutil.rmtree(path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to clean up directory %s: %s", path, exc)


def find_downloaded_file(directory: str) -> Optional[str]:
    """
    Find the first non-hidden file inside a directory (used to locate the
    final merged/converted output produced by yt-dlp).

    Args:
        directory: Directory to search.

    Returns:
        Full path to the found file, or None if no file is found.
    """
    if not os.path.isdir(directory):
        return None
    for entry in sorted(os.listdir(directory)):
        if entry.startswith("."):
            continue
        full_path = os.path.join(directory, entry)
        if os.path.isfile(full_path):
            return full_path
    return None