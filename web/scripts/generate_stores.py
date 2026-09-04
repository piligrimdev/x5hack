"""Generate demo stores: X5 Group chains × Moscow districts.

Creates StoreFormats for each chain and one Store per (chain, district) pair.
Idempotent: skips already-existing formats and stores.

Config via env vars:
  DATABASE_URL   PostgreSQL connection string
"""

import os
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "web" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

from sqlalchemy import select  # noqa: E402

from webx5.core.db import db  # noqa: E402
from webx5.entities.store import Store, StoreFormat  # noqa: E402

# X5 Group chains
CHAINS = ["Пятёрочка", "Перекрёсток", "Чижик"]

# Moscow districts → geo_cluster
DISTRICTS = [
    ("d_01", "ЦАО",  ["ул. Тверская, 14", "ул. Арбат, 22", "ул. Пречистенка, 5"]),
    ("d_02", "САО",  ["Ленинградский пр-т, 60", "ул. Дмитровская, 18", "Волоколамское ш., 3"]),
    ("d_03", "СВАО", ["пр-т Мира, 105", "Ярославское ш., 12", "ул. Лосиноостровская, 7"]),
    ("d_04", "ВАО",  ["Щёлковское ш., 25", "ул. Измайловская, 44", "Сиреневый б-р, 8"]),
    ("d_05", "ЮВАО", ["ул. Люблинская, 34", "Рязанский пр-т, 90", "ул. Марьинская, 2"]),
    ("d_06", "ЮАО",  ["Каширское ш., 56", "ул. Варшавская, 71", "Балаклавский пр-т, 14"]),
    ("d_07", "ЮЗАО", ["Ленинский пр-т, 117", "ул. Профсоюзная, 128", "Новочерёмушкинская ул., 5"]),
    ("d_08", "ЗАО",  ["Кутузовский пр-т, 48", "ул. Молодогвардейская, 3", "Рублёвское ш., 20"]),
    ("d_09", "СЗАО", ["Волоколамское ш., 88", "ул. Маршала Жукова, 41", "ул. Твардовского, 9"]),
    ("d_10", "ЗелАО", ["Крюковская пл., 1", "ул. Юности, 6", "Панфиловский пр-т, 21"]),
]

# Not every chain goes to every district — mirrors realistic coverage
COVERAGE: dict[str, list[str]] = {
    "Пятёрочка": ["d_01", "d_02", "d_03", "d_04", "d_05", "d_06", "d_07", "d_08", "d_09", "d_10"],
    "Перекрёсток": ["d_01", "d_02", "d_03", "d_05", "d_06", "d_07", "d_08"],
    "Чижик":       ["d_02", "d_04", "d_05", "d_06", "d_07", "d_09", "d_10"],
}

# Address index per (chain, district) — rotate through 3 addresses per district
ADDRESS_IDX: dict[str, int] = {"Пятёрочка": 0, "Перекрёсток": 1, "Чижик": 2}


def main() -> None:
    district_map = {did: (geo, addrs) for did, geo, addrs in DISTRICTS}

    formats_created = stores_created = skipped = 0

    with db.get_sync_session() as session:
        # 1. Ensure StoreFormats exist
        format_by_name: dict[str, StoreFormat] = {}
        for chain in CHAINS:
            existing = session.scalar(select(StoreFormat).where(StoreFormat.name == chain))
            if existing:
                format_by_name[chain] = existing
            else:
                fmt = StoreFormat(id=uuid.uuid4(), name=chain)
                session.add(fmt)
                session.flush()
                format_by_name[chain] = fmt
                formats_created += 1
                print(f"  Формат создан: {chain}")

        # 2. Create stores
        for chain, district_ids in COVERAGE.items():
            fmt = format_by_name[chain]
            addr_idx = ADDRESS_IDX[chain]

            for did in district_ids:
                geo, addrs = district_map[did]
                address = addrs[addr_idx % len(addrs)]

                existing = session.scalar(
                    select(Store).where(Store.format_id == fmt.id, Store.geo_cluster == did)
                )
                if existing:
                    skipped += 1
                    continue

                store = Store(
                    id=uuid.uuid4(),
                    format_id=fmt.id,
                    geo_cluster=did,
                    address=f"{chain}, {address}",
                )
                session.add(store)
                stores_created += 1
                print(f"  Магазин: {chain} / {geo} ({did}) — {address}")

        session.commit()

    print(f"\nГотово. Форматов создано: {formats_created}, магазинов создано: {stores_created}, пропущено: {skipped}")


if __name__ == "__main__":
    main()
