from fastapi import APIRouter

from footprono.api.v1 import (
    accounts,
    admin,
    bets,
    football,
    health,
    montantes,
    notifications,
    payments,
    predictions,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(accounts.router)
api_router.include_router(admin.router)
api_router.include_router(bets.router)
api_router.include_router(montantes.router)
api_router.include_router(notifications.router)
api_router.include_router(payments.router)
api_router.include_router(football.router)
api_router.include_router(predictions.router)
