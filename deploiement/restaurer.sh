#!/usr/bin/env bash
# Restaure une archive complète sur le serveur.
#
#   sudo bash /opt/nomentrace/deploiement/restaurer.sh ARCHIVE.zip [--sans-documents]
#   sudo bash /opt/nomentrace/deploiement/restaurer.sh ARCHIVE.zip.age --cle CLE.txt
#
# Une archive chiffrée se déchiffre avec la clé privée age, déposée sur le serveur le temps
# de l'opération seulement : l'effacer aussitôt après. Les bases en place sont sauvegardées
# et les documents courants mis de côté avant d'être remplacés.
set -euo pipefail

DEPLOIEMENT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_INSTANCE=/etc/nomentrace/nomentrace.env

usage() {
	echo "Usage : sudo bash $0 ARCHIVE(.zip|.zip.age) [--cle CLE_PRIVEE] [--sans-documents]" >&2
	exit 1
}

repond() {
	for _ in $(seq 1 60); do
		if curl --fail --silent --max-time 2 "http://${NOMENTRACE_HOTE}:${NOMENTRACE_PORT}/api/sante" |
			grep -q '"statut":"ok"'; then
			return 0
		fi
		sleep 1
	done
	return 1
}

main() {
	if [[ $EUID -ne 0 ]]; then
		echo "À lancer avec sudo." >&2
		exit 1
	fi
	[[ $# -ge 1 ]] || usage
	local archive="$1" cle="" options=()
	shift
	while [[ $# -gt 0 ]]; do
		case "$1" in
		--cle)
			[[ $# -ge 2 ]] || usage
			cle="$2"
			shift 2
			;;
		--sans-documents)
			options+=(--sans-documents)
			shift
			;;
		*) usage ;;
		esac
	done
	if [[ ! -f $archive ]]; then
		echo "Archive introuvable : $archive" >&2
		exit 1
	fi
	set -a
	# shellcheck source=/dev/null
	. "$ENV_INSTANCE"
	set +a

	local travail
	travail="$(mktemp -d)"
	trap 'rm -rf "$travail"' EXIT
	if [[ $archive == *.age ]]; then
		if [[ -z $cle || ! -f $cle ]]; then
			echo "Archive chiffrée : préciser --cle CLE_PRIVEE." >&2
			exit 1
		fi
		age --decrypt --identity "$cle" --output "$travail/archive.zip" "$archive"
	else
		cp "$archive" "$travail/archive.zip"
	fi
	chown -R nomentrace:nomentrace "$travail"

	echo "Arrêt de Nomentrace."
	systemctl stop nomentrace
	if ! bash "$DEPLOIEMENT/commande.sh" sauvegarde restaurer "$travail/archive.zip" "${options[@]}"; then
		echo "Restauration refusée, rien n'a été modifié. Redémarrage." >&2
		systemctl start nomentrace
		exit 1
	fi
	systemctl start nomentrace
	if repond; then
		echo "Nomentrace répond : restauration terminée."
		exit 0
	fi
	echo "Nomentrace ne répond pas après la restauration : voir journalctl -u nomentrace." >&2
	exit 1
}

main "$@"
