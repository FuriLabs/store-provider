# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import os
import aiofiles
import msgspec
from common.utils import store_print

async def download_file(session, url, file_path, verbose=False):
    """Download a file from a URL to a file path"""
    try:
        downloaded = 0
        previous_progress = 0
        async with session.get(url) as response:
            if response.status == 200:
                download_size = response.headers.get('Content-Length', 0)
                with open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

                        if download_size:
                            downloaded += len(chunk)
                            progress = int((downloaded / int(download_size)) * 100)

                            if progress != previous_progress:
                                store_print(f"Downloading {url}: {progress}%", verbose)
                                previous_progress = progress
                return True
            else:
                store_print(f"Download failed with status {response.status}: {url}", verbose)
                return False
    except Exception as e:
        store_print(f"Error downloading {url}: {e}", verbose)
        if os.path.exists(file_path):
            os.remove(file_path)
        return False

async def download_index(session, repo_url, repo_name, cache_dir, verbose=False):
    """Download repository index"""
    repo_cache_dir = os.path.join(cache_dir, repo_name)
    os.makedirs(repo_cache_dir, exist_ok=True)

    repo_url = repo_url.rstrip('/')
    index_url = f"{repo_url}/index-v2.json"
    index_path = os.path.join(repo_cache_dir, 'index-v2.json')
    url_path = os.path.join(repo_cache_dir, 'repo_url.txt')

    try:
        result = await download_file(session, index_url, index_path, verbose)

        if not result:
            return False

        async with aiofiles.open(url_path, 'w') as f:
            await f.write(repo_url)

        return True
    except Exception as e:
        store_print(f"Error downloading index for {repo_url}: {e}", verbose)
        return False

def get_localized_text(text_obj, lang='en-US'):
    """Get localized text from a text object"""
    if isinstance(text_obj, dict):
        return text_obj.get(lang, list(text_obj.values())[0] if text_obj else 'N/A')
    return text_obj if text_obj else 'N/A'

def get_latest_version(versions):
    """Get the latest version from a versions object"""
    if not versions:
        return None

    latest = sorted(
        versions.items(),
        key=lambda x: x[1]['manifest']['versionCode'] if 'versionCode' in x[1]['manifest'] else 0,
        reverse=True
    )[0]

    return latest[1]

def get_package_info(package_id, metadata, version_info, repository_url):
    """Get package information"""
    apk_name = version_info['file']['name']
    download_url = f"{repository_url}{apk_name}"

    icon_url = 'N/A'
    if 'icon' in metadata:
        icon_path = get_localized_text(metadata['icon'])
        if isinstance(icon_path, dict) and 'name' in icon_path:
            icon_url = f"{repository_url}{icon_path['name']}"

    manifest = version_info['manifest']
    return {
        'apk_name': apk_name.lstrip('/'),
        'download_url': download_url,
        'icon_url': icon_url,
        'version': manifest.get('versionName', 'N/A'),
        'version_code': manifest.get('versionCode', 'N/A'),
        'size': version_info['file'].get('size', 'N/A'),
        'min_sdk': manifest.get('usesSdk', {}).get('minSdkVersion', 'N/A'),
        'target_sdk': manifest.get('usesSdk', {}).get('targetSdkVersion', 'N/A'),
        'permissions': [p['name'] for p in manifest.get('usesPermission', []) if isinstance(p, dict)],
        'features': manifest.get('features', []),
        'hash': version_info['file'].get('sha256', 'N/A'),
        'hash_type': 'sha256'
    }

async def process_indexes(cache_dir, json_enc, verbose=False):
    """Process repository indexes and extract package information"""
    rows = []

    for repo_dir in os.listdir(cache_dir):
        repo_path = os.path.join(cache_dir, repo_dir)
        index_path = os.path.join(repo_path, 'index-v2.json')
        url_path = os.path.join(repo_path, 'repo_url.txt')

        if not os.path.exists(index_path) or not os.path.exists(url_path):
            continue

        try:
            async with aiofiles.open(index_path, 'rb') as f:
                raw_data = await f.read()
            index_data = msgspec.json.decode(raw_data)

            async with aiofiles.open(url_path, 'r') as f:
                repository_url = await f.read()
        except Exception as e:
            store_print(f"Error processing {index_path}: {e}", verbose)
            continue

        for package_id, package_data in index_data.get("packages", {}).items():
            name = get_localized_text(package_data["metadata"].get("name", ""))
            latest_version = get_latest_version(package_data["versions"])
            if not latest_version:
                continue

            package_info = get_package_info(package_id, package_data["metadata"], latest_version, repository_url)
            row = {
                "repository": repo_dir,
                "package_id": package_id,
                "repository_url": repository_url,
                "name": name,
                "summary": get_localized_text(package_data["metadata"].get("summary", "N/A")),
                "description": get_localized_text(package_data["metadata"].get("description", "N/A")),
                "license": package_data["metadata"].get("license", "N/A"),
                "categories": json_enc.encode(package_data["metadata"].get("categories", [])),
                "author": package_data["metadata"].get("author", {}).get("name", "N/A"),
                "web_url": package_data["metadata"].get("webSite", "N/A"),
                "source_url": package_data["metadata"].get("sourceCode", "N/A"),
                "tracker_url": package_data["metadata"].get("issueTracker", "N/A"),
                "changelog_url": package_data["metadata"].get("changelog", "N/A"),
                "donation_url": json_enc.encode(package_data["metadata"].get("donate", [])),
                "added_date": package_data["metadata"].get("added", "N/A"),
                "last_updated": package_data["metadata"].get("lastUpdated", "N/A"),
                "package": json_enc.encode(package_info),
            }
            rows.append(row)

        os.remove(index_path)
        os.remove(url_path)
    return rows

def read_repo_list(repo_file, repo_dir):
    """Read repository list from a file"""
    try:
        with open(os.path.join(repo_dir, repo_file), 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []
