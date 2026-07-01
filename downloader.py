"""
downloader.py
-------------
Core download logic built on top of yt-dlp. Provides a `YouTubeDownloader`
class responsible for:

  * Fetching video metadata (title, thumbnail, channel, duration, etc.)
  * Determining which video qualities are actually available
  * Downloading video (merged bestvideo+bestaudio -> MP4) at a chosen quality
  * Downloading and converting audio to MP3 (320 kbps via FFmpeg/libmp3lame)
  * Reporting live progress through a caller-supplied callback

All exceptions raised by yt-dlp are translated into a small set of custom,
user-friendly exception classes so the Streamlit UI can show clear messages.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

import yt_dlp

from utils import ensure_directory, sanitize_filename

logger = logging.getLogger("youtube_downloader.downloader")

ProgressCallback = Callable[[Dict[str, Any]], None]

# Standard "ladder" of resolutions we look for when building the quality dropdown.
QUALITY_LADDER = [2160, 1440, 1080, 720, 480, 360, 240, 144]


class DownloaderError(Exception):
    """Base class for all downloader-related errors."""


class InvalidURLError(DownloaderError):
    """Raised when the provided URL is not a usable YouTube URL."""


class VideoUnavailableError(DownloaderError):
    """Raised when a video is private, removed, region-locked, or otherwise unavailable."""


class AgeRestrictedError(DownloaderError):
    """Raised when a video is age-restricted and cannot be fetched without authentication."""


class NetworkError(DownloaderError):
    """Raised when a network-level failure prevents fetching or downloading."""


class YouTubeDownloader:
    """
    Wraps yt-dlp to provide metadata fetching and download operations
    tailored for the Streamlit UI.
    """

    def __init__(self, work_dir: str) -> None:
        """
        Args:
            work_dir: Base directory where per-download temp folders are created.
        """
        self.work_dir = work_dir
        ensure_directory(self.work_dir)

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #

    def fetch_info(self, url: str) -> Dict[str, Any]:
        """
        Fetch metadata for a YouTube video without downloading it.

        Args:
            url: The YouTube video URL.

        Returns:
            A dictionary with normalized metadata fields plus the raw
            yt-dlp `formats` list (used later to build the quality dropdown).

        Raises:
            VideoUnavailableError, AgeRestrictedError, NetworkError, DownloaderError
        """
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise self._translate_download_error(exc) from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected error while fetching info")
            raise DownloaderError(f"Failed to fetch video info: {exc}") from exc

        if info is None:
            raise VideoUnavailableError("No information could be retrieved for this video.")

        return {
            "id": info.get("id"),
            "title": info.get("title", "Unknown title"),
            "channel": info.get("channel") or info.get("uploader", "Unknown channel"),
            "duration": info.get("duration"),
            "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"),
            "thumbnail": self._best_thumbnail(info),
            "description": info.get("description", "") or "",
            "webpage_url": info.get("webpage_url", url),
            "formats": info.get("formats", []),
            "age_limit": info.get("age_limit", 0),
        }

    @staticmethod
    def _best_thumbnail(info: Dict[str, Any]) -> Optional[str]:
        """Pick the highest-resolution thumbnail available from video info."""
        thumbnails = info.get("thumbnails") or []
        if thumbnails:
            # yt-dlp typically orders thumbnails from lowest to highest resolution.
            sorted_thumbs = sorted(
                thumbnails,
                key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
            )
            return sorted_thumbs[-1].get("url")
        return info.get("thumbnail")

    def get_available_qualities(self, formats: List[Dict[str, Any]]) -> List[str]:
        """
        Determine which standard resolutions are actually available for a video.

        Args:
            formats: The raw `formats` list from yt-dlp's extracted info.

        Returns:
            A list of quality labels (e.g. ["Best Quality", "1080p", "720p", ...])
            ordered from highest to lowest, containing only resolutions that exist.
        """
        available_heights = set()
        for fmt in formats:
            height = fmt.get("height")
            vcodec = fmt.get("vcodec")
            if height and vcodec and vcodec != "none":
                available_heights.add(height)

        labels = ["Best Quality"]
        for standard_height in QUALITY_LADDER:
            # Match videos that are at least close to a standard rung
            # (yt-dlp sometimes reports 1088 instead of 1080, etc.)
            if any(abs(h - standard_height) <= 16 for h in available_heights):
                suffix = " (4K)" if standard_height == 2160 else ""
                labels.append(f"{standard_height}p{suffix}")

        return labels

    # ------------------------------------------------------------------ #
    # Downloads
    # ------------------------------------------------------------------ #

    def download_video(
        self,
        url: str,
        quality_label: str,
        output_dir: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> str:
        """
        Download a video at the requested quality, merging bestvideo+bestaudio
        into a single MP4 file via FFmpeg.

        Args:
            url: The YouTube video URL.
            quality_label: A label from `get_available_qualities`
                (e.g. "1080p", "Best Quality").
            output_dir: Directory to save the resulting file into.
            progress_callback: Optional callable invoked with yt-dlp progress dicts.

        Returns:
            The full path to the downloaded MP4 file.

        Raises:
            VideoUnavailableError, AgeRestrictedError, NetworkError, DownloaderError
        """
        ensure_directory(output_dir)
        format_selector = self._build_format_selector(quality_label)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": format_selector,
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(output_dir, "%(title).150s.%(ext)s"),
            "restrictfilenames": False,
            "progress_hooks": [progress_callback] if progress_callback else [],
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }
            ],
        }

        return self._run_download(url, ydl_opts)

    def download_audio(
        self,
        url: str,
        output_dir: str,
        progress_callback: Optional[ProgressCallback] = None,
        bitrate_kbps: int = 320,
    ) -> str:
        """
        Download the best available audio stream and convert it to MP3.

        Args:
            url: The YouTube video URL.
            output_dir: Directory to save the resulting file into.
            progress_callback: Optional callable invoked with yt-dlp progress dicts.
            bitrate_kbps: Target MP3 bitrate (default 320 kbps).

        Returns:
            The full path to the downloaded MP3 file.

        Raises:
            VideoUnavailableError, AgeRestrictedError, NetworkError, DownloaderError
        """
        ensure_directory(output_dir)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best",
            "outtmpl": os.path.join(output_dir, "%(title).150s.%(ext)s"),
            "progress_hooks": [progress_callback] if progress_callback else [],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(bitrate_kbps),
                }
            ],
        }

        return self._run_download(url, ydl_opts)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_format_selector(quality_label: str) -> str:
        """
        Translate a UI quality label into a yt-dlp format-selector string,
        with automatic fallback to the best available quality.
        """
        if quality_label.startswith("Best"):
            return "bestvideo+bestaudio/best"

        # Extract the numeric height, e.g. "1080p" -> 1080, "2160p (4K)" -> 2160
        digits = "".join(ch for ch in quality_label if ch.isdigit())
        if not digits:
            return "bestvideo+bestaudio/best"

        height = int(digits)
        # Prefer exact-or-lower match at this height, then fall back to best overall.
        return (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/"
            f"bestvideo+bestaudio/best"
        )

    def _run_download(self, url: str, ydl_opts: Dict[str, Any]) -> str:
        """Execute a yt-dlp download with the given options and return the output path."""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # yt-dlp exposes the final post-processed filename via this helper.
                final_path = ydl.prepare_filename(info)

                # After postprocessing (e.g. mp3 conversion, mp4 remux) the extension
                # may differ from the originally requested one. Resolve the real file.
                base, _ = os.path.splitext(final_path)
                for ext in (".mp4", ".mp3", ".mkv", ".webm", ".m4a"):
                    candidate = base + ext
                    if os.path.isfile(candidate):
                        return candidate

                if os.path.isfile(final_path):
                    return final_path

                raise DownloaderError("Download completed but the output file could not be located.")

        except yt_dlp.utils.DownloadError as exc:
            raise self._translate_download_error(exc) from exc
        except DownloaderError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected error during download")
            raise DownloaderError(f"Download failed: {exc}") from exc

    @staticmethod
    def _translate_download_error(exc: "yt_dlp.utils.DownloadError") -> DownloaderError:
        """Map a raw yt-dlp DownloadError into a user-friendly custom exception."""
        message = str(exc).lower()

        if "private video" in message:
            return VideoUnavailableError("This video is private and cannot be downloaded.")
        if "video unavailable" in message or "removed" in message:
            return VideoUnavailableError("This video is unavailable or has been removed.")
        if "sign in to confirm your age" in message or "age" in message and "restrict" in message:
            return AgeRestrictedError(
                "This video is age-restricted and cannot be downloaded without authentication."
            )
        if "unable to download webpage" in message or "urlopen error" in message or "network" in message:
            return NetworkError("A network error occurred while contacting YouTube. Please try again.")
        if "unsupported url" in message or "is not a valid url" in message:
            return InvalidURLError("The provided URL is not a valid or supported YouTube URL.")

        return DownloaderError(f"Could not process this video: {exc}")