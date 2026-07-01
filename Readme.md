# 🎬 YouTube Downloader (Streamlit)

A modern, production-quality Streamlit web app for downloading YouTube videos
(up to 4K, when available) or extracting audio as 320 kbps MP3 — built on
top of [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and FFmpeg.

> ⚖️ **Use responsibly.** Only download videos you own, that are licensed for
> reuse, or that you otherwise have explicit permission to download, in
> compliance with YouTube's Terms of Service and applicable copyright law.

---

## Features

- 🔗 Paste any YouTube URL and fetch full metadata (title, channel, duration,
  upload date, views, description, thumbnail)
- 🎚️ Quality dropdown that only lists resolutions actually available for
  that specific video (up to 2160p / 4K)
- 📦 Choose between MP4 video or MP3 audio (320 kbps, via `libmp3lame`)
- 📊 Live progress bar with percentage, download speed, ETA, and file size
- 💾 Direct in-browser download via Streamlit's `download_button`
- 🧹 Automatic cleanup of temporary server-side files
- 🖥️ Sidebar with environment info (Python, yt-dlp, FFmpeg detection)
- 🛡️ Friendly error handling for invalid URLs, private/removed/age-restricted
  videos, and network issues

---

## Project Structure

```
youtube_downloader/
│
├── app.py            # Streamlit UI and orchestration
├── downloader.py      # yt-dlp wrapper: metadata + video/audio downloads
├── utils.py            # Formatting, validation, and filesystem helpers
├── requirements.txt
├── README.md
└── downloads/          # Temporary per-session download folders (auto-cleaned)
```

---

## 1. Installation

### Prerequisites

- Python 3.9+ (3.12 recommended)
- FFmpeg installed and available on your system `PATH` (required for
  merging video/audio streams and converting to MP3)

### Install Python dependencies

```bash
# (Optional but recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 2. Installing FFmpeg

The app checks for FFmpeg on startup and will show a warning in the sidebar
if it isn't found.

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Windows:**
1. Download a build from https://www.gyan.dev/ffmpeg/builds/ (or
   https://ffmpeg.org/download.html).
2. Extract it, then add the `bin` folder to your system `PATH` environment
   variable.
3. Verify with `ffmpeg -version` in a new terminal window.

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Fedora:**
```bash
sudo dnf install ffmpeg
```

**Verify installation (any OS):**
```bash
ffmpeg -version
```

---

## 3. Running the Application

From the project root:

```bash
streamlit run app.py
```

Streamlit will print a local URL (typically `http://localhost:8501`) —
open it in your browser.

---

## 4. Usage

1. Paste a YouTube URL into the input box and click **Fetch Video**.
2. Review the video's thumbnail, title, channel, duration, and other details.
3. Choose a **Video Quality** (only qualities that actually exist for that
   video are shown) and a **Download Type** (MP4 Video or MP3 Audio).
4. Click **Download** and watch the live progress bar (speed, ETA, size).
5. Once complete, click the **Save to your device** button to download the
   file through your browser.

---

## Troubleshooting

| Issue | Likely Cause / Fix |
|---|---|
| Sidebar shows "FFmpeg: Not found" | FFmpeg isn't installed or isn't on your `PATH`. Reinstall and restart your terminal/IDE. |
| "This video is age-restricted..." | Some age-restricted videos require an authenticated session and cannot be downloaded by this app. |
| "This video is private/unavailable" | The video was deleted, made private, or is region-locked. |
| "A network error occurred..." | Check your internet connection; YouTube may also be temporarily rate-limiting requests — wait and retry. |
| Download stalls at 0% | Very large 4K files can take time to start reporting progress; check your terminal for `yt-dlp` output/log messages. |
| `yt-dlp` errors mentioning format unavailable | YouTube periodically changes its site; run `pip install -U yt-dlp` to get the latest fixes. |
| MP3 conversion fails | Confirm FFmpeg is installed and includes `libmp3lame` support (`ffmpeg -codecs | grep mp3`). |

If problems persist, try upgrading `yt-dlp` to the latest version, since
YouTube frequently changes its internal APIs:

```bash
pip install -U yt-dlp
```

---

## Notes on Architecture

- **`utils.py`** — Pure helper functions (formatting, validation, filesystem
  utilities) with no Streamlit or yt-dlp dependencies, fully unit-testable.
- **`downloader.py`** — All yt-dlp interaction lives here, wrapped in a
  `YouTubeDownloader` class with custom exception types
  (`InvalidURLError`, `VideoUnavailableError`, `AgeRestrictedError`,
  `NetworkError`) so the UI layer never has to parse raw yt-dlp error text.
- **`app.py`** — Streamlit UI only. Uses `st.session_state` to persist
  fetched video info and downloaded file paths across reruns, and a
  yt-dlp `progress_hooks` callback to update the progress bar live during
  the (synchronous) download call.

---

## License / Disclaimer

This tool is provided for educational purposes and for downloading content
you have the rights to. The authors are not responsible for misuse. Always
respect content creators' rights and YouTube's Terms of Service.