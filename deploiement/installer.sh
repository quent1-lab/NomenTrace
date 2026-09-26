#!/usr/bin/env bash
# Installation de Nomentrace sur une VM Ubuntu 24.04 neuve (Oracle Cloud ou autre).
#
#   sudo bash installer.sh DOMAINE [--courriel ADRESSE] [--depot URL] [--version VERSION]
#
# DOMAINE      nom sous lequel l'outil sera servi en HTTPS ; il doit déjà désigner la VM
# --courriel   adresse de contact transmise à Let's Encrypt (facultative)
# --depot      dépôt git à installer (par défaut le dépôt public de Nomentrace)
# --version    étiquette, branche ou commit (par défaut la dernière étiquette v*, sinon main)
#
# Le script peut être relancé : il ne remplace ni les réglages ni les données existants.
set -euo pipefail

DEPOT_DEFAUT=https://github.com/quent1-lab/NomenTrace.git
APP=/opt/nomentrace
DONNEES=/var/lib/nomentrace
CONF=/etc/nomentrace
PORT=8000

etape() {
	echo
	echo "== $*"
}

usage() {
	sed -n '2,11p' "$0" >&2
	exit 1
}

installer_paquets() {
	etape "Fuseau horaire Europe/Paris (horodatages et retards de livraison en heure locale)"
	timedatectl set-timezone Europe/Paris
	etape "Paquets système"
	export DEBIAN_FRONTEND=noninteractive
	apt-get update -q
	apt-get install -y -q software-properties-common curl git age sqlite3 \
		debian-keyring debian-archive-keyring apt-transport-https gnupg
	# Python 3.14 : absent des dépôts d'Ubuntu 24.04, fourni pour arm64 et amd64 par deadsnakes.
	if ! command -v python3.14 >/dev/null; then
		add-apt-repository -y ppa:deadsnakes/ppa
	fi
	# Caddy : dépôt officiel, plus récent que celui d'Ubuntu.
	if [[ ! -f /etc/apt/sources.list.d/caddy-stable.list ]]; then
		curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key |
			gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
		curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
			>/etc/apt/sources.list.d/caddy-stable.list
		chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
			/etc/apt/sources.list.d/caddy-stable.list
	fi
	apt-get update -q
	apt-get install -y -q python3.14 python3.14-venv caddy
}

ouvrir_pare_feu() {
	etape "Pare-feu de la VM : ports 80 et 443"
	# Les images Ubuntu d'Oracle finissent la chaîne INPUT par un REJECT : les règles
	# d'ouverture doivent passer avant lui.
	local port ligne
	for port in 80 443; do
		if iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
			continue
		fi
		ligne="$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')"
		if [[ -n $ligne ]]; then
			iptables -I INPUT "$ligne" -p tcp -m state --state NEW --dport "$port" -j ACCEPT
		else
			iptables -A INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT
		fi
	done
	if command -v netfilter-persistent >/dev/null; then
		netfilter-persistent save
	else
		echo "netfilter-persistent absent : règles non enregistrées pour le prochain démarrage." >&2
	fi
}

installer_code() {
	local depot="$1" version="$2"
	etape "Utilisateur système et dossiers"
	if ! id nomentrace >/dev/null 2>&1; then
		useradd --system --user-group --home-dir "$DONNEES" --shell /usr/sbin/nologin nomentrace
	fi
	install -d -o nomentrace -g nomentrace -m 750 "$DONNEES" "$DONNEES/data" "$DONNEES/echange"
	install -d -m 700 /var/backups/nomentrace
	install -d -m 755 "$CONF"

	etape "Code de l'application"
	if [[ ! -d $APP/.git ]]; then
		git clone --quiet "$depot" "$APP"
	fi
	git -C "$APP" fetch --quiet --tags --prune --force origin
	if [[ -z $version ]]; then
		version="$(git -C "$APP" tag --list 'v*' --sort=-v:refname | head -n 1)"
		if [[ -z $version ]]; then
			version=origin/main
			echo "Aucune étiquette v* publiée : installation de la branche main."
		fi
	elif git -C "$APP" rev-parse --quiet --verify "origin/$version^{commit}" >/dev/null; then
		version="origin/$version"
	fi
	git -C "$APP" checkout --quiet --force --detach "$version"
	echo "Version installée : $version ($(git -C "$APP" rev-parse --short HEAD))"

	etape "Environnement Python"
	if [[ ! -x $APP/.venv/bin/python ]]; then
		python3.14 -m venv "$APP/.venv"
	fi
	"$APP/.venv/bin/pip" install --quiet --disable-pip-version-check -r "$APP/requirements.txt"
}

ecrire_reglages() {
	local domaine="$1" courriel="$2"
	etape "Réglages dans $CONF"
	if [[ ! -f $CONF/nomentrace.env ]]; then
		sed -e "s|__DOMAINE__|$domaine|g" -e "s|__PORT__|$PORT|g" \
			"$APP/deploiement/nomentrace.env.exemple" >"$CONF/nomentrace.env"
		chmod 644 "$CONF/nomentrace.env"
	else
		echo "$CONF/nomentrace.env existe déjà : gardé tel quel."
	fi
	if [[ ! -f $CONF/sauvegarde.env ]]; then
		install -m 600 "$APP/deploiement/sauvegarde.env.exemple" "$CONF/sauvegarde.env"
	fi
	if [[ ! -f $CONF/cles_sauvegarde.txt ]]; then
		echo "# Clés publiques age autorisées à relire les sauvegardes, une par ligne." \
			>"$CONF/cles_sauvegarde.txt"
		chmod 644 "$CONF/cles_sauvegarde.txt"
	fi

	etape "Caddy pour $domaine"
	local contact="# aucune adresse de contact"
	if [[ -n $courriel ]]; then
		contact="email $courriel"
	fi
	sed -e "s|__DOMAINE__|$domaine|g" -e "s|__PORT__|$PORT|g" -e "s|__COURRIEL__|$contact|g" \
		"$APP/deploiement/Caddyfile.modele" >/etc/caddy/Caddyfile
	caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
	systemctl reload-or-restart caddy
}

demarrer() {
	etape "Services"
	install -m 644 "$APP"/deploiement/systemd/* /etc/systemd/system/
	systemctl daemon-reload
	systemctl enable --now nomentrace
	for _ in $(seq 1 60); do
		if curl --fail --silent --max-time 2 "http://127.0.0.1:$PORT/api/sante" |
			grep -q '"statut":"ok"'; then
			echo "Nomentrace répond sur 127.0.0.1:$PORT."
			return 0
		fi
		sleep 1
	done
	echo "Nomentrace ne répond pas : voir journalctl -u nomentrace." >&2
	return 1
}

main() {
	if [[ $EUID -ne 0 ]]; then
		echo "À lancer avec sudo." >&2
		exit 1
	fi
	[[ $# -ge 1 && $1 != -* ]] || usage
	local domaine="$1" courriel="" depot="$DEPOT_DEFAUT" version=""
	shift
	while [[ $# -gt 0 ]]; do
		[[ $# -ge 2 ]] || usage
		case "$1" in
		--courriel) courriel="$2" ;;
		--depot) depot="$2" ;;
		--version) version="$2" ;;
		*) usage ;;
		esac
		shift 2
	done
	installer_paquets
	ouvrir_pare_feu
	installer_code "$depot" "$version"
	ecrire_reglages "$domaine" "$courriel"
	demarrer
	etape "Installation terminée"
	echo "Étapes suivantes, détaillées dans deploiement/README.md :"
	echo "  1. premier administrateur :"
	echo "     sudo bash $APP/deploiement/commande.sh comptes creer-admin ADRESSE --nom \"Prénom Nom\""
	echo "  2. sauvegarde nocturne : renseigner $CONF/sauvegarde.env et $CONF/cles_sauvegarde.txt,"
	echo "     puis sudo systemctl enable --now nomentrace-sauvegarde.timer"
	echo "  3. mises à jour automatiques (facultatif) :"
	echo "     sudo systemctl enable --now nomentrace-maj.timer"
}

main "$@"
