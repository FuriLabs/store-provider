# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>

import aiohttp
import json

from common.utils import store_print

OPENSTORE_API_URL = "https://open-store.io/api/v4/apps"

async def fetch_app_list(session, verbose=False):
    """
    Fetch the list of apps from the OpenStore API.

    Args:
        session: aiohttp ClientSession
        verbose: Whether to print verbose logs

    Returns:
        List of apps
    """
    apps = []
    next_url = f"{OPENSTORE_API_URL}?type=app&channel=focal"
    page_count = 0

    while next_url:
        try:
            store_print(f"Fetching page {page_count + 1} from {next_url}", verbose)
            async with session.get(next_url) as response:
                if response.status != 200:
                    store_print(f"Error fetching apps: HTTP {response.status}", verbose)
                    break

                data = await response.json()

                packages = data.get('data', {}).get('packages', [])
                page_count += 1

                for app in packages:
                    # Filter apps based on criteria:
                    # 1. Type must be "app" (not webapp/webapp+)
                    # 2. Should not be xenial-only channel
                    channels = app.get('channels', [])
                    if ("app" in app.get('types', []) and
                        not any(wtype in app.get('types', []) for wtype in ["webapp", "webapp+"]) and
                        not (len(channels) == 1 and channels[0] == "xenial")):
                        apps.append(app)

                next_url = data.get('data', {}).get('next')
        except Exception as e:
            store_print(f"Error fetching apps: {e}", verbose)
            break

    store_print(f"Fetched {len(apps)} apps in {page_count} pages", verbose)
    return apps

async def get_app_details(session, app_id, verbose=False):
    """
    Get detailed information about an app.

    Args:
        session: aiohttp ClientSession
        app_id: App ID
        verbose: Whether to print verbose logs

    Returns:
        App details or None if not found
    """
    url = f"{OPENSTORE_API_URL}/{app_id}"

    try:
        store_print(f"Fetching app details for {app_id}", verbose)
        async with session.get(url) as response:
            if response.status != 200:
                store_print(f"Error fetching app details: HTTP {response.status}", verbose)
                return None

            data = await response.json()
            if not data.get('success'):
                store_print(f"API returned error: {data.get('message')}", verbose)
                return None

            return data.get('data')
    except Exception as e:
        store_print(f"Error fetching app details: {e}", verbose)
        return None
