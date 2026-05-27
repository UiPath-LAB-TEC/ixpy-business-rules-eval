from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import apply_migrations
from .routes import routers


def create_app() -> FastAPI:
    settings = get_settings()
    apply_migrations(settings.db_path)
    app = FastAPI(title="business-rule-ui", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in routers:
        app.include_router(router)
    return app


app = create_app()
