# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import os
from inspect import currentframe
from time import time

def store_print(message, verbose):
    if not verbose:
        return

    frame = currentframe()
    caller_frame = frame.f_back

    bus_name = None

    if 'self' in caller_frame.f_locals:
        cls = caller_frame.f_locals['self']
        cls_name = cls.__class__.__name__

        if hasattr(cls, 'bus') and cls.bus:
            bus_name = cls.bus._requested_name if hasattr(cls.bus, '_requested_name') else None
        elif hasattr(cls, '_interface_name'):
            bus_name = cls._interface_name

        func_name = caller_frame.f_code.co_name

        if bus_name:
            full_message = f"[{bus_name}] {cls_name}.{func_name}: {message}"
        else:
            full_message = f"{cls_name}.{func_name}: {message}"
    else:
        func_name = caller_frame.f_code.co_name
        full_message = f"{func_name}: {message}"
    print(f"{time()} {full_message}")

async def download_file(session, url, output_path, verbose=False):
    """
    Download a file from a URL to the specified path.

    Args:
        session: aiohttp ClientSession
        url: URL to download from
        output_path: Path to save the file
        verbose: Whether to print verbose logs

    Returns:
        True if download was successful, False otherwise
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                store_print(f"Error downloading file: HTTP {response.status}", verbose)
                return False

            # Download the file
            with open(output_path, 'wb') as f:
                total = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 65536

                async for chunk in response.content.iter_chunked(chunk_size):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        progress = int(downloaded * 100 / total)
                        store_print(f"Download progress: {progress}%", verbose)

            return True
    except Exception as e:
        store_print(f"Error downloading file: {e}", verbose)
        if os.path.exists(output_path):
            os.remove(output_path)
        return False
