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
]


@router.get("", response_model=list[Repo])
async def list_repos() -> list[Repo]:
    return CURATED_REPOS
