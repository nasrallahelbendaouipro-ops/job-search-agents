#!/usr/bin/env bash
#
# Durcissement du VPS pour un fonctionnement non surveillé.
#
# À exécuter une fois, en root, après l'installation décrite dans
# README-deploy.md. Le script est idempotent : le relancer ne casse rien.
#
#   bash deploy/harden-vps.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Ce script doit être lancé en root." >&2
    exit 1
fi

echo "==> Docker démarre automatiquement au boot"
# Sans ça, un redémarrage du VPS (mise à jour noyau, incident chez Hostinger)
# laisse la pile éteinte jusqu'à une intervention manuelle. Les conteneurs ont
# déjà `restart: unless-stopped`, mais ça ne vaut que si le démon tourne.
systemctl enable --now docker

echo "==> Timer du pipeline activé au boot"
systemctl enable agents-pipeline.timer 2>/dev/null || \
    echo "    (timer pas encore installé — voir l'étape 5 du README)"

echo "==> Mises à jour de sécurité automatiques"
# Correctifs de sécurité appliqués sans intervention. Les redémarrages ne sont
# PAS automatiques : un reboot surprise en pleine exécution est pire que le
# délai d'un correctif. On se contente de signaler qu'il est nécessaire.
export DEBIAN_FRONTEND=noninteractive
apt-get install -y unattended-upgrades apt-listchanges >/dev/null

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF

cat > /etc/apt/apt.conf.d/51unattended-upgrades-local <<'CONF'
// Sécurité uniquement : on ne veut pas qu'une montée de version mineure
// change le comportement d'un paquet pendant la nuit.
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
CONF

echo "==> Protection contre le bourrinage SSH"
apt-get install -y fail2ban >/dev/null
systemctl enable --now fail2ban

echo "==> Rotation des logs Docker"
# Doublon volontaire avec les limites déclarées dans docker-compose.yml :
# celles-ci ne s'appliquent qu'à nos conteneurs, ce réglage couvre le démon.
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
    cat > /etc/docker/daemon.json <<'CONF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
CONF
    systemctl restart docker
else
    echo "    /etc/docker/daemon.json existe déjà — laissé tel quel"
fi

echo
echo "==> Terminé. Vérifications :"
echo "    systemctl is-enabled docker agents-pipeline.timer fail2ban"
echo "    systemctl list-timers agents-pipeline.timer"
echo "    unattended-upgrades --dry-run --debug 2>&1 | tail -5"
