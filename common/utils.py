# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import hashlib
import os
import time
from urllib.parse import urlparse

from loguru import logger

ICON_CACHE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days, matches gnome-software's icon cache


async def cache_icon(session, icon_url, cache_dir):
    """
    Download an icon into a local cache and return its file path.

    gnome-software only renders remote icons after its own background
    download plus a widget repaint, so clients get a ready-to-use local
    file instead. Cached files are reused until ICON_CACHE_MAX_AGE.

    Args:
        session: aiohttp ClientSession
        icon_url: HTTP(S) URL of the icon
        cache_dir: Directory to store cached icons in

    Returns:
        Path of the cached icon, or an empty string if unavailable
    """
    if not icon_url or not icon_url.startswith(("http://", "https://")):
        return ""

    ext = os.path.splitext(urlparse(icon_url).path)[1] or ".png"
    filename = hashlib.sha1(icon_url.encode()).hexdigest() + ext
    filepath = os.path.join(cache_dir, filename)

    try:
        stat = os.stat(filepath)
        if stat.st_size > 0 and time.time() - stat.st_mtime < ICON_CACHE_MAX_AGE:
            return filepath
    except OSError:
        pass

    os.makedirs(cache_dir, exist_ok=True)
    if await download_file(session, icon_url, filepath):
        return filepath
    return ""


async def download_file(
    session, url, output_path, headers=None, progress_callback=None
):
    """
    Download a file from a URL to the specified path.

    Args:
        session: aiohttp ClientSession
        url: URL to download from
        output_path: Path to save the file
        headers: Optional dict of HTTP headers to include in the request

    Returns:
        True if download was successful, False otherwise
    """
    try:
        # choose whether to pass headers
        if headers is not None:
            req = session.get(url, headers=headers)
        else:
            req = session.get(url)

        async with req as response:
            if response.status != 200:
                logger.error(f"Error downloading file: HTTP {response.status}")
                return False

            # Download the file in chunks
            with open(output_path, "wb") as f:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 65536
                last_progress = -1

                async for chunk in response.content.iter_chunked(chunk_size):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        progress = int(downloaded * 100 / total)
                        logger.trace(f"Download progress: {progress}%")
                        if progress_callback and progress != last_progress:
                            progress_callback(progress)
                            last_progress = progress
            return True
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False
