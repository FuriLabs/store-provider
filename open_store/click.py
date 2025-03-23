# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>

from pathlib import Path
import subprocess
import tempfile
import platform
import tarfile
import asyncio
import shlex
import glob
import stat
import os

from common.utils import store_print

async def extract_click_package(click_path, target_dir, verbose=False):
    """
    Extract a click package to the target directory.

    Args:
        click_path: Path to the .click file
        target_dir: Directory to extract contents to
        verbose: Whether to print verbose logs

    Returns:
        Path to the extracted directory or None if extraction failed
    """
    os.makedirs(target_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            store_print(f"Extracting click package: {click_path}", verbose)
            subprocess.run(['ar', 'x', click_path], cwd=temp_dir, check=True)

            data_tar_path = os.path.join(temp_dir, 'data.tar.gz')
            if os.path.exists(data_tar_path):
                with tarfile.open(data_tar_path) as tar:
                    tar.extractall(path=target_dir)

                cleanup_files = ['_click-binary', 'control.tar.gz', 'debian-binary']
                for file_name in cleanup_files:
                    file_path = os.path.join(temp_dir, file_name)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            store_print(f"Error removing {file_path}: {e}", verbose)

                store_print(f"Extracted to {target_dir}", verbose)
                return target_dir
            else:
                store_print(f"data.tar.gz not found in {click_path}", verbose)
                return None
        except subprocess.CalledProcessError as e:
            store_print(f"Error extracting click package: {e}", verbose)
            return None
        except tarfile.TarError as e:
            store_print(f"Error extracting data tarball: {e}", verbose)
            return None

def get_system_architecture():
    """
    Get the current system architecture and map it to OpenStore architecture names.

    Returns:
        String representation of the architecture (arm64, armhf, amd64, or all)
    """
    arch_mapping = {
        'aarch64': 'arm64',
        'armv7l': 'armhf',
        'x86_64': 'amd64'
    }
    return arch_mapping.get(platform.machine(), 'all')

def find_compatible_download(downloads, system_arch, prefer_focal=True):
    """
    Find the best download option based on architecture and channel preferences.

    Args:
        downloads: List of download options
        system_arch: Current system architecture
        prefer_focal: Whether to prefer focal channel

    Returns:
        Best matching download or None if no match found
    """
    if prefer_focal:
        for download in downloads:
            if (download.get('channel') == 'focal' and 
                (download.get('architecture') == system_arch or download.get('architecture') == 'all')):
                return download

    for download in downloads:
        if download.get('architecture') == system_arch or download.get('architecture') == 'all':
            return download

    return None

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

async def process_desktop_files(app_id, app_dir, verbose=False):
    """
    Process desktop files in the extracted click package.

    For each desktop file found:
    1. Read and parse the content
    2. Create a wrapper script to set up environment variables
    3. Create a modified version with absolute paths in ~/.local/open-store/applications/
    4. Create a symlink to ~/.local/share/applications/

    Args:
        app_id: App ID
        app_dir: Path to the extracted app directory
        verbose: Whether to print verbose logs

    Returns:
        List of created desktop files and symlinks
    """
    results = []

    store_apps_dir = os.path.expanduser("~/.local/open-store/applications")
    system_apps_dir = os.path.expanduser("~/.local/share/applications")
    scripts_dir = os.path.expanduser("~/.local/open-store/scripts")

    os.makedirs(store_apps_dir, exist_ok=True)
    os.makedirs(system_apps_dir, exist_ok=True)
    os.makedirs(scripts_dir, exist_ok=True)

    desktop_files = glob.glob(os.path.join(app_dir, "**/*.desktop"), recursive=True)

    if not desktop_files:
        store_print(f"No desktop files found for {app_id}", verbose)
        return results

    for desktop_file in desktop_files:
        try:
            desktop_content = {}
            current_section = None

            with open(desktop_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1]
                        desktop_content[current_section] = {}
                    elif '=' in line and current_section:
                        key, value = line.split('=', 1)
                        desktop_content[current_section][key.strip()] = value.strip()

            if 'Desktop Entry' not in desktop_content:
                store_print(f"Invalid desktop file (no Desktop Entry section): {desktop_file}", verbose)
                continue

            desktop_filename = os.path.basename(desktop_file)
            script_basename = f"{app_id}_{os.path.splitext(desktop_filename)[0]}"
            script_path = os.path.join(scripts_dir, f"{script_basename}.sh")
            store_desktop_path = os.path.join(store_apps_dir, f"{app_id}_{desktop_filename}")
            system_desktop_path = os.path.join(system_apps_dir, f"{app_id}_{desktop_filename}")

            entry = desktop_content['Desktop Entry']
            name = entry.get('Name', app_id)
            exec_cmd = entry.get('Exec', '')
            icon = entry.get('Icon', '')

            with open(script_path, 'w') as f:
                f.write("#!/bin/bash\n\n")
                f.write("# Script generated by OpenStore to launch app with the right enrionment variables\n\n")
                f.write("TRIPLET=$(awk 'BEGIN{FS=\"[ ()-]\"; \"bash --version\"|getline; OFS=\"-\"; if (/bash/) print $9,$11,$12}')\n\n")
                f.write(f"cd {app_dir}\n\n")
                f.write("export LD_LIBRARY_PATH=${PWD}/lib:${PWD}/usr/lib:${PWD}/lib/${TRIPLET}:${PWD}/usr/lib/${TRIPLET}:${LD_LIBRARY_PATH}\n\n")
                f.write("export PATH=${PWD}:${PWD}/bin:${PWD}/usr/bin:${PWD}/lib/bin:${PWD}/lib/${TRIPLET}/bin:${PATH}\n\n")
                f.write("export QML2_IMPORT_PATH=${PWD}/lib:${PWD}/lib/${TRIPLET}:${PWD}/usr/lib/:${PWD}/usr/lib/${TRIPLET}/\n\n")
                f.write(f"{exec_cmd}\n")

            os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            entry['Path'] = app_dir
            entry['Exec'] = script_path

            if icon and not icon.startswith('/') and not icon.startswith('$'):
                icon_path = os.path.join(app_dir, icon)
                if os.path.exists(icon_path):
                    entry['Icon'] = icon_path

            with open(store_desktop_path, 'w') as f:
                for section, keys in desktop_content.items():
                    f.write(f"[{section}]\n")
                    for key, value in keys.items():
                        f.write(f"{key}={value}\n")
                    f.write("\n")

            if os.path.exists(system_desktop_path):
                os.remove(system_desktop_path)
            os.symlink(store_desktop_path, system_desktop_path)

            store_print(f"Created wrapper script and desktop file for {name}", verbose)
            results.append({
                'name': name,
                'script_path': script_path,
                'store_desktop_path': store_desktop_path,
                'system_desktop_path': system_desktop_path
            })
        except Exception as e:
            store_print(f"Error processing desktop file {desktop_file}: {e}", verbose)
    return results

async def cleanup_desktop_files(app_id, verbose=False):
    """
    Clean up desktop files and symlinks for an app.

    Args:
        app_id: App ID
        verbose: Whether to print verbose logs

    Returns:
        True if successful, False otherwise
    """

    try:
        store_apps_dir = os.path.expanduser("~/.local/open-store/applications")
        system_apps_dir = os.path.expanduser("~/.local/share/applications")
        scripts_dir = os.path.expanduser("~/.local/open-store/scripts")

        pattern = f"{app_id}_*.desktop"
        script_pattern = f"{app_id}_*.sh"

        store_desktop_files = glob.glob(os.path.join(store_apps_dir, pattern))
        system_desktop_files = glob.glob(os.path.join(system_apps_dir, pattern))
        script_files = glob.glob(os.path.join(scripts_dir, script_pattern))

        for desktop_file in system_desktop_files:
            if os.path.islink(desktop_file):
                os.remove(desktop_file)
                store_print(f"Removed desktop file symlink: {desktop_file}", verbose)

        for desktop_file in store_desktop_files:
            os.remove(desktop_file)
            store_print(f"Removed desktop file: {desktop_file}", verbose)

        for script_file in script_files:
            os.remove(script_file)
            store_print(f"Removed wrapper script: {script_file}", verbose)

        return True
    except Exception as e:
        store_print(f"Error cleaning up desktop files for {app_id}: {e}", verbose)
        return False
