#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "Uso: $0 CAMINHO_DO_BACKUP.dump BANCO_DE_TESTE" >&2
  exit 64
fi

BACKUP_FILE=$1
TARGET_DB=$2
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-"$ROOT_DIR/docker-compose.yml"}
POSTGRES_USER=${POSTGRES_USER:-meteoro}

case "$TARGET_DB" in
  meteoro|postgres|template0|template1)
    echo "A restauração exige um banco de teste distinto de '$TARGET_DB'." >&2
    exit 65
    ;;
esac

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Arquivo de backup não encontrado: $BACKUP_FILE" >&2
  exit 66
fi

case "$TARGET_DB" in
  [A-Za-z][A-Za-z0-9_]* ) ;;
  *)
    echo "Nome de banco inválido; use letras, números e sublinhado." >&2
    exit 67
    ;;
esac

if [ -f "$BACKUP_FILE.sha256" ]; then
  (cd "$(dirname -- "$BACKUP_FILE")" && sha256sum -c "$(basename -- "$BACKUP_FILE").sha256")
fi

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$TARGET_DB\";"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
  -c "CREATE DATABASE \"$TARGET_DB\";"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$TARGET_DB" < "$BACKUP_FILE"
printf 'Restauração concluída no banco de teste: %s\n' "$TARGET_DB"
