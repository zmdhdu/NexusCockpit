#!/usr/bin/env python
"""Test DB manager chat log persistence."""
import asyncio
import sys
sys.path.insert(0, ".")

from nexus.core.db_manager import get_db_manager

async def test():
    db = get_db_manager()
    await db.connect()
    print(f"Connected: {db.is_connected}")
    
    # Test insert
    await db.execute_update(
        "INSERT INTO chat_logs (cockpit_id, user_id, user_input, assistant_response, "
        "intent, action, latency_ms, cache_hit) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        ("cockpit-01", "test_user", "test input", "test response",
         "test_intent", "test_action", 100.0, False),
    )
    print("Insert OK")
    
    # Test select
    rows = await db.execute_query(
        "SELECT COUNT(*) as cnt FROM chat_logs WHERE user_id = %s",
        ("test_user",),
    )
    print(f"Count: {rows}")
    
    # Test record_user_habit
    await db.record_user_habit("test_user", "cockpit-01", "test_habit", "test_value")
    print("Habit record OK")
    
    await db.close()

asyncio.run(test())
