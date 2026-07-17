#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKUP_DIR=${BACKUP_DIR:-"$ROOT_DIR/backups"}
COMPOSE_FILE=${COMPOSE_FILE:-"$ROOT_DIR/docker-compose.yml"}
POSTGRES_DB=${POSTGRES_DB:-meteoro}
POSTGRES_USER=${POSTGRES_USER:-meteoro}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTPUT="$BACKUP_DIR/meteoro_${STAMP}.dump"

mkdir -p "$BACKUP_DIR"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB" > "$OUTPUT"
sha256sum "$OUTPUT" > "$OUTPUT.sha256"
printf 'Backup criado: %s\nHash: %s\n' "$OUTPUT" "$OUTPUT.sha256"
