#!/usr/bin/env python3
"""
Test script for database integration.
Verifies that database operations work correctly.

Usage:
    python scripts/test_db.py
"""

import asyncio
import sys
from pathlib import Path


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_database():
    """Run database tests."""
    print("=== Database Integration Tests ===\n")

    # Test 1: Initialize database
    print("1. Testing database initialization...")
    try:
        from db.database import AsyncSessionLocal, get_db_status, init_db

        await init_db()
        status = await get_db_status()
        assert status["status"] == "ok", f"Database status: {status}"
        print(f"   OK - Database initialized at {status['path']}")
    except Exception as e:
        print(f"   FAIL - {e}")
        return False

    # Test 2: Test ChatRepository
    print("\n2. Testing ChatRepository...")
    try:
        from db.repositories import ChatRepository

        async with AsyncSessionLocal() as session:
            repo = ChatRepository(session)

            # Create session
            chat_session = await repo.create_session("Test Chat", "Test prompt")
            assert chat_session["title"] == "Test Chat"
            session_id = chat_session["id"]
            print(f"   Created session: {session_id}")

            # Add message
            msg = await repo.add_message(session_id, "user", "Hello, test!")
            assert msg["content"] == "Hello, test!"
            print(f"   Added message: {msg['id']}")

            # Get session
            fetched = await repo.get_session(session_id)
            assert fetched is not None
            assert len(fetched["messages"]) == 1
            print(f"   Fetched session with {len(fetched['messages'])} message(s)")

            # Delete session
            deleted = await repo.delete_session(session_id)
            assert deleted
            print(f"   Deleted session: {session_id}")

        print("   OK - ChatRepository working")
    except Exception as e:
        print(f"   FAIL - {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 3: Test FAQRepository
    print("\n3. Testing FAQRepository...")
    try:
        from db.repositories import FAQRepository

        async with AsyncSessionLocal() as session:
            repo = FAQRepository(session)

            # Create entry
            entry = await repo.create_entry("test question", "test answer")
            assert entry["question"] == "test question"
            print(f"   Created FAQ: {entry['question']}")

            # Get as dict
            faq_dict = await repo.get_as_dict()
            assert "test question" in faq_dict
            print(f"   Got FAQ dict with {len(faq_dict)} entries")

            # Delete entry
            deleted = await repo.delete_by_question("test question")
            assert deleted
            print("   Deleted FAQ entry")

        print("   OK - FAQRepository working")
    except Exception as e:
        print(f"   FAIL - {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 4: Test ConfigRepository
    print("\n4. Testing ConfigRepository...")
    try:
        from db.repositories import ConfigRepository

        async with AsyncSessionLocal() as session:
            repo = ConfigRepository(session)

            # Set config
            await repo.set_config("test_key", {"value": 123})
            print("   Set config: test_key")

            # Get config
            value = await repo.get_config("test_key")
            assert value["value"] == 123
            print(f"   Got config: {value}")

            # Delete config
            deleted = await repo.delete_config("test_key")
            assert deleted
            print("   Deleted config: test_key")

        print("   OK - ConfigRepository working")
    except Exception as e:
        print(f"   FAIL - {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 5: Test Redis (optional)
    print("\n5. Testing Redis connection (optional)...")
    try:
        from db.redis_client import close_redis, get_redis_status, init_redis

        redis_ok = await init_redis()
        if redis_ok:
            status = await get_redis_status()
            print(f"   OK - Redis connected: v{status.get('version')}")
            await close_redis()
        else:
            print("   SKIP - Redis not available (this is OK)")
    except Exception as e:
        print(f"   SKIP - Redis error: {e} (this is OK)")

    print("\n=== All tests passed! ===")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_database())
    sys.exit(0 if success else 1)
