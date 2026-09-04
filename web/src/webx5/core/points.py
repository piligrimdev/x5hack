from webx5.crud.points import PointsRepository
from webx5.services.points import PointsService

points_repo = PointsRepository()
points_service = PointsService(repo=points_repo)
