# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

from dbus_fast.aio import MessageBus
from dbus_fast import BusType, Variant
from loguru import logger

async def ping_session_manager():
    """Check if the container session manager is running"""
    bus = None
    try:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()

        introspection = await bus.introspect('io.furios.Andromeda.Session', '/SessionManager')
        proxy = bus.get_proxy_object('io.furios.Andromeda.Session', '/SessionManager', introspection)
        interface = proxy.get_interface('io.furios.Andromeda.SessionManager')

        await interface.call_ping()

        bus.disconnect()

        return True
    except Exception as e:
        logger.error(f"Container session manager is not started: {e}")
        return False

async def install_app(package_path):
    """Install an app in the container"""
    try:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()

        introspection = await bus.introspect('io.furios.Andromeda.Session', '/SessionManager')
        proxy = bus.get_proxy_object('io.furios.Andromeda.Session', '/SessionManager', introspection)
        interface = proxy.get_interface('io.furios.Andromeda.SessionManager')

        await interface.call_install_app(package_path)

        bus.disconnect()
        logger.success(f"Successfully installed {package_path}")
        return True
    except Exception as e:
        logger.error(f"Error installing app: {e}")
        return False

async def remove_app(package_name):
    """Remove an app from the container"""
    try:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()

        introspection = await bus.introspect('io.furios.Andromeda.Session', '/SessionManager')
        proxy = bus.get_proxy_object('io.furios.Andromeda.Session', '/SessionManager', introspection)
        interface = proxy.get_interface('io.furios.Andromeda.SessionManager')

        await interface.call_remove_app(package_name)

        bus.disconnect()
        logger.success(f"Successfully removed {package_name}")
        return True
    except Exception as e:
        logger.error(f"Error removing app: {e}")
        return False

async def get_apps_info():
    """Get information about installed apps"""
    try:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await bus.introspect('io.furios.Andromeda.Session', '/SessionManager')
        proxy = bus.get_proxy_object('io.furios.Andromeda.Session', '/SessionManager', introspection)
        interface = proxy.get_interface('io.furios.Andromeda.SessionManager')

        apps_info = await interface.call_get_apps_info()
        result = []

        for app in apps_info:
            app_info = {
                'id': Variant('s', app['packageName'].value),
                'packageName': Variant('s', app['packageName'].value),
                'name': Variant('s', app['name'].value),
                'versionName': Variant('s', app['versionName'].value),
                'state': Variant('s', 'installed')
            }
            result.append(app_info)

        bus.disconnect()
        return result
    except Exception as e:
        logger.error(f"Error getting apps info: {e}")
        return []

async def compare_installed_with_repo(db, json_decoder):
    """Compare installed apps with repository versions to find upgradable apps"""
    upgradable = []
    installed_apps = await get_apps_info()

    if not installed_apps:
        logger.warning("No installed apps found")
        return upgradable

    for app in installed_apps:
        package_name = app['packageName'].value
        current_version = app['versionName'].value

        async with db.execute(
            "SELECT repository, package, package_id, repository_url FROM apps WHERE package_id = ?",
            (package_name,)
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            repository, package_json, package_id, repository_url = row
            if not package_json:
                continue

            available_pkg = json_decoder(package_json)
            repo_version = available_pkg.get("version", "N/A")

            if repo_version != current_version:
                upgradable_info = {
                    'id': package_name,
                    'packageInfo': available_pkg,
                    'repo_url': repository_url,
                    'current_version': current_version,
                    'available_version': repo_version,
                    'name': app['name'].value,
                }
                upgradable.append(upgradable_info)
                break
    return upgradable
