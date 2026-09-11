"""Alembic migration environment."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.models import Base

config = context.config

# `fileConfig` remplace la configuration du journal du **processus entier**, et
# `alembic.ini` y pose `[logger_root] level = WARN`. Lancé seul, c'est ce qu'on
# veut. Appelé depuis l'application, cela coupait tous les messages INFO pour
# le reste de l'exécution : sur 1 214 démarrages, aucun n'a jamais pu écrire
# « Alembic migrations applied successfully », ni le bilan du rattrapage des
# hashs qui le suit.
#
# Ce silence a coûté cher : il a contribué à masquer trois mois durant un
# rattrapage qui échouait à chaque démarrage.
#
# `configure_logger` est le drapeau que la documentation d'Alembic prévoit pour
# ce cas ; l'application le pose à faux.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
