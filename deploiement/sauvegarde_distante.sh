#!/usr/bin/env bash
# Sauvegarde nocturne, lancée par nomentrace-sauvegarde.service : archive complète (base
# du projet, base des comptes, documents et corbeille), chiffrée par age pour les clés
# publiques configurées, puis envoyée dans le bucket par la demande pré-authentifiée.
# L'archive en clair ne quitte jamais le serveur et n'y reste pas.
set -euo pipefail
umask 077

: "${NOMENTRACE_SAUVEGARDE_URL:?NOMENTRACE_SAUVEGARDE_URL est vide : voir /etc/nomentrace/sauvegarde.env}"
: "${NOMENTRACE_SAUVEGARDE_CLES:?NOMENTRACE_SAUVEGARDE_CLES est vide : voir /etc/nomentrace/sauvegarde.env}"
if ! grep -q '^age1' "$NOMENTRACE_SAUVEGARDE_CLES" 2>/dev/null; then
	echo "Aucune clé publique age dans $NOMENTRACE_SAUVEGARDE_CLES : sauvegarde non chiffrable." >&2
	exit 1
fi

racine="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
travail="$(mktemp -d)"
trap 'rm -rf "$travail"' EXIT

nom="nomentrace_${NOMENTRACE_PROJET:-principal}_$(date +%Y%m%d_%H%M%S).zip.age"
cd "$racine"
"$racine/.venv/bin/python" -m backend.sauvegarde archive "$travail/archive.zip" >/dev/null
age --encrypt --recipients-file "$NOMENTRACE_SAUVEGARDE_CLES" \
	--output "$travail/$nom" "$travail/archive.zip"
rm -f "$travail/archive.zip"

curl --fail --silent --show-error --retry 3 --retry-delay 60 \
	--upload-file "$travail/$nom" "${NOMENTRACE_SAUVEGARDE_URL%/}/$nom"
echo "Sauvegarde envoyée : $nom ($(stat -c %s "$travail/$nom") octets)."
