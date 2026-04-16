import asyncio
from models.schemas import TaskState
from memory.short_term import get_redis, _state_key

async def main():
    try:
        r = await get_redis()
        keys = await r.keys("task_state:*")
        print("Found keys:", keys)
        for key in keys:
            payload = await r.get(key)
            if payload:
                try:
                    TaskState.model_validate_json(payload)
                except Exception as e:
                    print(f"Error validating {key}: {e}")
        await r.aclose()
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
