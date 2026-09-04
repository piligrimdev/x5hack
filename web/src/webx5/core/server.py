from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi_pagination import add_pagination
from scalar_fastapi import get_scalar_api_reference

from webx5.routes.auth import auth_router
from webx5.routes.basket import basket_router
from webx5.routes.catalog import catalog_router
from webx5.routes.discounts import discounts_router
from webx5.routes.health import health_router
from webx5.routes.receipts import receipts_router
from webx5.routes.stores import stores_router

app = FastAPI(title="webx5", version="0.1.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(basket_router)
app.include_router(catalog_router)
app.include_router(receipts_router)
app.include_router(stores_router)
app.include_router(discounts_router)

add_pagination(app)


@app.get("/docs", include_in_schema=False, response_class=HTMLResponse)
def scalar_docs() -> HTMLResponse:
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
