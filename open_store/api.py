# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>

import aiohttp
import json
from loguru import logger

OPENSTORE_API_URL = "https://open-store.io/api/v4/apps"

async def fetch_app_list(session):
    """
    Fetch the list of apps from the OpenStore API.

    Args:
        session: aiohttp ClientSession

    Returns:
        List of apps
    """
    apps = []
    next_url = OPENSTORE_API_URL
    page_count = 0

    while next_url:
        try:
            logger.info(f"Fetching page {page_count + 1} from {next_url}")
            async with session.get(next_url) as response:
                if response.status != 200:
                    logger.error(f"Error fetching apps: HTTP {response.status}")
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
            logger.error(f"Error fetching apps: {e}")
            break

    logger.info(f"Fetched {len(apps)} apps in {page_count} pages")
    return apps

async def get_app_details(session, app_id):
    """
    Get detailed information about an app.

    Args:
        session: aiohttp ClientSession
        app_id: App ID

    Returns:
        App details or None if not found
    """
    url = f"{OPENSTORE_API_URL}/{app_id}"

    try:
        logger.info(f"Fetching app details for {app_id}")
        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Error fetching app details: HTTP {response.status}")
                return None

            data = await response.json()
            if not data.get('success'):
                logger.error(f"API returned error: {data.get('message')}")
                return None

            return data.get('data')
    except Exception as e:
        logger.error(f"Error fetching app details: {e}")
        return None
