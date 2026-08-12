from __future__ import annotations

from app.config import get_settings
from app.database import build_engine, create_schema, resolve_database_url


def main() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    create_schema(engine)
    print({"status": "ok", "database_url": resolve_database_url(settings)})


if __name__ == "__main__":
    main()
