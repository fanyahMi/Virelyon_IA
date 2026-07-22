from fastapi import APIRouter

from app.api.v1.endpoints import ares, costs

api_router = APIRouter()
api_router.include_router(ares.router)
api_router.include_router(costs.router)
