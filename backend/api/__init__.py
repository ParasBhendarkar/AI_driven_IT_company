from api.auth import router as auth_router
from api.github import router as github_router
from api.tasks import router as tasks_router
from api.inbox import router as inbox_router
from api.memory import router as memory_router
from api.activity import router as activity_router

__all__ = [
    "auth_router",
    "github_router",
    "tasks_router",
    "inbox_router",
    "memory_router",
    "activity_router",
]
