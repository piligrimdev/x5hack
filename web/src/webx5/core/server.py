from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference

from webx5.routes.health import health_router

app = FastAPI(title="webx5", version="0.1.0", docs_url=None, redoc_url=None)

app.include_router(health_router)


@app.get("/docs", include_in_schema=False, response_class=HTMLResponse)
def scalar_docs() -> HTMLResponse:
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
