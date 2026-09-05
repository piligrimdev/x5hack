import os

from webx5.core.purchases import discount_calculator_service, receipt_repo, receipt_service
from webx5.crud.basket import BasketRepository
from webx5.crud.store import StoreRepository
from webx5.services.basket_assistant import BasketService

BASKET_LLM_MODEL = os.environ.get("BASKET_LLM_MODEL", "anthropic/claude-haiku-4.5")

basket_repo = BasketRepository()
basket_service = BasketService(
    repo=basket_repo,
    receipt_repo=receipt_repo,
    store_repo=StoreRepository(),
    discount_calc=discount_calculator_service,
    receipt_service=receipt_service,
    model=BASKET_LLM_MODEL,
)
