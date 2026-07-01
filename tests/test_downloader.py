import os
import tempfile
import unittest

from downloader import YouTubeDownloader


class YouTubeDownloaderTests(unittest.TestCase):
    def test_build_common_options_includes_cookie_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cookie_path = os.path.join(tmpdir, "cookies.txt")
            with open(cookie_path, "w", encoding="utf-8") as handle:
                handle.write("# Netscape HTTP Cookie File")

            downloader = YouTubeDownloader(tmpdir, cookies_file=cookie_path)
            options = downloader._build_common_options()

            self.assertEqual(options["cookies"], cookie_path)
            self.assertIn("extractor_args", options)
            self.assertIn("youtube", options["extractor_args"])

    def test_build_common_options_uses_browser_cookies_when_requested(self) -> None:
        downloader = YouTubeDownloader("/tmp", cookies_from_browser="chrome")
        options = downloader._build_common_options()

        self.assertEqual(options["cookiesfrombrowser"], ["chrome"])


if __name__ == "__main__":
    unittest.main()
