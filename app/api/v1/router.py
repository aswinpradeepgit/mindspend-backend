"""Aggregates all v1 route modules under a single router.

New feature areas get their own module in routes/ and are included here.
"""

from fastapi import APIRouter

from app.api.v1.routes import (
    categories,
    coach,
    devices,
    expenses,
    goals,
    health,
    notifications,
    profile,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(coach.router, prefix="/coach", tags=["coach"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(notifications.router, prefix="/internal", tags=["internal"])
