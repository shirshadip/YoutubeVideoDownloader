"""
app.py
------
Streamlit front-end for the YouTube Downloader application.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import logging
import os
import time
from importlib.metadata import version as get_package_version
from typing import Any, Dict, Optional

import streamlit as st
import yt_dlp
import shutil

st.write("FFmpeg:", shutil.which("ffmpeg"))

from downloader import (
    AgeRestrictedError,
    DownloaderError,
    InvalidURLError,
    NetworkError,
    VideoUnavailableError,
    YouTubeDownloader,
)
from utils import (
    clear_directory,
    ensure_directory,
    find_downloaded_file,
    format_bytes,
    format_duration,
    format_number,
    format_upload_date,
    generate_unique_id,
    get_ffmpeg_version,
    get_python_version,
    is_ffmpeg_installed,
    is_valid_youtube_url,
)

# --------------------------------------------------------------------------- #
# Configuration & logging
# --------------------------------------------------------------------------- #

APP_VERSION = "1.0.0"
BASE_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("youtube_downloader.app")

st.set_page_config(
    page_title="YouTube Downloader",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_directory(BASE_DOWNLOAD_DIR)


# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #

def inject_custom_css() -> None:
    """Inject custom CSS for a modern, polished look."""
    st.markdown(
        """
        <style>
        .main-title {
            font-size: 2.6rem;
            font-weight: 800;
            background: linear-gradient(90deg, #FF0000 0%, #FF6B6B 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0;
        }
        .subtitle {
            color: #9aa0a6;
            font-size: 1.05rem;
            margin-top: -0.4rem;
            margin-bottom: 1.5rem;
        }
        .thumbnail-img img {
            border-radius: 16px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
        }
        .info-card {
            background: rgba(127, 127, 127, 0.08);
            border-radius: 14px;
            padding: 1.1rem 1.3rem;
            border: 1px solid rgba(127, 127, 127, 0.15);
        }
        .status-pill {
            display: inline-block;
            padding: 0.2rem 0.7rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .pill-green { background: rgba(46, 204, 113, 0.18); color: #2ecc71; }
        .pill-red { background: rgba(231, 76, 60, 0.18); color: #e74c3c; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #

def init_session_state() -> None:
    """Initialize Streamlit session state keys used throughout the app."""
    defaults: Dict[str, Any] = {
        "video_info": None,
        "session_id": generate_unique_id(),
        "download_ready": False,
        "downloaded_file_path": None,
        "downloaded_file_name": None,
        "last_url": "",
        "cookies_file": os.getenv("YOUTUBE_COOKIES_FILE", ""),
        "cookies_from_browser": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

def render_sidebar() -> None:
    """Render the sidebar with app/environment information."""
    with st.sidebar:
        st.markdown("## ℹ️ Application Info")
        st.markdown(f"**Version:** {APP_VERSION}")
        st.markdown(f"**Python:** {get_python_version()}")
        try:
            yt_dlp_version = get_package_version("yt-dlp")
        except Exception:
            yt_dlp_version = "unknown"
        st.markdown(f"**yt-dlp:** {yt_dlp_version}")

        cookies_file = st.text_input(
            "Cookies file (optional)",
            value=st.session_state.cookies_file,
            placeholder="C:/path/to/cookies.txt",
            help="Netscape-format cookies file helps yt-dlp handle YouTube bot checks.",
        )
        st.session_state.cookies_file = cookies_file.strip() if cookies_file else ""
        if st.session_state.cookies_file and not os.path.isfile(os.path.expanduser(st.session_state.cookies_file)):
            st.warning("The cookies file path does not exist yet. Export or place the file first.", icon="⚠️")

        browser_options = ["", "Chrome", "Edge", "Firefox", "Brave", "Opera", "Safari"]
        browser_value = st.session_state.cookies_from_browser or ""
        browser_index = 0
        if browser_value:
            browser_index = browser_options.index(
                next((option for option in browser_options[1:] if option.lower() == browser_value.lower()), "")
            ) + 1
        browser_choice = st.selectbox(
            "Browser cookies (optional)",
            options=browser_options,
            index=browser_index,
            help="If you have a browser session signed into YouTube, yt-dlp can read its cookies directly.",
        )
        st.session_state.cookies_from_browser = browser_choice.lower() if browser_choice else ""

        ffmpeg_ok = is_ffmpeg_installed()
        pill_class = "pill-green" if ffmpeg_ok else "pill-red"
        pill_text = f"Detected ({get_ffmpeg_version()})" if ffmpeg_ok else "Not found"
        st.markdown(
            f"**FFmpeg:** <span class='status-pill {pill_class}'>{pill_text}</span>",
            unsafe_allow_html=True,
        )

        if not ffmpeg_ok:
            st.warning(
                "FFmpeg was not found on your system PATH. Video merging and "
                "MP3 conversion will not work until it is installed. See the "
                "README for installation instructions.",
                icon="⚠️",
            )

        st.markdown("---")
        st.markdown("**Theme:** Follows your Streamlit app theme settings")
        st.markdown("---")
        st.markdown(
            "Use responsibly: only download videos you own or have "
            "permission to download, in accordance with YouTube's "
            "Terms of Service and applicable copyright law."
        )


# --------------------------------------------------------------------------- #
# Fetch video info
# --------------------------------------------------------------------------- #

def fetch_video_section() -> None:
    """Render the URL input and 'Fetch Video' button, and handle fetching."""
    st.markdown("### 🔗 Enter a YouTube URL")
    col1, col2 = st.columns([4, 1])
    with col1:
        url = st.text_input(
            "YouTube URL",
            placeholder="https://www.youtube.com/watch?v=...",
            label_visibility="collapsed",
        )
    with col2:
        fetch_clicked = st.button("🔍 Fetch Video", use_container_width=True, type="primary")

    if fetch_clicked:
        if not url or not url.strip():
            st.error("Please enter a YouTube URL before fetching.", icon="🚫")
            return

        if not is_valid_youtube_url(url):
            st.error("That doesn't look like a valid YouTube URL. Please check and try again.", icon="🚫")
            return

        downloader = YouTubeDownloader(
            BASE_DOWNLOAD_DIR,
            cookies_file=st.session_state.cookies_file or None,
            cookies_from_browser=st.session_state.cookies_from_browser or None,
        )
        with st.spinner("Fetching video information..."):
            try:
                info = downloader.fetch_info(url.strip())
            except AgeRestrictedError as exc:
                st.error(str(exc), icon="🔞")
                return
            except VideoUnavailableError as exc:
                st.error(str(exc), icon="🚫")
                return
            except NetworkError as exc:
                st.error(str(exc), icon="🌐")
                return
            except InvalidURLError as exc:
                st.error(str(exc), icon="🚫")
                return
            except DownloaderError as exc:
                st.error(f"Something went wrong: {exc}", icon="⚠️")
                return

        st.session_state.video_info = info
        st.session_state.last_url = url.strip()
        st.session_state.download_ready = False
        st.session_state.downloaded_file_path = None
        st.success("Video information retrieved successfully!", icon="✅")


# --------------------------------------------------------------------------- #
# Display video details
# --------------------------------------------------------------------------- #

def render_video_details() -> None:
    """Render the fetched video's thumbnail and metadata."""
    info = st.session_state.video_info
    if not info:
        return

    st.markdown("---")
    col_thumb, col_meta = st.columns([1, 1.4])

    with col_thumb:
        if info.get("thumbnail"):
            st.markdown('<div class="thumbnail-img">', unsafe_allow_html=True)
            st.image(info["thumbnail"], use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

    with col_meta:
        st.markdown(f"#### {info.get('title', 'Unknown title')}")
        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        st.markdown(f"📺 **Channel:** {info.get('channel', 'Unknown')}")
        st.markdown(f"⏱️ **Duration:** {format_duration(info.get('duration'))}")
        st.markdown(f"📅 **Upload Date:** {format_upload_date(info.get('upload_date'))}")
        st.markdown(f"👁️ **Views:** {format_number(info.get('view_count'))}")
        st.markdown("</div>", unsafe_allow_html=True)

        description = info.get("description", "") or ""
        if description:
            with st.expander("📄 Description (preview)"):
                st.write(description[:200] + ("..." if len(description) > 200 else ""))


# --------------------------------------------------------------------------- #
# Download options & progress
# --------------------------------------------------------------------------- #

def make_progress_hook(progress_bar, status_text, details_text):
    """
    Build a yt-dlp progress hook closure that updates Streamlit placeholders.

    yt-dlp calls this hook synchronously during the (blocking) download call,
    so it is safe to update the UI placeholders directly from here.
    """

    def hook(d: Dict[str, Any]) -> None:
        status = d.get("status")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            percent = (downloaded / total) if total else 0.0
            percent = max(0.0, min(percent, 1.0))

            speed = d.get("speed")
            eta = d.get("eta")

            speed_str = f"{format_bytes(speed)}/s" if speed else "calculating..."
            eta_str = f"{eta}s" if eta is not None else "calculating..."
            size_str = format_bytes(total) if total else "Unknown size"

            progress_bar.progress(percent)
            status_text.markdown(f"**Status:** ⬇️ Downloading — {percent * 100:.1f}%")
            details_text.markdown(
                f"**Speed:** {speed_str} &nbsp;|&nbsp; "
                f"**ETA:** {eta_str} &nbsp;|&nbsp; "
                f"**Size:** {size_str}"
            )

        elif status == "finished":
            progress_bar.progress(1.0)
            status_text.markdown("**Status:** ⚙️ Processing / merging with FFmpeg...")
            details_text.markdown("Finalizing the file, please wait...")

        elif status == "error":
            status_text.markdown("**Status:** ❌ Error during download")

    return hook


def download_options_section() -> None:
    """Render quality/type dropdowns and handle the actual download."""
    info = st.session_state.video_info
    if not info:
        return

    st.markdown("---")
    st.markdown("### ⚙️ Download Options")

    downloader = YouTubeDownloader(
        BASE_DOWNLOAD_DIR,
        cookies_file=st.session_state.cookies_file or None,
        cookies_from_browser=st.session_state.cookies_from_browser or None,
    )
    qualities = downloader.get_available_qualities(info.get("formats", []))

    col1, col2 = st.columns(2)
    with col1:
        quality_choice = st.selectbox("🎚️ Video Quality", options=qualities, index=0)
    with col2:
        download_type = st.selectbox("📦 Download Type", options=["MP4 Video", "MP3 Audio"], index=0)

    download_clicked = st.button("⬇️ Download", type="primary", use_container_width=True)

    if not download_clicked:
        return

    if not is_ffmpeg_installed():
        st.error(
            "FFmpeg is required to merge video/audio and convert to MP3, but it "
            "was not found on this system. Please install FFmpeg and try again.",
            icon="⚠️",
        )
        return

    session_dir = os.path.join(BASE_DOWNLOAD_DIR, st.session_state.session_id)
    clear_directory(session_dir)
    ensure_directory(session_dir)

    progress_bar = st.progress(0.0)
    status_text = st.empty()
    details_text = st.empty()
    hook = make_progress_hook(progress_bar, status_text, details_text)

    try:
        with st.spinner("Preparing download..."):
            if download_type == "MP3 Audio":
                output_path = downloader.download_audio(
                    st.session_state.last_url,
                    session_dir,
                    progress_callback=hook,
                    bitrate_kbps=320,
                )
            else:
                output_path = downloader.download_video(
                    st.session_state.last_url,
                    quality_choice,
                    session_dir,
                    progress_callback=hook,
                )
    except AgeRestrictedError as exc:
        st.error(str(exc), icon="🔞")
        return
    except VideoUnavailableError as exc:
        st.error(str(exc), icon="🚫")
        return
    except NetworkError as exc:
        st.error(str(exc), icon="🌐")
        return
    except DownloaderError as exc:
        st.error(f"Download failed: {exc}", icon="⚠️")
        return

    if not output_path or not os.path.isfile(output_path):
        found = find_downloaded_file(session_dir)
        if found:
            output_path = found
        else:
            st.error("Download finished but the output file could not be located.", icon="⚠️")
            return

    status_text.markdown("**Status:** ✅ Complete!")
    details_text.markdown(f"**Final size:** {format_bytes(os.path.getsize(output_path))}")

    st.session_state.download_ready = True
    st.session_state.downloaded_file_path = output_path
    st.session_state.downloaded_file_name = os.path.basename(output_path)

    st.success("Your file is ready to download below.", icon="🎉")


def render_download_button() -> None:
    """Render the final Streamlit download button once a file is ready."""
    if not st.session_state.download_ready or not st.session_state.downloaded_file_path:
        return

    file_path = st.session_state.downloaded_file_path
    if not os.path.isfile(file_path):
        return

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    st.download_button(
        label=f"💾 Save '{st.session_state.downloaded_file_name}' to your device",
        data=file_bytes,
        file_name=st.session_state.downloaded_file_name,
        mime="application/octet-stream",
        use_container_width=True,
        type="primary",
    )

    st.caption(
        "Note: the temporary server-side copy of this file will be cleaned up "
        "automatically. Use the button above to save it to your device now."
    )


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #

def cleanup_old_sessions(max_age_seconds: int = 3600) -> None:
    """
    Remove stale per-session download folders that are older than `max_age_seconds`,
    to prevent the downloads directory from growing unbounded over time.
    """
    if not os.path.isdir(BASE_DOWNLOAD_DIR):
        return
    now = time.time()
    for entry in os.listdir(BASE_DOWNLOAD_DIR):
        full_path = os.path.join(BASE_DOWNLOAD_DIR, entry)
        if entry == st.session_state.get("session_id"):
            continue  # never delete the active session's folder mid-use
        if os.path.isdir(full_path):
            try:
                age = now - os.path.getmtime(full_path)
                if age > max_age_seconds:
                    clear_directory(full_path)
            except OSError:
                continue


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    inject_custom_css()
    init_session_state()
    cleanup_old_sessions()

    st.markdown('<p class="main-title">🎬 YouTube Downloader</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitle">Download YouTube videos in up to 4K, or extract '
        "audio as high-quality MP3 — fast, clean, and simple.</p>",
        unsafe_allow_html=True,
    )

    render_sidebar()
    fetch_video_section()

    if st.session_state.video_info:
        render_video_details()
        download_options_section()
        render_download_button()

    st.markdown("---")
    st.caption(
        "⚖️ Only download content you own or have explicit permission to download, "
        "in compliance with YouTube's Terms of Service and applicable copyright law."
    )


if __name__ == "__main__":
    main()