import os

from webx5.core.points import points_service
from webx5.core.purchases import discount_calculator_service, receipt_repo, receipt_service
from webx5.crud.basket import BasketRepository
from webx5.crud.store import StoreRepository
from webx5.services.basket_assistant import BasketService

BASKET_LLM_MODEL = os.environ.get("BASKET_LLM_MODEL", "google/gemini-3.1-flash-lite")

basket_repo = BasketRepository()
basket_service = BasketService(
    repo=basket_repo,
    receipt_repo=receipt_repo,
    store_repo=StoreRepository(),
    discount_calc=discount_calculator_service,
    receipt_service=receipt_service,
    points_service=points_service,
    model=BASKET_LLM_MODEL,
)
