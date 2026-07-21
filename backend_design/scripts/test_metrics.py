#!/usr/bin/env python
"""Test if cockpit metrics are being recorded."""
import asyncio
import sys

sys.path.insert(0, ".")

from nexus.observability.cockpit_metrics import get_cockpit_metrics


async def test():
    metrics = get_cockpit_metrics()
    print(f"Metrics singleton: {metrics}")
    print(f"Redis client: {metrics._redis}")

    if metrics._redis:
        # Try recording
        await metrics.record_chat("cockpit-01", 100.0, False)
        print("Recorded chat metric")

        # Check
        stats = await metrics.get_cockpit_stats("cockpit-01")
        print(f"Stats after record: {stats}")
    else:
        print("ERROR: Redis client is None! Metrics will not be recorded.")

asyncio.run(test())
