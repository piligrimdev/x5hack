from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

# Decimal serialized as float in JSON responses (not string)
JsonDecimal = Annotated[Decimal, PlainSerializer(float, return_type=float)]
