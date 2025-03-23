# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

from inspect import currentframe
from time import time

def store_print(message, verbose):
    if not verbose:
        return

    frame = currentframe()
    caller_frame = frame.f_back

    bus_name = None

    if 'self' in caller_frame.f_locals:
        cls = caller_frame.f_locals['self']
        cls_name = cls.__class__.__name__

        if hasattr(cls, 'bus') and cls.bus:
            bus_name = cls.bus._requested_name if hasattr(cls.bus, '_requested_name') else None
        elif hasattr(cls, '_interface_name'):
            bus_name = cls._interface_name

        func_name = caller_frame.f_code.co_name

        if bus_name:
            full_message = f"[{bus_name}] {cls_name}.{func_name}: {message}"
        else:
            full_message = f"{cls_name}.{func_name}: {message}"
    else:
        func_name = caller_frame.f_code.co_name
        full_message = f"{func_name}: {message}"
    print(f"{time()} {full_message}")
