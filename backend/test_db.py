import asyncio
from sqlalchemy import select
from database import async_session_maker
from models.db import AgentCall

async def main():
    async with async_session_maker() as s:
        res = await s.execute(select(AgentCall).where(AgentCall.task_id=="bf23bbf7-a2e7-4536-93c6-11d0cc86f1f0").order_by(AgentCall.created_at.desc()).limit(10))
        for r in res.scalars().all():
            print(f"Role: {r.agent_role}, Action: {r.action}")
            if r.error_message:
                print(f"Error: {r.error_message}")
            if r.output_payload:
                print(f"Output: {str(r.output_payload)[:300]}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
