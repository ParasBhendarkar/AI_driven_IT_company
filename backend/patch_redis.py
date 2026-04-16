import asyncio
import json
from memory.short_term import get_redis

async def main():
    r = await get_redis()
    keys = await r.keys("task_state:*")
    count = 0
    for key in keys:
        payload = await r.get(key)
        if payload:
            data = json.loads(payload)
            changed = False
            
            # Fix tl_review_feedback
            if "tl_review_feedback" in data and isinstance(data["tl_review_feedback"], list):
                data["tl_review_feedback"] = "\n".join(str(x) for x in data["tl_review_feedback"])
                changed = True
                
            # Fix team_leader_output.review_feedback
            if "team_leader_output" in data and data["team_leader_output"]:
                tl_out = data["team_leader_output"]
                if "review_feedback" in tl_out and isinstance(tl_out["review_feedback"], list):
                    tl_out["review_feedback"] = "\n".join(str(x) for x in tl_out["review_feedback"])
                    changed = True
                if "final_feedback" in tl_out and isinstance(tl_out["final_feedback"], list):
                    tl_out["final_feedback"] = "\n".join(str(x) for x in tl_out["final_feedback"])
                    changed = True
                    
            if "tl_final_feedback" in data and isinstance(data["tl_final_feedback"], list):
                data["tl_final_feedback"] = "\n".join(str(x) for x in data["tl_final_feedback"])
                changed = True

            if changed:
                await r.set(key, json.dumps(data))
                count += 1
                print(f"Fixed {key}")
                
    await r.aclose()
    print(f"Fixed {count} broken task states in Redis.")

if __name__ == "__main__":
    asyncio.run(main())
