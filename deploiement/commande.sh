#!/usr/bin/env bash
# Lance une commande de Nomentrace sous l'utilisateur nomentrace, avec les réglages de
# l'instance, comme le ferait le service.
#
#   sudo bash /opt/nomentrace/deploiement/commande.sh comptes creer-admin ADRESSE --nom NOM
#   sudo bash /opt/nomentrace/deploiement/commande.sh sauvegarde archive /tmp/archive.zip
#
# Le premier argument désigne le module backend.MODULE ; les suivants lui sont passés.
set -euo pipefail

APP=/opt/nomentrace
ENV_INSTANCE=/etc/nomentrace/nomentrace.env

if [[ $EUID -ne 0 ]]; then
	echo "À lancer avec sudo." >&2
	exit 1
fi
if [[ $# -lt 1 ]]; then
	echo "Usage : sudo bash $0 MODULE [ARGUMENTS…]   (MODULE : comptes, sauvegarde)" >&2
	exit 1
fi

module="$1"
shift
exec systemd-run --quiet --wait --pipe --collect \
	--uid=nomentrace --gid=nomentrace \
	--property=EnvironmentFile="$ENV_INSTANCE" \
	--property=WorkingDirectory="$APP" \
	--property=UMask=0027 \
	"$APP/.venv/bin/python" -m "backend.$module" "$@"
