from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings

engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
_is_sqlite = settings.database_url.startswith("sqlite")
if _is_sqlite:
    # timeout: espera o lock em vez de falhar de imediato quando API e worker
    # escrevem ao mesmo tempo (cenário de desenvolvimento com dois processos).
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.database_url, **engine_kwargs)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        """WAL permite um escritor e vários leitores simultâneos.

        Sem isso, rodar a API e o worker de ingestão juntos produz
        'database is locked' intermitente. Em produção o banco é
        PostgreSQL/PostGIS e estas diretivas não se aplicam.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
