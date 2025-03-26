#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import asyncio
import sys
import signal
from argparse import ArgumentParser
from loguru import logger

from store_manager.store_manager import StoreManager

def configure_logger(args) -> None:
    # Remove default logger to configure our own
    logger.remove()

    if args.verbose:
        logger.add(sys.stdout)

async def main():
    # Disable buffering for stdout and stderr so that logs are written immediately
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    parser = ArgumentParser(description="Run the Store Provider services", add_help=False)
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output.')
    args = parser.parse_args()
    configure_logger(args)

    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()

    def handle_sigint():
        logger.info("Received SIGINT, shutting down...")
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, handle_sigint)

    manager = StoreManager()

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
            logger.error(f"Error in task: {e}")
    logger.info("Main loop exited, goodbye!")

if __name__ == "__main__":
    asyncio.run(main())
