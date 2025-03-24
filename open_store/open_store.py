# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>

from pathlib import Path
from time import time
import tempfile
import asyncio
import aiohttp
import shutil
import json
import sys
import os

from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method, signal
from dbus_fast import BusType, Variant

from loguru import logger

from common.utils import download_file
from open_store.database import (
    init_app_database, init_installed_database, save_app_list,
    search_apps, save_installed_app, remove_installed_app,
    get_installed_apps, get_installed_app
)
from open_store.api import fetch_app_list, get_app_details
from open_store.click import (
    extract_click_package, get_system_architecture,
    find_compatible_download,
    process_desktop_files, cleanup_desktop_files
)

DATABASE = os.path.expanduser("~/.cache/store-provider/open-store/open-store.db")
CACHE_DIR = os.path.expanduser("~/.cache/store-provider/open-store/repo")
DOWNLOAD_DIR = os.path.expanduser("~/.cache/store-provider/open-store/downloads")
INSTALLED_DB = os.path.expanduser("~/.local/store-provider/open-store/apps.db")
APPS_DIR = os.path.expanduser("~/.local/store-provider/open-store")
IDLE_TIMEOUT = 120
OPENSTORE_API_URL = "https://open-store.io/api/v4/apps"

class OpenStoreInterface(ServiceInterface):
    def __init__(self, idle_callback=None):
        logger.info("Initializing OpenStore service")
        super().__init__('io.FuriOS.OpenStore')
        self.session = None
        self.db = None
        self.installed_db = None

        # Get current system architecture
        self.system_arch = get_system_architecture()
        logger.info(f"Detected system architecture: {self.system_arch}")

        self.idle_callback = idle_callback
        self.idle_timer = None

        # Task queue implementation
        self._task_queue = asyncio.Queue()
        self._task_processor = None
        self._running = False

        # Start the task processor
        self._start_task_processor()

        # Start the idle timer
        self._reset_idle_timer()

    async def init_db(self):
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        os.makedirs(os.path.dirname(INSTALLED_DB), exist_ok=True)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        self.db = await init_app_database(DATABASE)
        self.installed_db = await init_installed_database(INSTALLED_DB)

        cursor = await self.db.execute("SELECT COUNT(*) FROM apps")
        count = await cursor.fetchone()
        if count[0] == 0:
            logger.warning("Apps table is empty, fetching data from API")
            await self.fetch_all_apps()

    async def ensure_session(self):
        """Ensure HTTP session exists"""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Clean up HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

    def _start_task_processor(self):
        """Start the async task processor if it's not already running"""
        if not self._running:
            self._running = True
            self._task_processor = asyncio.create_task(self._process_task_queue())
            logger.info("Task processor started")

    def _reset_idle_timer(self):
        """Reset the idle timer when activity occurs"""
        if self.idle_callback:
            asyncio.create_task(self.idle_callback())

    async def _process_task_queue(self):
        """Process tasks in queue one at a time"""
        while self._running:
            try:
                # Get next task from queue
                task, future = await self._task_queue.get()

                # Reset idle timer on activity
                self._reset_idle_timer()

                try:
                    # Execute the task
                    result = await task()

                    # Set the result for the waiting caller
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                    logger.error(f"Task error: {e}")

                # Mark task as done
                self._task_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Task processor error: {e}")

    async def _queue_task(self, task_func):
        """Queue a task and wait for its result"""
        future = asyncio.Future()
        await self._task_queue.put((task_func, future))

        # Reset idle timer on activity
        self._reset_idle_timer()

        # Wait for the task to complete and return its result
        return await future

    async def fetch_all_apps(self):
        """Fetch all apps from the OpenStore API"""
        await self.ensure_session()
        apps = await fetch_app_list(self.session)

        if apps:
            await save_app_list(self.db, apps)
            return True

        return False

    async def download_app(self, download_url, app_id, version, output_dir):
        await self.ensure_session()

        try:
            click_filename = f"{app_id}-{version}.click"
            output_path = os.path.join(output_dir, click_filename)

            success = await download_file(self.session, download_url, output_path)

            if success:
                return output_path
            else:
                return None
        except Exception as e:
            logger.error(f"Error downloading app: {e}")
            return None

    @method()
    async def Search(self, query: 's') -> 's':
        async def _search_task():
            logger.info(f"Searching for {query}")

            cursor = await self.db.execute("SELECT COUNT(*) FROM apps")
            count = await cursor.fetchone()
            if count[0] == 0:
                logger.warning("No apps in database, fetching first")
                await self.fetch_all_apps()

            results = await search_apps(self.db, query)

            return json.dumps(results)

        return await self._queue_task(_search_task)

    @method()
    async def GetRepositories(self) -> 'a(ss)':
        async def _get_repositories_task():
            logger.info("Getting repositories")
            # For now, just return OpenStore as the only repository
            return [["OpenStore", "https://open-store.io"]]

        return await self._queue_task(_get_repositories_task)

    @method()
    async def UpdateCache(self) -> 'b':
        async def _update_cache_task():
            logger.info("Updating cache")
            try:
                result = await self.fetch_all_apps()
                return result
            except Exception as e:
                logger.error(f"Error updating cache: {e}")
                return False

        return await self._queue_task(_update_cache_task)

    @method()
    async def Install(self, package_id: 's') -> 'b':
        async def _install_task():
            logger.info(f"Installing package {package_id}")

            await self.ensure_session()
            app_details = await get_app_details(self.session, package_id)

            if not app_details:
                logger.error(f"Could not get app details for {package_id}")
                return False

            downloads = app_details.get('downloads', [])
            if not downloads:
                logger.error(f"No downloads available for {package_id}")
                return False

            compatible_download = find_compatible_download(downloads, self.system_arch)
            if not compatible_download:
                logger.error(f"No compatible download found for {package_id} on {self.system_arch}")
                return False

            download_url = compatible_download.get('download_url')
            version = compatible_download.get('version', '0.0.0')
            arch = compatible_download.get('architecture')
            channel = compatible_download.get('channel')

            if not download_url:
                logger.error(f"No download URL for {package_id}")
                return False

            # Create a temporary directory for downloading the click package
            with tempfile.TemporaryDirectory() as temp_download_dir:
                logger.info(f"Downloading {download_url} for architecture {arch}")
                click_path = await self.download_app(download_url, package_id, version, temp_download_dir)

                if not click_path:
                    logger.error(f"Failed to download {package_id}")
                    return False

                try:
                    # Check for existing installation and clean up
                    old_app = await get_installed_app(self.installed_db, package_id)

                    if old_app:
                        old_app_dir = old_app['app_dir']

                        await cleanup_desktop_files(package_id)

                        # Remove old app directory
                        if old_app_dir and os.path.exists(old_app_dir):
                            try:
                                shutil.rmtree(old_app_dir)
                                logger.info(f"Removed old app directory: {old_app_dir}")
                            except Exception as e:
                                logger.error(f"Error removing old app directory: {e}")
                except Exception as e:
                    logger.error(f"Error checking for old version: {e}")

                app_dir = os.path.join(APPS_DIR, package_id)
                os.makedirs(app_dir, exist_ok=True)

                # Extract the click package
                extracted_dir = await extract_click_package(click_path, app_dir)
                if not extracted_dir:
                    logger.error(f"Failed to extract {package_id}")
                    return False

                # Process desktop files
                desktop_files = await process_desktop_files(package_id, app_dir)
                logger.info(f"Processed {len(desktop_files)} desktop files for {package_id}")

                # Save app info to database (without click_path)
                current_time = time()
                success = await save_installed_app(
                    self.installed_db,
                    package_id,
                    app_details.get('name', ''),
                    version,
                    channel,
                    arch,
                    current_time,
                    app_dir
                )

                if success:
                    self.AppInstalled(package_id)
                    logger.success(f"Successfully installed {package_id} version {version} for {arch}")
                    return True
                else:
                    logger.error("Error saving installation details")
                    return False

        return await self._queue_task(_install_task)

    @signal()
    def AppInstalled(self, package_id: 's') -> 's':
        return package_id

    @method()
    async def GetUpgradable(self) -> 'aa{sv}':
        async def _get_upgradable_task():
            logger.info("Getting upgradable apps")
            upgradable = []

            try:
                installed_apps = await get_installed_apps(self.installed_db)
                await self.ensure_session()

                for app in installed_apps:
                    app_id = app['id']
                    app_name = app['name']
                    current_version = app['version']
                    channel = app['channel']
                    architecture = app['architecture']

                    app_details = await get_app_details(self.session, app_id)
                    if not app_details:
                        continue

                    downloads = app_details.get('downloads', [])
                    compatible_downloads = [d for d in downloads if
                                            d.get('architecture') == architecture or
                                            d.get('architecture') == 'all']

                    if not compatible_downloads:
                        continue

                    latest_version = None
                    latest_download = None

                    channel_downloads = [d for d in compatible_downloads if d.get('channel') == channel]
                    if channel_downloads:
                        latest_download = max(channel_downloads, key=lambda x: int(x.get('revision', 0)))
                        latest_version = latest_download.get('version', '0.0.0')
                    else:
                        # If no match by channel, try focal
                        focal_downloads = [d for d in compatible_downloads if d.get('channel') == 'focal']
                        if focal_downloads:
                            latest_download = max(focal_downloads, key=lambda x: int(x.get('revision', 0)))
                            latest_version = latest_download.get('version', '0.0.0')
                        # If no focal either, just get the latest revision
                        else:
                            latest_download = max(compatible_downloads, key=lambda x: int(x.get('revision', 0)))
                            latest_version = latest_download.get('version', '0.0.0')

                    if latest_version != current_version:
                        app_info = {
                            'id': Variant('s', app_id),
                            'name': Variant('s', app_name),
                            'packageName': Variant('s', app_id),
                            'currentVersion': Variant('s', current_version),
                            'availableVersion': Variant('s', latest_version),
                            'architecture': Variant('s', architecture),
                            'repository': Variant('s', 'OpenStore'),
                            'download_url': Variant('s', latest_download.get('download_url', '')),
                            'channel': Variant('s', latest_download.get('channel', ''))
                        }
                        upgradable.append(app_info)
                        logger.info(f"Upgradable: {app_id} from {current_version} to {latest_version}")

                return upgradable
            except Exception as e:
                logger.error(f"Error getting upgradable apps: {e}")
                return []

        return await self._queue_task(_get_upgradable_task)

    @method()
    async def UpgradePackages(self, packages: 'as') -> 'b':
        async def _upgrade_packages_task():
            logger.info(f"Upgrading packages {packages}")

            upgrade_list = packages
            if not upgrade_list:
                upgradable = await self.GetUpgradable()
                upgrade_list = [app['id'].value for app in upgradable]

            if not upgrade_list:
                logger.info("No packages to upgrade")
                return True

            logger.info(f"Upgrading packages: {', '.join(upgrade_list)}")

            success = True
            for package_id in upgrade_list:
                if not await self.Install(package_id):
                    logger.error(f"Failed to upgrade {package_id}")
                    success = False
            return success
        return await self._queue_task(_upgrade_packages_task)

    @method()
    async def GetInstalledApps(self) -> 'aa{sv}':
        async def _get_installed_apps_task():
            logger.info("Getting installed apps")
            result = []

            try:
                installed_apps = await get_installed_apps(self.installed_db)
                for app in installed_apps:
                    app_info = {
                        'id': Variant('s', app['id']),
                        'packageName': Variant('s', app['id']),
                        'name': Variant('s', app['name']),
                        'versionName': Variant('s', app['version']),
                        'channel': Variant('s', app['channel']),
                        'architecture': Variant('s', app['architecture']),
                        'installDate': Variant('d', float(app['install_date'])),
                        'state': Variant('s', 'installed')
                    }
                    result.append(app_info)

                return result
            except Exception as e:
                logger.error(f"Error getting installed apps: {e}")
                return []

        return await self._queue_task(_get_installed_apps_task)

    @method()
    async def UninstallApp(self, package_name: 's') -> 'b':
        async def _uninstall_app_task():
            logger.info(f"Uninstalling app {package_name}")

            try:
                app = await get_installed_app(self.installed_db, package_name)
                if not app:
                    logger.error(f"App {package_name} not found in installed apps")
                    return False

                app_dir = app['app_dir']
                await cleanup_desktop_files(package_name)
                await remove_installed_app(self.installed_db, package_name)

                if app_dir and os.path.exists(app_dir):
                    try:
                        shutil.rmtree(app_dir)
                        logger.info(f"Removed app directory: {app_dir}")
                    except Exception as e:
                        logger.error(f"Error removing app directory: {e}")

                logger.success(f"Successfully uninstalled {package_name}")
                return True
            except Exception as e:
                logger.error(f"Error uninstalling app: {e}")
                return False

        return await self._queue_task(_uninstall_app_task)

    async def cleanup(self):
        """Clean up resources when service is stopping"""
        self._running = False
        if self.idle_timer:
            self.idle_timer.cancel()
        if self._task_processor:
            self._task_processor.cancel()
            try:
                await self._task_processor
            except asyncio.CancelledError:
                pass
        await self.cleanup_session()
        if self.db:
            await self.db.close()
        if hasattr(self, 'installed_db') and self.installed_db:
            await self.installed_db.close()

class OpenStoreService:
    def __init__(self, idle_callback=None):
        logger.info("Initializing OpenStore service")
        self.bus = None
        self.openstore_interface = None
        self.idle_callback = idle_callback

    async def setup(self):
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self.openstore_interface = OpenStoreInterface(
            idle_callback=self.idle_callback
        )

        await self.openstore_interface.init_db()
        self.bus.export('/', self.openstore_interface)
        await self.bus.request_name('io.FuriOS.OpenStore')

        return self.bus

    async def cleanup(self):
        """Clean up resources"""
        if self.openstore_interface:
            await self.openstore_interface.cleanup()
