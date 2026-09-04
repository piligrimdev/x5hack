from webx5.crud.catalog import CatalogRepository
from webx5.services.catalog import CatalogService

catalog_repo = CatalogRepository()
catalog_service = CatalogService(repo=catalog_repo)
