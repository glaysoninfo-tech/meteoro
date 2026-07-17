from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.geospatial.schemas import (
    SensorCreate,
    SensorOut,
    SensorUpdate,
    StationCreate,
    StationOut,
    StationUpdate,
    TerritoryCreate,
    TerritoryOut,
    TerritoryUpdate,
)
from app.modules.geospatial.service import geospatial_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser

router = APIRouter()


@router.get("/official-layers")
def get_official_layers(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
) -> dict:
    """Camadas de referência de fontes oficiais (ANA, CEMADEN, INPE).

    Busca ao vivo com cache de 10 minutos; cada camada reporta disponibilidade
    individual — indisponibilidade externa não derruba o mapa.
    """
    from app.modules.geospatial.official_layers import official_layers

    return official_layers()


@router.get("/territories", response_model=list[TerritoryOut])
def list_territories(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> list[TerritoryOut]:
    return geospatial_service.list_territories(db=db, organization_id=current_user.organization_id)


@router.post("/territories", response_model=TerritoryOut, status_code=status.HTTP_201_CREATED)
def create_territory(
    payload: TerritoryCreate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> TerritoryOut:
    try:
        territory = geospatial_service.create_territory(db, current_user.organization_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="geospatial", action="territory.created", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="territory", resource_id=territory.territory_id,
    )
    return territory


@router.patch("/territories/{territory_id}", response_model=TerritoryOut)
def update_territory(
    territory_id: str,
    payload: TerritoryUpdate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> TerritoryOut:
    try:
        territory = geospatial_service.update_territory(db, current_user.organization_id, territory_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="geospatial", action="territory.updated", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="territory", resource_id=territory.territory_id,
    )
    return territory


@router.get("/stations", response_model=list[StationOut])
def list_stations(
    territory_id: str | None = Query(default=None),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> list[StationOut]:
    return geospatial_service.list_stations(db, current_user.organization_id, territory_id)


@router.post("/stations", response_model=StationOut, status_code=status.HTTP_201_CREATED)
def create_station(
    payload: StationCreate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> StationOut:
    try:
        station = geospatial_service.create_station(db, current_user.organization_id, payload)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="geospatial", action="station.created", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="station", resource_id=station.station_id,
    )
    return station


@router.patch("/stations/{station_id}", response_model=StationOut)
def update_station(
    station_id: str,
    payload: StationUpdate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> StationOut:
    try:
        station = geospatial_service.update_station(db, current_user.organization_id, station_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="geospatial", action="station.updated", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="station", resource_id=station.station_id,
    )
    return station


@router.get("/sensors", response_model=list[SensorOut])
def list_sensors(
    station_id: str | None = Query(default=None),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> list[SensorOut]:
    return geospatial_service.list_sensors(db, current_user.organization_id, station_id)


@router.post("/sensors", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
def create_sensor(
    payload: SensorCreate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> SensorOut:
    try:
        sensor = geospatial_service.create_sensor(db, current_user.organization_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="geospatial", action="sensor.created", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="sensor", resource_id=sensor.sensor_id,
    )
    return sensor


@router.patch("/sensors/{sensor_id}", response_model=SensorOut)
def update_sensor(
    sensor_id: str,
    payload: SensorUpdate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> SensorOut:
    try:
        sensor = geospatial_service.update_sensor(db, current_user.organization_id, sensor_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="geospatial", action="sensor.updated", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="sensor", resource_id=sensor.sensor_id,
    )
    return sensor
