"""Curated demo repository listing."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/repos", tags=["repos"])


class Repo(BaseModel):
    id: str
    name: str
    description: str
    language: str
    path: str


CURATED_REPOS: list[Repo] = [
    Repo(
        id="vibe-todo-app",
        name="Vibe Todo App",
        description="A quick todo API built with AI assistance for a CS 101 final project. Contains common security antipatterns.",
        language="javascript",
        path="demo-repos/vibe-todo-app",
    ),
    Repo(
        id="vibe-notes-api",
        name="Vibe Notes API",
        description="A Flask personal-notes service shipped over a weekend with AI help. Touches crypto, deserialization, SSRF, and template rendering.",
        language="python",
        path="demo-repos/vibe-notes-api",
    ),
    Repo(
        id="vibe-file-share",
        name="Vibe File Share",
        description="An Express file-sharing service with uploads, downloads, thumbnails, and URL mirroring. Classic AI-generated antipatterns throughout.",
        language="javascript",
        path="demo-repos/vibe-file-share",
    ),
    Repo(
        id="vibe-auth-service",
        name="Vibe Auth Service",
        description="A standalone Express auth microservice (login, register, reset, sessions). Covers JWT, cookies, password hashing, and reset tokens.",
        language="javascript",
        path="demo-repos/vibe-auth-service",
    ),
]


@router.get("", response_model=list[Repo])
async def list_repos() -> list[Repo]:
    return CURATED_REPOS
