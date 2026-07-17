#!/bin/sh
# Sidecar de backup da produção assistida.
# Executa um backup na subida (evidência imediata) e depois um por dia no
# horário BACKUP_HOUR_UTC, com retenção de BACKUP_RETENTION_DAYS dias.
# Conteúdo: dump do PostgreSQL (formato custom + sha256) e tar dos payloads brutos.
set -eu

: "${PGHOST:=postgres}"
: "${POSTGRES_DB:=meteoro}"
: "${POSTGRES_USER:=meteoro}"
: "${BACKUP_RETENTION_DAYS:=30}"
: "${BACKUP_HOUR_UTC:=02}"
export PGPASSWORD="${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD}"

backup_once() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  db_file="/backups/meteoro_${stamp}.dump"
  raw_file="/backups/raw_${stamp}.tar.gz"

  echo "[backup] iniciando ${stamp}"
  pg_dump --format=custom --no-owner --no-privileges \
    -h "$PGHOST" -U "$POSTGRES_USER" "$POSTGRES_DB" > "$db_file"
  (cd /backups && sha256sum "$(basename "$db_file")" > "$db_file.sha256")

  if [ -d /raw ] && [ -n "$(ls -A /raw 2>/dev/null)" ]; then
    tar -czf "$raw_file" -C /raw .
    (cd /backups && sha256sum "$(basename "$raw_file")" > "$raw_file.sha256")
  fi

  find /backups -type f -mtime +"$BACKUP_RETENTION_DAYS" -delete
  echo "[backup] concluído: $(ls -sh "$db_file" | awk '{print $1}') em ${db_file}"
}

seconds_until_next_run() {
  now=$(date -u +%s)
  target=$(date -u -d "$(date -u +%Y-%m-%d) ${BACKUP_HOUR_UTC}:00:00" +%s)
  [ "$target" -le "$now" ] && target=$((target + 86400))
  echo $((target - now))
}

# Evidência imediata na subida do serviço.
backup_once

while true; do
  wait_seconds=$(seconds_until_next_run)
  echo "[backup] próximo ciclo em ${wait_seconds}s"
  sleep "$wait_seconds"
  backup_once || echo "[backup] FALHA no ciclo $(date -u +%FT%TZ)" >&2
done
