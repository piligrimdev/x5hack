from webx5.crud.basket import BasketRepository
from webx5.services.basket_assistant import BasketService

basket_repo = BasketRepository()
basket_service = BasketService(repo=basket_repo)
