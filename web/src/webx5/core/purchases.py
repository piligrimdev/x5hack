from webx5.crud.discount import DiscountRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.services.discount_calculator import DiscountCalculatorService
from webx5.services.receipt import ReceiptService

discount_repo = DiscountRepository()
receipt_repo = ReceiptRepository()

discount_calculator_service = DiscountCalculatorService(discount_repo=discount_repo)
receipt_service = ReceiptService(receipt_repo=receipt_repo, discount_repo=discount_repo)
