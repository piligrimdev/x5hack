import os
from pathlib import Path

import structlog
import uvicorn
from dotenv import load_dotenv

from webx5.core.logging_config import configure_logging, default_log_dir

_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()
configure_logging()

structlog.get_logger("app.startup").info(
    "app.starting",
    service=os.getenv("SERVICE_NAME", "webx5"),
    log_dir=str(default_log_dir()),
)


def main() -> None:
    from webx5.core.server import app

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
