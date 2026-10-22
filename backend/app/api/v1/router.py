"""Aggregate all versioned sub-routers into a single ``v1`` router.

Routes keep their explicit ``/api/...`` prefixes so the URL surface stays stable
for the web client and existing integrations.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import items, search, shared, user

api_v1_router = APIRouter()
api_v1_router.include_router(user.router)
api_v1_router.include_router(items.router)
api_v1_router.include_router(search.router)
api_v1_router.include_router(shared.router)


__all__ = ["api_v1_router"]
