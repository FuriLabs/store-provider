#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import asyncio
from loguru import logger

from android_store import AndroidStoreService
from open_store import OpenStoreService

from dbus_fast.service import ServiceInterface, method, signal
from dbus_fast.aio import MessageBus
from dbus_fast import BusType, Variant

class StoreManagerInterface(ServiceInterface):
    def __init__(self):
        logger.info("Initializing Store Manager interface")
        super().__init__('io.FuriOS.StoreManager')

    @method()
    async def Start(self) -> 'b':
        return True

    @method()
    async def GetAvailableStores(self) -> 'as':
        return ["AndroidStore", "OpenStore"]

class StoreManager:
    def __init__(self):
        logger.info("Initializing Store Manager")
        self.android_store = None
        self.open_store = None
        self.shutdown_event = asyncio.Event()
        self.idle_timer = None
        self.idle_timeout = 120  # seconds
        self.store_manager_bus = None
        self._tasks = []

    async def reset_idle_timer(self):
        if self.idle_timer:
            self.idle_timer.cancel()
        self.idle_timer = asyncio.create_task(self._idle_countdown())
        self._tasks.append(self.idle_timer)

    async def _idle_countdown(self):
        try:
            await asyncio.sleep(self.idle_timeout)
            logger.info(f"Services idle for {self.idle_timeout} seconds, shutting down")
            self.shutdown_event.set()
        except asyncio.CancelledError:
            pass

    async def setup_store_manager_interface(self):
        self.store_manager_bus = await MessageBus(bus_type=BusType.SESSION).connect()
        store_manager_interface = StoreManagerInterface()
        self.store_manager_bus.export('/io/FuriOS/StoreManager', store_manager_interface)
        await self.store_manager_bus.request_name('io.FuriOS.StoreManager')
        logger.info("Store Manager DBus interface is now running")

    async def setup(self):
        try:
            self.android_store = AndroidStoreService(idle_callback=self.reset_idle_timer)
            self.open_store = OpenStoreService(idle_callback=self.reset_idle_timer)

            setup_tasks = [
                self.setup_store_manager_interface(),
                self.reset_idle_timer(),
                self.android_store.setup(),
                self.open_store.setup()
            ]

            results = await asyncio.gather(*setup_tasks)

            android_bus = results[2]
            openstore_bus = results[3]

            android_disconnect = asyncio.create_task(android_bus.wait_for_disconnect())
            openstore_disconnect = asyncio.create_task(openstore_bus.wait_for_disconnect())
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())

            self._tasks.extend([android_disconnect, openstore_disconnect, shutdown_task])

            try:
                done, pending = await asyncio.wait(
                    [android_disconnect, openstore_disconnect, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                for task in pending:
                    if not task.done():
                        task.cancel()

                if shutdown_task in done:
                    logger.info("Shutting down due to inactivity")
                elif android_disconnect in done:
                    logger.info("Android Store bus disconnected")
                elif openstore_disconnect in done:
                    logger.info("OpenStore bus disconnected")
            except asyncio.CancelledError:
                logger.info("Setup cancelled, initiating cleanup")
                raise
        except asyncio.CancelledError:
            logger.info("Setup cancelled, will clean up resources")
            raise
        except Exception as e:
            logger.error(f"Setup error: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self):
        logger.info("Cleaning up resources...")

        for task in self._tasks:
            if task and not task.done():
                task.cancel()

        self._tasks.clear()

        cleanup_tasks = []

        if self.android_store:
            cleanup_tasks.append(self.android_store.cleanup())
        if self.open_store:
            cleanup_tasks.append(self.open_store.cleanup())
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        if self.idle_timer and not self.idle_timer.done():
            self.idle_timer.cancel()

        self.android_store = None
        self.open_store = None
        self.store_manager_bus = None
        self.idle_timer = None

        logger.info("Cleanup complete")
