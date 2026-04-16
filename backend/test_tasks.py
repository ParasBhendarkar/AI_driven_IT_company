import asyncio
from services.task_service import list_tasks

async def main():
    try:
        tasks = await list_tasks()
        print("Tasks fetched successfully:", len(tasks))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
