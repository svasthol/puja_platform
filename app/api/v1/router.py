"""v1 API router — aggregates every endpoint module."""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    addresses,
    admin,
    admin_areas,
    admin_auth,
    admin_bookings,
    admin_catalog,
    admin_kyc,
    admin_promos,
    admin_pujaris,
    admin_refunds,
    admin_rm,
    app_config,
    auth,
    bookings,
    catalog,
    devices,
    offers,
    panchangam,
    pujaris,
    pujari_bookings,
    service_areas,
    service_lifecycle,
    webhooks,
    ws,
)

api_router = APIRouter()
api_router.include_router(app_config.router)
api_router.include_router(panchangam.router)
api_router.include_router(auth.router)
api_router.include_router(admin_auth.router)
api_router.include_router(devices.router)
api_router.include_router(addresses.router)
api_router.include_router(service_areas.router)
api_router.include_router(catalog.router)
api_router.include_router(bookings.router)
api_router.include_router(offers.router)
api_router.include_router(pujari_bookings.router)
api_router.include_router(pujaris.router)
api_router.include_router(service_lifecycle.router)
api_router.include_router(admin.router)
api_router.include_router(admin_catalog.router)
api_router.include_router(admin_areas.router)
api_router.include_router(admin_rm.router)
api_router.include_router(admin_pujaris.router)
api_router.include_router(admin_kyc.router)
api_router.include_router(admin_bookings.router)
api_router.include_router(admin_refunds.router)
api_router.include_router(admin_promos.router)
api_router.include_router(webhooks.router)
api_router.include_router(ws.router)
