from fastapi import FastAPI

from webx5.routes.health import health_router

app = FastAPI(title="webx5", version="0.1.0")

app.include_router(health_router)
