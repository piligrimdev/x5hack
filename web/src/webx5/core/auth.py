from webx5.crud.user import UserRepository
from webx5.services.auth import AuthService

user_repo = UserRepository()
auth_service = AuthService(user_repo=user_repo)
