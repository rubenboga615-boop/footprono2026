from fastapi import APIRouter

from footprono.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
