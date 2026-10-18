from fastapi import APIRouter

from app.api.v1 import admin, auth, compliance, meetings, projects, risks, users, webhooks

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(admin.router)
api_v1_router.include_router(meetings.router)
api_v1_router.include_router(risks.router)
api_v1_router.include_router(risks.analytics_router)
api_v1_router.include_router(compliance.router)
api_v1_router.include_router(webhooks.router)
