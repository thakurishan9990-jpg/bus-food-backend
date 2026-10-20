from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.dhaba import Dhaba, MenuItem
from app.models.route import Route
from app.models.stop import Stop
from app.models.trip import Trip
from app.models.user import UserRole
from app.schemas.dashboard import Business, Operations
from app.schemas.dhaba import DhabaCreate, DhabaRead, DhabaUpdate, MenuItemCreate, MenuItemRead, MenuItemUpdate
from app.schemas.route import RouteCreate, RouteRead, RouteUpdate
from app.schemas.stop import StopCreate, StopRead, StopUpdate
from app.schemas.trip import TripCreate, TripRead, TripUpdate
from app.services import dashboard_service
from app.utils.errors import NotFoundError
from app.utils.security import require_role

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))])


def _apply_update(obj, payload) -> None:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)


# ---- Dashboards ----

@router.get("/operations", response_model=Operations)
def operations(db: Session = Depends(get_db)) -> Operations:
    """Live KPIs, open orders by route, live trips, and kitchens that can't keep up. Admin only."""
    return dashboard_service.operations(db)


@router.get("/business", response_model=Business)
def business(db: Session = Depends(get_db)) -> Business:
    """Today's income by stream (commission, fees, ads, add-ons), and the split of an example order. Admin only."""
    return dashboard_service.business(db)


# ---- Routes ----

@router.post("/routes", response_model=RouteRead, status_code=201)
def create_route(payload: RouteCreate, db: Session = Depends(get_db)) -> Route:
    route = Route(**payload.model_dump())
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


@router.patch("/routes/{route_id}", response_model=RouteRead)
def update_route(route_id: int, payload: RouteUpdate, db: Session = Depends(get_db)) -> Route:
    route = db.get(Route, route_id)
    if route is None:
        raise NotFoundError(f"Route {route_id} not found")
    _apply_update(route, payload)
    db.commit()
    db.refresh(route)
    return route


@router.delete("/routes/{route_id}", status_code=204)
def delete_route(route_id: int, db: Session = Depends(get_db)) -> None:
    route = db.get(Route, route_id)
    if route is None:
        raise NotFoundError(f"Route {route_id} not found")
    db.delete(route)
    db.commit()


# ---- Stops ----

@router.post("/stops", response_model=StopRead, status_code=201)
def create_stop(payload: StopCreate, db: Session = Depends(get_db)) -> Stop:
    if db.get(Route, payload.route_id) is None:
        raise NotFoundError(f"Route {payload.route_id} not found")
    stop = Stop(**payload.model_dump())
    db.add(stop)
    db.commit()
    db.refresh(stop)
    return stop


@router.patch("/stops/{stop_id}", response_model=StopRead)
def update_stop(stop_id: int, payload: StopUpdate, db: Session = Depends(get_db)) -> Stop:
    stop = db.get(Stop, stop_id)
    if stop is None:
        raise NotFoundError(f"Stop {stop_id} not found")
    _apply_update(stop, payload)
    db.commit()
    db.refresh(stop)
    return stop


@router.delete("/stops/{stop_id}", status_code=204)
def delete_stop(stop_id: int, db: Session = Depends(get_db)) -> None:
    stop = db.get(Stop, stop_id)
    if stop is None:
        raise NotFoundError(f"Stop {stop_id} not found")
    db.delete(stop)
    db.commit()


# ---- Dhabas ----

@router.post("/dhabas", response_model=DhabaRead, status_code=201)
def create_dhaba(payload: DhabaCreate, db: Session = Depends(get_db)) -> Dhaba:
    if db.get(Stop, payload.stop_id) is None:
        raise NotFoundError(f"Stop {payload.stop_id} not found")
    dhaba = Dhaba(**payload.model_dump())
    db.add(dhaba)
    db.commit()
    db.refresh(dhaba)
    return dhaba


@router.patch("/dhabas/{dhaba_id}", response_model=DhabaRead)
def update_dhaba(dhaba_id: int, payload: DhabaUpdate, db: Session = Depends(get_db)) -> Dhaba:
    dhaba = db.get(Dhaba, dhaba_id)
    if dhaba is None:
        raise NotFoundError(f"Dhaba {dhaba_id} not found")
    _apply_update(dhaba, payload)
    db.commit()
    db.refresh(dhaba)
    return dhaba


@router.delete("/dhabas/{dhaba_id}", status_code=204)
def delete_dhaba(dhaba_id: int, db: Session = Depends(get_db)) -> None:
    dhaba = db.get(Dhaba, dhaba_id)
    if dhaba is None:
        raise NotFoundError(f"Dhaba {dhaba_id} not found")
    db.delete(dhaba)
    db.commit()


# ---- Trips ----

@router.post("/trips", response_model=TripRead, status_code=201)
def create_trip(payload: TripCreate, db: Session = Depends(get_db)) -> Trip:
    if db.get(Route, payload.route_id) is None:
        raise NotFoundError(f"Route {payload.route_id} not found")
    trip = Trip(**payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.patch("/trips/{trip_id}", response_model=TripRead)
def update_trip(trip_id: int, payload: TripUpdate, db: Session = Depends(get_db)) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {trip_id} not found")
    _apply_update(trip, payload)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: int, db: Session = Depends(get_db)) -> None:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {trip_id} not found")
    db.delete(trip)
    db.commit()


# ---- Menu items ----

@router.post("/menu-items", response_model=MenuItemRead, status_code=201)
def create_menu_item(payload: MenuItemCreate, db: Session = Depends(get_db)) -> MenuItem:
    if db.get(Dhaba, payload.dhaba_id) is None:
        raise NotFoundError(f"Dhaba {payload.dhaba_id} not found")
    menu_item = MenuItem(**payload.model_dump())
    db.add(menu_item)
    db.commit()
    db.refresh(menu_item)
    return menu_item


@router.patch("/menu-items/{menu_item_id}", response_model=MenuItemRead)
def update_menu_item(menu_item_id: int, payload: MenuItemUpdate, db: Session = Depends(get_db)) -> MenuItem:
    menu_item = db.get(MenuItem, menu_item_id)
    if menu_item is None:
        raise NotFoundError(f"Menu item {menu_item_id} not found")
    _apply_update(menu_item, payload)
    db.commit()
    db.refresh(menu_item)
    return menu_item


@router.delete("/menu-items/{menu_item_id}", status_code=204)
def delete_menu_item(menu_item_id: int, db: Session = Depends(get_db)) -> None:
    menu_item = db.get(MenuItem, menu_item_id)
    if menu_item is None:
        raise NotFoundError(f"Menu item {menu_item_id} not found")
    db.delete(menu_item)
    db.commit()
