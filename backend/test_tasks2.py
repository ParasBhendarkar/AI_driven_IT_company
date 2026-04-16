import asyncio
from services.task_service import list_tasks
from memory.short_term import _redis
from models.schemas import TaskState

async def main():
    try:
        keys = await _redis.keys("task:*")
        for key in keys:
            payload = await _redis.get(key)
            if payload:
                try:
                    TaskState.model_validate_json(payload)
                except Exception as e:
                    print(f"Error validating {key}: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
