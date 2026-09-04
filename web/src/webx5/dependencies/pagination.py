from typing import Annotated

from fastapi import Depends
from fastapi_pagination import Params


def get_pagination_params(page: int = 1, size: int = 20) -> Params:
    size = min(size, 100)
    return Params(page=page, size=size)


PaginationParams = Annotated[Params, Depends(get_pagination_params)]
