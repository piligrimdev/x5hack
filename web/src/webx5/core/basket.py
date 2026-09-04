import os

from webx5.crud.basket import BasketRepository
from webx5.services.basket_assistant import BasketService

BASKET_LLM_MODEL = os.environ.get("BASKET_LLM_MODEL", "anthropic/claude-haiku-4.5")

basket_repo = BasketRepository()
basket_service = BasketService(repo=basket_repo, model=BASKET_LLM_MODEL)
