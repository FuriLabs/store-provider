#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import asyncio
import sys
import signal
from argparse import ArgumentParser

from android_store.android_store import AndroidStoreService
from open_store.open_store import OpenStoreService
from common.utils import store_print

class StoreManager:
    def __init__(self, verbose=False):
        store_print("Initializing Store Manager", verbose)
        self.verbose = verbose
        self.android_store = None
        self.open_store = None
        self.shutdown_event = asyncio.Event()
        self.idle_timer = None
        self.idle_timeout = 120  # seconds

    async def reset_idle_timer(self):
        """Reset the shared idle timer when any service has activity"""
        if self.idle_timer:
            self.idle_timer.cancel()
        self.idle_timer = asyncio.create_task(self._idle_countdown())

    async def _idle_countdown(self):
        """Count down to service shutdown due to inactivity"""
        try:
            await asyncio.sleep(self.idle_timeout)
            store_print(f"Services idle for {self.idle_timeout} seconds, shutting down", self.verbose)
            self.shutdown_event.set()
        except asyncio.CancelledError:
            pass

    async def setup(self):
        try:
            self.android_store = AndroidStoreService(verbose=self.verbose, idle_callback=self.reset_idle_timer)
            self.open_store = OpenStoreService(verbose=self.verbose, idle_callback=self.reset_idle_timer)

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
                    store_print("Shutting down due to inactivity", self.verbose)
                elif android_disconnect in done:
                    store_print("Android Store bus disconnected", self.verbose)
                elif openstore_disconnect in done:
                    store_print("OpenStore bus disconnected", self.verbose)
            except asyncio.CancelledError:
                store_print("Setup cancelled, cleaning up", self.verbose)
                for task in all_tasks:
                    if not task.done():
                        task.cancel()
                raise
        except asyncio.CancelledError:
            store_print("Setup cancelled, shutting down", self.verbose)
            raise
        finally:
            if self.android_store:
                await self.android_store.cleanup()
            if self.open_store:
                await self.open_store.cleanup()
            if self.idle_timer and not self.idle_timer.done():
                self.idle_timer.cancel()

async def main():
    # Disable buffering for stdout and stderr so that logs are written immediately
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    parser = ArgumentParser(description="Run the Store Provider services", add_help=False)
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output.')
    args = parser.parse_args()

    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()

    def handle_sigint():
        store_print("Received SIGINT, shutting down...", args.verbose)
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, handle_sigint)

    manager = StoreManager(verbose=args.verbose)

    setup_task = asyncio.create_task(manager.setup())
    stop_task = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait(
        [setup_task, stop_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()

    for task in done:
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            store_print(f"Error in task: {e}", args.verbose)
    store_print("Main loop exited, goodbye!", args.verbose)

if __name__ == "__main__":
    asyncio.run(main())
