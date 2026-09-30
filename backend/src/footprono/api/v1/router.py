from fastapi import APIRouter

from footprono.api.v1 import accounts, football, health, predictions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(accounts.router)
api_router.include_router(football.router)
api_router.include_router(predictions.router)
