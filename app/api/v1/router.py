"""v1 API router — aggregates every endpoint module."""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    addresses,
    admin,
    auth,
    bookings,
    catalog,
    offers,
    pujaris,
    service_lifecycle,
    webhooks,
    ws,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(addresses.router)
api_router.include_router(catalog.router)
api_router.include_router(bookings.router)
api_router.include_router(offers.router)
api_router.include_router(pujaris.router)
api_router.include_router(service_lifecycle.router)
api_router.include_router(admin.router)
api_router.include_router(webhooks.router)
api_router.include_router(ws.router)
