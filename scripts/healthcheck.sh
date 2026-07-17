#!/usr/bin/env sh
set -eu

BASE_URL="${1:-http://localhost:8000}"

echo "Verificando ${BASE_URL}/health"
curl --fail --silent --show-error "${BASE_URL}/health"
echo
echo "Saúde HTTP disponível. Para a rotina completa, confira no portal operacional: fontes, jobs, fila suspeita e alertas técnicos."
