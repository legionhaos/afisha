from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.chat import router as chat_router
from app.api.v1.dictionaries import router as dict_router
from app.api.v1.events import router as events_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.health import router as health_router
from app.api.v1.subscriptions import router as subscriptions_router

api_v1_router = APIRouter()

api_v1_router.include_router(events_router)
api_v1_router.include_router(dict_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(subscriptions_router)
api_v1_router.include_router(feedback_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(health_router)
