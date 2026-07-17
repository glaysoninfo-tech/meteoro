from fastapi import APIRouter

from app.modules.alerts.api import router as alerts_router
from app.modules.audit.api import router as audit_router
from app.modules.catalog.api import router as catalog_router
from app.modules.communications.api import router as communications_router
from app.modules.data_quality.api import router as data_quality_router
from app.modules.geospatial.api import router as geospatial_router
from app.modules.identity.api import router as identity_router
from app.modules.incidents.api import router as incidents_router
from app.modules.ingestion.api import router as ingestion_router
from app.modules.meteorology.api import router as meteorology_router
from app.modules.operations.api import router as operations_router
from app.modules.planning.api import router as planning_router
from app.modules.public.api import router as public_router
from app.modules.recommendations.api import router as recommendations_router

api_router = APIRouter()


@api_router.get("/status", tags=["system"])
def system_status() -> dict[str, str]:
    return {"status": "online", "stage": "bootstrap"}


api_router.include_router(identity_router, prefix="/auth", tags=["auth"])
api_router.include_router(catalog_router, prefix="/catalog", tags=["catalog"])
api_router.include_router(geospatial_router, prefix="/geospatial", tags=["geospatial"])
api_router.include_router(ingestion_router, prefix="/ingestion", tags=["ingestion"])
api_router.include_router(communications_router, prefix="/communications", tags=["communications"])
api_router.include_router(meteorology_router, prefix="/meteorology", tags=["meteorology"])
api_router.include_router(operations_router, prefix="/operations", tags=["operations"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
api_router.include_router(incidents_router, prefix="/incidents", tags=["incidents"])
api_router.include_router(planning_router, prefix="/planning", tags=["planning"])
api_router.include_router(
    data_quality_router, prefix="/data-quality", tags=["data-quality"]
)
api_router.include_router(audit_router, prefix="/audit", tags=["audit"])
api_router.include_router(public_router, prefix="/public", tags=["public"])
api_router.include_router(recommendations_router, prefix="/recommendations", tags=["recommendations"])
