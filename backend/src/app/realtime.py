from app.core.realtime.hub import Hub
from app.core.realtime.router import Router


__all__ = ["get_hub", "hub", "router"]

router = Router()
hub = Hub(router)

def get_hub() -> Hub:
    return hub