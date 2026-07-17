"""Criação de schema para ambientes efêmeros.

ATENÇÃO: o caminho canônico para criar/atualizar o banco é `alembic upgrade head`,
que aplica a cadeia de migrações e grava `alembic_version`. Este módulo existe
apenas para cenários de teste/descartáveis. Um banco criado por `create_all`
não tem `alembic_version` e não deve ser usado em operação.
"""

from app.db.base import Base
from app.db.session import engine

# Todos os módulos com models precisam ser importados para registrar as
# tabelas no metadata. Manter em ordem alfabética e completo — um import
# faltante gera banco sem as tabelas daquele módulo (bug real: incidents
# ausente em bancos criados por versões anteriores deste arquivo).
from app.modules.alerts import models as alerts_models  # noqa: F401
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.catalog import models as catalog_models  # noqa: F401
from app.modules.communications import models as communications_models  # noqa: F401
from app.modules.data_quality import models as data_quality_models  # noqa: F401
from app.modules.geospatial import models as geospatial_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.incidents import models as incidents_models  # noqa: F401
from app.modules.ingestion import models as ingestion_models  # noqa: F401
from app.modules.planning import models as planning_models  # noqa: F401
from app.modules.recommendations import models as recommendations_models  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
