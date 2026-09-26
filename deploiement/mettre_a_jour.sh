#!/usr/bin/env bash
# Met Nomentrace à jour, et revient à la version précédente si elle ne répond pas.
#
#   sudo bash /opt/nomentrace/deploiement/mettre_a_jour.sh           dernière étiquette v*
#   sudo bash /opt/nomentrace/deploiement/mettre_a_jour.sh v1.2      version précise
#   sudo bash /opt/nomentrace/deploiement/mettre_a_jour.sh main      tête d'une branche
#   sudo bash /opt/nomentrace/deploiement/mettre_a_jour.sh --auto    minuterie : seulement
#                                                                    une étiquette plus récente
#
# Étapes : arrêt du service, copie des deux bases, passage à la version voulue, dépendances,
# redémarrage, contrôle de /api/sante. En cas d'échec : retour au code précédent et remise
# des bases copiées, car une mise à jour de schéma appliquée ne se défait pas autrement.
set -euo pipefail

APP=/opt/nomentrace
ENV_INSTANCE=/etc/nomentrace/nomentrace.env
INSTANTANES=/var/backups/nomentrace
NB_INSTANTANES=5

journal() { echo "[$(date '+%F %T')] $*"; }

# Contrôle de santé : le service répond « ok » dans les 60 secondes.
verifier() {
	for _ in $(seq 1 60); do
		if curl --fail --silent --max-time 2 "http://${NOMENTRACE_HOTE}:${NOMENTRACE_PORT}/api/sante" |
			grep -q '"statut":"ok"'; then
			return 0
		fi
		sleep 1
	done
	return 1
}

# Unités systemd du dépôt recopiées si elles ont changé avec la version.
installer_unites() {
	local unite change=0
	for unite in "$APP"/deploiement/systemd/*; do
		if ! cmp -s "$unite" "/etc/systemd/system/$(basename "$unite")"; then
			install -m 644 "$unite" /etc/systemd/system/
			change=1
		fi
	done
	if [[ $change -eq 1 ]]; then systemctl daemon-reload; fi
}

# Appelée dans un test « if » : chaque étape vérifie elle-même son succès.
installer_code() {
	git -C "$APP" checkout --quiet --force --detach "$1" || return 1
	"$APP/.venv/bin/pip" install --quiet --disable-pip-version-check 		-r "$APP/requirements.txt" || return 1
	installer_unites
}

chemin_base() {
	if [[ $1 == base ]]; then echo "$NOMENTRACE_BASE"; else echo "$NOMENTRACE_COMPTES"; fi
}

# Copie des bases, service arrêté : fichier principal et éventuels journaux WAL.
copier_bases() {
	local cible="$1" nom chemin suffixe
	for nom in base comptes; do
		chemin="$(chemin_base "$nom")"
		mkdir -p "$cible/$nom"
		for suffixe in "" -wal -shm; do
			if [[ -e "$chemin$suffixe" ]]; then cp -a "$chemin$suffixe" "$cible/$nom/"; fi
		done
	done
}

remettre_bases() {
	local source="$1" nom chemin
	for nom in base comptes; do
		chemin="$(chemin_base "$nom")"
		rm -f "$chemin" "$chemin-wal" "$chemin-shm"
		if compgen -G "$source/$nom/*" >/dev/null; then
			cp -a "$source/$nom/." "$(dirname "$chemin")/"
		fi
	done
}

choisir_version() {
	local demande="$1"
	if [[ -z $demande || $demande == --auto ]]; then
		git -C "$APP" tag --list 'v*' --sort=-v:refname | head -n 1
	elif git -C "$APP" rev-parse --quiet --verify "origin/$demande^{commit}" >/dev/null; then
		echo "origin/$demande"
	else
		echo "$demande"
	fi
}

main() {
	if [[ $EUID -ne 0 ]]; then
		echo "À lancer avec sudo." >&2
		exit 1
	fi
	exec 9>/run/nomentrace-maj.lock
	if ! flock --nonblock 9; then
		echo "Une mise à jour est déjà en cours." >&2
		exit 1
	fi
	set -a
	# shellcheck source=/dev/null
	. "$ENV_INSTANCE"
	set +a

	local demande="${1:-}" version cible actuel horodatage instantane
	git -C "$APP" fetch --quiet --tags --prune --force origin
	version="$(choisir_version "$demande")"
	if [[ -z $version ]]; then
		echo "Aucune étiquette v* publiée : préciser la version voulue." >&2
		exit 1
	fi
	if ! cible="$(git -C "$APP" rev-parse --quiet --verify "$version^{commit}")"; then
		echo "Version « $version » introuvable dans le dépôt." >&2
		exit 1
	fi
	actuel="$(git -C "$APP" rev-parse HEAD)"
	if [[ $cible == "$actuel" ]]; then
		[[ $demande == --auto ]] || journal "Déjà en version $version."
		exit 0
	fi
	# La minuterie ne fait qu'avancer : une version posée à la main n'est pas défaite.
	if [[ $demande == --auto ]] && git -C "$APP" merge-base --is-ancestor "$cible" "$actuel"; then
		exit 0
	fi

	horodatage="$(date +%Y%m%d_%H%M%S)"
	instantane="$INSTANTANES/$horodatage"
	journal "Mise à jour vers $version ($(git -C "$APP" rev-parse --short "$cible"))."
	systemctl stop nomentrace
	install -d -m 700 "$instantane"
	copier_bases "$instantane"
	echo "$actuel" >"$instantane/commit"
	journal "Bases copiées dans $instantane."

	if installer_code "$cible" && systemctl start nomentrace && verifier; then
		journal "Nomentrace répond en version $version."
		find "$INSTANTANES" -mindepth 1 -maxdepth 1 -type d | sort | head -n "-$NB_INSTANTANES" |
			xargs --no-run-if-empty rm -rf
		exit 0
	fi

	journal "Contrôle échoué : retour à la version précédente."
	journalctl --unit nomentrace --since "-3 min" --no-pager | tail -n 30 || true
	systemctl stop nomentrace || true
	installer_code "$actuel"
	remettre_bases "$instantane"
	systemctl start nomentrace
	if verifier; then
		journal "Version précédente rétablie, bases remises à l'état d'avant la mise à jour."
		exit 1
	fi
	journal "ÉCHEC : la version précédente ne répond pas non plus. Voir journalctl -u nomentrace."
	exit 2
}

main "$@"
