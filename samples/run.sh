#!/usr/bin/env bash
# Teste ARES contre le service IA en cours d'exécution, avec les données de ce dossier.
#
# Prérequis : le service tourne (ex. `make run` → http://localhost:8080).
# Variables (optionnelles) :
#   AI_URL   (défaut http://localhost:8080)
#   AI_KEY   (défaut demo-secret) — doit correspondre à INTERNAL_API_KEY du .env
set -uo pipefail

AI_URL="${AI_URL:-http://localhost:8080}"
AI_KEY="${AI_KEY:-demo-secret}"
DIR="$(cd "$(dirname "$0")" && pwd)"
H=(-H "X-Internal-Key: ${AI_KEY}" -H "Content-Type: application/json")

pp() { if command -v python3 >/dev/null; then python3 -m json.tool 2>/dev/null || cat; else cat; fi; }
call() { # méthode url [fichier]
  local code
  code=$(curl -s -o /tmp/ares_out.json -w "%{http_code}" "${H[@]}" -X "$1" "$2" ${3:+--data @"$3"})
  echo "  [HTTP $code]"; pp < /tmp/ares_out.json; echo
}

echo "############################################################"
echo "# Service : $AI_URL"
echo "############################################################"

echo; echo "### /health (public) ###"
curl -s "$AI_URL/health" | pp; echo

echo; echo "======================================================"
echo " ✅ MARCHE SANS CLÉ CLAUDE (logique pure / déterministe)"
echo "======================================================"

echo; echo "### /score — lead DANS l'ICP (score élevé attendu) ###"
call POST "$AI_URL/api/v1/ares/score" "$DIR/score_bon.json"

echo "### /score — lead HORS-ICP (secteur exclu → fit 0, score bas) ###"
call POST "$AI_URL/api/v1/ares/score" "$DIR/score_hors_icp.json"

echo "### /score — lead INCOMPLET (faible complétude) ###"
call POST "$AI_URL/api/v1/ares/score" "$DIR/score_incomplet.json"

echo "### /decide — plafond de relance ATTEINT (3/3 → 'arrêt', déterministe) ###"
call POST "$AI_URL/api/v1/ares/decide" "$DIR/decide_plafond.json"

echo "### /costs — coûts cumulés du workspace ###"
call GET "$AI_URL/api/v1/costs/11111111-1111-1111-1111-111111111111"

echo; echo "======================================================"
echo " ⚠️  NÉCESSITE ANTHROPIC_API_KEY (sinon 503 propre)"
echo "======================================================"

echo; echo "### /qualify (Claude Sonnet) ###"
call POST "$AI_URL/api/v1/ares/qualify" "$DIR/qualify.json"

echo "### /classify (Claude Haiku) ###"
call POST "$AI_URL/api/v1/ares/classify" "$DIR/classify.json"

echo "### /generate (Claude Sonnet) ###"
call POST "$AI_URL/api/v1/ares/generate" "$DIR/generate.json"

echo "### /decide — plafond NON atteint (1/3 → décision via Claude) ###"
call POST "$AI_URL/api/v1/ares/decide" "$DIR/decide_continuer.json"
