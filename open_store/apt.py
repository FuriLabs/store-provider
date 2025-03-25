# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>

import subprocess
import asyncio

from loguru import logger

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

def is_package_installed(package_name):
    """
    Check if a Debian package is installed.

    Args:
        package_name (str): The name of the package to check

    Returns:
        bool: True if the package is installed, False otherwise
    """
    try:
        subprocess.run(['dpkg', '-s', package_name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True)
        return True
    except subprocess.CalledProcessError:
        return False

async def update_cache():
    """
    Update APT package cache using AptKit D-Bus service

    Returns:
        bool: True if cache update was successful, False otherwise
    """
    ret = True
    bus = None
    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        introspection = await bus.introspect('org.aptkit', '/org/aptkit')
        aptkit_proxy = bus.get_proxy_object('org.aptkit', '/org/aptkit', introspection)
        aptkit_interface = aptkit_proxy.get_interface('org.aptkit')

        logger.info("Updating package cache")
        transaction_path = await aptkit_interface.call_update_cache()
        logger.info(f"Transaction started: {transaction_path}")

        transaction_introspection = await bus.introspect('org.aptkit', transaction_path)
        transaction_proxy = bus.get_proxy_object('org.aptkit', transaction_path, transaction_introspection)
        transaction_interface = transaction_proxy.get_interface('org.aptkit.transaction')

        finished_future = asyncio.Future()

        def on_property_changed(property_name, value):
            logger.info(f"Property changed: {property_name} = {value}")
            if property_name == "Progress":
                logger.info(f"Progress: {value}%")
            elif property_name == "Status":
                logger.info(f"Status: {value}")
            elif property_name == "ExitState":
                logger.info(f"Exit state: {value}")
                if value != "exit-unfinished":
                    if not finished_future.done():
                        finished_future.set_result(value)

        def on_finished(exit_state):
            logger.info(f"Transaction finished with exit state: {exit_state}")
            if not finished_future.done():
                finished_future.set_result(exit_state)

        transaction_interface.on_property_changed(on_property_changed)
        transaction_interface.on_finished(on_finished)

        await transaction_interface.call_run()

        try:
            exit_state = await asyncio.wait_for(finished_future, timeout=300)

            if exit_state.value != "exit-success":
                logger.error(f"Cache update failed with exit state: {exit_state.value}")
                ret = False
            else:
                logger.success(f"Cache update completed successfully with exit state: {exit_state.value}")
        except asyncio.TimeoutError:
            logger.error("Cache update timed out after 5 minutes")
            try:
                await transaction_interface.call_cancel()
                logger.error("Transaction cancelled")
            except Exception as e:
                logger.error(f"Error cancelling transaction: {e}")
            ret = False
    except Exception as e:
        logger.error(f"Error during cache update: {e}")
        ret = False
    finally:
        if bus:
            bus.disconnect()
    return ret

async def install_package(package_name):
    """
    Install a Debian package using AptKit D-Bus service

    Args:
        package_name (str): The name of the package to install

    Returns:
        bool: True if installation was successful, False otherwise
    """
    ret = True
    bus = None

    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        introspection = await bus.introspect('org.aptkit', '/org/aptkit')
        aptkit_proxy = bus.get_proxy_object('org.aptkit', '/org/aptkit', introspection)
        aptkit_interface = aptkit_proxy.get_interface('org.aptkit')

        logger.info(f"Installing package: {package_name}")

        transaction_path = await aptkit_interface.call_install_packages([package_name])
        logger.info(f"Transaction started: {transaction_path}")

        transaction_introspection = await bus.introspect('org.aptkit', transaction_path)
        transaction_proxy = bus.get_proxy_object('org.aptkit', transaction_path, transaction_introspection)
        transaction_interface = transaction_proxy.get_interface('org.aptkit.transaction')

        finished_future = asyncio.Future()

        def on_property_changed(property_name, value):
            logger.info(f"Property changed: {property_name} = {value}")

            if property_name == "Progress":
                logger.info(f"Progress: {value}%")
            elif property_name == "Status":
                logger.info(f"Status: {value}")
            elif property_name == "ExitState":
                logger.info(f"Exit state: {value}")
                if value != "exit-unfinished":
                    if not finished_future.done():
                        finished_future.set_result(value)

        def on_finished(exit_state):
            logger.info(f"Transaction finished with exit state: {exit_state}")
            if not finished_future.done():
                finished_future.set_result(exit_state)

        transaction_interface.on_property_changed(on_property_changed)
        transaction_interface.on_finished(on_finished)

        await transaction_interface.call_run()

        try:
            exit_state = await asyncio.wait_for(finished_future, timeout=300)
            if exit_state.value != "exit-success":
                logger.error(f"Transaction failed with exit state: {exit_state.value}")
                ret = False
            else:
                logger.success(f"Transaction completed successfully with exit state: {exit_state.value}")
        except asyncio.TimeoutError:
            logger.error("Transaction timed out after 5 minutes")
            try:
                await transaction_interface.call_cancel()
                logger.error("Transaction cancelled")
            except Exception as e:
                logger.error(f"Error cancelling transaction: {e}")

            ret = False
    except Exception as e:
        logger.error(f"Error during installation: {e}")
        ret = False
    finally:
        bus.disconnect()
    return ret
