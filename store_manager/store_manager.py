#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import asyncio
from loguru import logger

from android_store.android_store import AndroidStoreService
from open_store.open_store import OpenStoreService

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

    async def reset_idle_timer(self):
        """Reset the shared idle timer when any service has activity"""
        if self.idle_timer:
            self.idle_timer.cancel()
        self.idle_timer = asyncio.create_task(self._idle_countdown())

    async def _idle_countdown(self):
        """Count down to service shutdown due to inactivity"""
        try:
            await asyncio.sleep(self.idle_timeout)
            logger.info(f"Services idle for {self.idle_timeout} seconds, shutting down")
            self.shutdown_event.set()
        except asyncio.CancelledError:
            pass

    async def setup(self):
        try:
            self.store_manager_bus = await MessageBus(bus_type=BusType.SESSION).connect()
            store_manager_interface = StoreManagerInterface()
            self.store_manager_bus.export('/io/FuriOS/StoreManager', store_manager_interface)
            await self.store_manager_bus.request_name('io.FuriOS.StoreManager')
            logger.info("Store Manager DBus interface is now running")

            self.android_store = AndroidStoreService(idle_callback=self.reset_idle_timer)
            self.open_store = OpenStoreService(idle_callback=self.reset_idle_timer)

            await self.reset_idle_timer()

            android_bus_task = asyncio.create_task(self.android_store.setup())
            openstore_bus_task = asyncio.create_task(self.open_store.setup())

            android_bus = await android_bus_task
            openstore_bus = await openstore_bus_task

            android_disconnect = asyncio.create_task(android_bus.wait_for_disconnect())
            openstore_disconnect = asyncio.create_task(openstore_bus.wait_for_disconnect())
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())

            all_tasks = [android_disconnect, openstore_disconnect, shutdown_task]

            try:
                done, pending = await asyncio.wait(
                    all_tasks,
                    return_when=asyncio.FIRST_COMPLETED
                )

                for task in pending:
                    task.cancel()

                if shutdown_task in done:
                    logger.info("Shutting down due to inactivity")
                elif android_disconnect in done:
                    logger.info("Android Store bus disconnected")
                elif openstore_disconnect in done:
                    logger.info("OpenStore bus disconnected")
            except asyncio.CancelledError:
                logger.error("Setup cancelled, cleaning up")
                for task in all_tasks:
                    if not task.done():
                        task.cancel()
                raise
        except asyncio.CancelledError:
            logger.error("Setup cancelled, shutting down")
            raise
        finally:
            if self.android_store:
                await self.android_store.cleanup()
            if self.open_store:
                await self.open_store.cleanup()
            if self.idle_timer and not self.idle_timer.done():
                self.idle_timer.cancel()
            if self.store_manager_bus:
                self.store_manager_bus = None
