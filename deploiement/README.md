# Héberger Nomentrace sur un serveur

Ce guide installe Nomentrace sur une machine virtuelle Linux, servie en HTTPS sous un nom
de domaine, avec une sauvegarde chiffrée envoyée chaque nuit hors de la machine et des
mises à jour qui reviennent seules en arrière quand elles échouent. Il prend l'exemple de
l'offre gratuite d'Oracle Cloud (Always Free), suffisante pour une quinzaine
d'utilisateurs ; les scripts conviennent à toute VM Ubuntu 24.04, chez un autre hébergeur
ou sur une machine de l'école.

Compter une à deux heures la première fois, dont une bonne part dans la console Oracle.
Les libellés de la console cités ici peuvent changer d'une version à l'autre ; en cas de
doute, la version anglaise est donnée entre parenthèses.

Dans tout le guide, `nomentrace.exemple.fr` désigne le nom sous lequel l'outil sera servi,
et `IP_DE_LA_VM` l'adresse publique de la machine. Les remplacer par les vôtres.

## Ce que le guide met en place

```
Internet ──443──▶ Caddy (HTTPS, certificat Let's Encrypt)
                    │ 127.0.0.1:8000
                    ▼
                 Nomentrace (service systemd « nomentrace », utilisateur nomentrace)
                    │
                    ├── /var/lib/nomentrace/data      base du projet, base des comptes
                    └── /var/lib/nomentrace/echange   documents, exports, sauvegardes

chaque nuit : archive complète ─ chiffrée (age) ─▶ bucket Object Storage, 30 jours
```

| Emplacement | Contenu |
|---|---|
| `/opt/nomentrace` | Le code, clone du dépôt, et son environnement Python `.venv` (appartient à root) |
| `/etc/nomentrace/nomentrace.env` | Les réglages de l'instance (variables `NOMENTRACE_*`) |
| `/etc/nomentrace/sauvegarde.env` | L'adresse d'envoi des sauvegardes, lisible par root seul |
| `/etc/nomentrace/cles_sauvegarde.txt` | Les clés publiques qui chiffrent les sauvegardes |
| `/var/lib/nomentrace` | Les données, seul dossier où le service peut écrire |
| `/var/backups/nomentrace` | Les copies des bases prises avant chaque mise à jour (5 dernières) |
| `/etc/caddy/Caddyfile` | Le proxy HTTPS |

Le dossier `deploiement/` du dépôt contient tout ce qui est installé :

| Fichier | Rôle |
|---|---|
| `installer.sh` | Installation complète d'une VM neuve ; peut être relancé sans rien écraser |
| `commande.sh` | Lance une commande de Nomentrace (comptes, sauvegarde) comme le service |
| `mettre_a_jour.sh` | Mise à jour avec contrôle et retour arrière |
| `sauvegarde_distante.sh` | Sauvegarde nocturne chiffrée vers le bucket |
| `restaurer.sh` | Restauration d'une archive, chiffrée ou non |
| `systemd/` | Le service, la sauvegarde nocturne et la recherche de mises à jour |
| `Caddyfile.modele`, `*.env.exemple` | Modèles des réglages, complétés par `installer.sh` |

## 1. Ce qu'il faut avant de commencer

Un compte Oracle Cloud. L'inscription demande une carte bancaire, même pour l'offre
gratuite.

Un nom de domaine dont on peut modifier les enregistrements DNS, chez son registraire.
On y créera un sous-domaine, par exemple `nomentrace.exemple.fr`.

Une paire de clés SSH sur son poste, pour se connecter à la VM. Sous Windows, dans un
terminal PowerShell :

```
ssh-keygen -t ed25519 -f $HOME\.ssh\nomentrace
```

L'outil `age`, sur son poste, qui fabrique la clé des sauvegardes et les déchiffre. Sous
Windows : `winget install FiloSottile.age` ; sous Linux : `sudo apt install age` ; sous
macOS : `brew install age`.

## 2. Le compte Oracle : éviter la récupération et la facture

Oracle se réserve le droit d'arrêter une instance Always Free jugée inactive. Selon la
[documentation d'Oracle](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
consultée le 26 septembre 2026, une instance est inactive quand, sur sept jours, le
95e centile de l'usage du processeur, l'usage du réseau et, pour les formes A1, l'usage de
la mémoire restent tous sous 20 %. Un outil utilisé par une équipe d'une quinzaine de
personnes reste presque toujours sous ces seuils : la VM serait arrêtée.

La parade retenue est de passer le compte en paiement à l'usage (Pay As You Go). La même
documentation précise qu'Oracle ne facture pas les ressources Always Free après ce
passage, seulement ce qui les dépasse ; la politique de récupération y est présentée comme
propre aux instances Always Free, et Oracle a indiqué que le passage en paiement à l'usage
en protège. Cette documentation évolue : la relire au moment de l'installation. On ne
génère pas de charge artificielle pour tromper la mesure.

Pour être prévenu de toute facturation, créer une alerte de budget :

1. Menu › Facturation et gestion des coûts › Budgets (Billing & Cost Management ›
   Budgets) › Créer un budget.
2. Portée : le compartiment racine. Montant mensuel : 1 €.
3. Règle d'alerte : sur le coût réel, seuil de 1 €, avec son adresse mail.

Rester dans les limites gratuites, c'est ne créer que ce que ce guide décrit : une VM A1 à
1 OCPU et 6 Go de mémoire (l'offre en couvre 2 OCPU et 12 Go par mois), un volume de
démarrage d'une cinquantaine de Go (200 Go gratuits), un bucket de moins de 20 Go.

## 3. Créer la machine virtuelle

Menu › Compute › Instances › Créer une instance.

1. Nom : `nomentrace`.
2. Placement : la région d'origine du compte (les instances A1 gratuites n'existent que
   là). Si Oracle répond « Out of capacity », réessayer plus tard ou dans un autre domaine
   de disponibilité ; c'est fréquent pour les formes A1.
3. Image : Canonical Ubuntu 24.04 (pas la variante « Minimal »).
4. Forme : Ampere, `VM.Standard.A1.Flex`, 1 OCPU, 6 Go de mémoire.
5. Réseau : créer un nouveau réseau cloud virtuel (VCN) et un sous-réseau public, avec une
   adresse IPv4 publique attribuée.
6. Clés SSH : coller la clé publique `nomentrace.pub` créée à l'étape 1.
7. Volume de démarrage : la taille par défaut suffit.

Une fois l'instance active, noter son adresse IP publique. Elle ne change pas tant que
l'instance existe ; pour qu'elle survive à une instance recréée, on peut la transformer en
adresse réservée (Réseau › Adresses IP publiques réservées).

### Ouvrir les ports 80 et 443 dans le réseau Oracle

Le trafic web doit être ouvert à deux endroits : dans le réseau d'Oracle, ici, et dans le
pare-feu de la VM, ce que fera `installer.sh`.

Instance › Sous-réseau › Listes de sécurité (Security Lists) › la liste par défaut ›
Ajouter des règles entrantes :

| Source | Protocole | Port de destination |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

Le port 80 sert à Let's Encrypt pour délivrer le certificat, et à rediriger vers https.
La règle SSH (port 22) existe déjà ; on peut la restreindre à l'adresse de son domicile.

## 4. Faire pointer le nom de domaine vers la VM

Chez le registraire du domaine, dans la zone DNS, ajouter un enregistrement :

| Nom | Type | Valeur |
|---|---|---|
| `nomentrace` | A | `IP_DE_LA_VM` |

Attendre qu'il soit visible, ce qui prend de quelques minutes à une heure :

```
nslookup nomentrace.exemple.fr
```

Caddy ne peut obtenir le certificat HTTPS qu'une fois ce nom résolu vers la VM, ports 80
et 443 ouverts.

## 5. Se connecter et installer

Depuis son poste :

```
ssh -i ~/.ssh/nomentrace ubuntu@IP_DE_LA_VM
```

Sur la VM, vérifier d'abord que la connexion par mot de passe est fermée (les images
d'Oracle le font déjà) :

```
sudo sshd -T | grep -i passwordauthentication
```

La réponse doit être `passwordauthentication no`. Puis installer :

```
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/quent1-lab/NomenTrace.git /tmp/nomentrace
sudo bash /tmp/nomentrace/deploiement/installer.sh nomentrace.exemple.fr --courriel vous@exemple.fr
```

Le script :

- règle le fuseau horaire sur Europe/Paris (les horodatages du journal et les retards de
  livraison sont en heure locale) ;
- installe Python 3.14 (dépôt deadsnakes, Ubuntu 24.04 ne le fournit pas), Caddy (dépôt
  officiel), `age`, `git`, `curl` et `sqlite3` ;
- ouvre les ports 80 et 443 dans le pare-feu de la VM, avant la règle de rejet que posent
  les images d'Oracle, et enregistre les règles pour les redémarrages ;
- crée l'utilisateur système `nomentrace`, sans shell, et les dossiers de données ;
- clone le dépôt dans `/opt/nomentrace`, à la dernière version publiée (étiquette `v*`),
  ou sur `main` s'il n'y en a aucune, puis installe les dépendances ;
- écrit `/etc/nomentrace/nomentrace.env` et `/etc/caddy/Caddyfile` pour ce domaine ;
- installe et démarre le service, puis contrôle qu'il répond.

`--courriel` est facultatif : Let's Encrypt y écrit si un certificat pose problème.
`--depot URL` installe un autre dépôt, par exemple sa propre copie de Nomentrace, et
`--version v1.2` une version précise.

Ouvrir `https://nomentrace.exemple.fr` : la page de connexion doit s'afficher, avec le
cadenas du navigateur. Le premier certificat peut demander une minute.

## 6. Le premier administrateur

Sur la VM :

```
sudo bash /opt/nomentrace/deploiement/commande.sh comptes creer-admin prenom.nom@ecole.fr --nom "Prénom Nom"
```

La commande affiche un lien, valable 72 heures et utilisable une seule fois, où l'on
choisit son mot de passe. Les comptes suivants se créent dans l'outil, Paramètres ›
Utilisateurs. La même commande sert de secours si plus aucun administrateur ne peut
entrer ; voir [EXPLOITATION.md](../docs/EXPLOITATION.md).

Dans l'outil, renseigner ensuite Paramètres › Projet (nom, préfixe, budget).

## 7. La sauvegarde nocturne

Chaque nuit vers 2 h 30, le serveur construit l'archive complète : base du projet, base
des comptes, documents joints et leur corbeille. Il la chiffre, puis l'envoie dans un
bucket, c'est-à-dire un espace de stockage de fichiers d'Oracle (Object Storage), séparé
de la VM : si la machine est perdue, les sauvegardes restent. L'archive en clair ne
quitte jamais la VM et n'y reste pas.

### Le chiffrement

Le chiffrement utilise `age` avec une paire de clés. La clé publique, posée sur le
serveur, permet seulement de chiffrer. La clé privée, seule capable de relire les
sauvegardes, reste hors du serveur, chez l'administrateur. Ainsi, ni un intrus sur la VM,
ni quelqu'un qui mettrait la main sur le bucket, ne peut lire une sauvegarde, qui contient
toute la base et les empreintes des mots de passe.

Chaque instance de Nomentrace a sa propre paire de clés : rien n'en est versionné dans le
dépôt. Sur son poste :

```
age-keygen -o nomentrace-sauvegarde.key
```

La commande affiche la clé publique (`age1…`) ; le fichier contient la clé privée
(`AGE-SECRET-KEY-…`). Ranger ce fichier en deux endroits sûrs, par exemple un gestionnaire
de mots de passe et une clé USB rangée à part. Sans lui, les sauvegardes sont
illisibles : il n'existe aucun moyen de les récupérer. On peut autoriser plusieurs
personnes, chacune avec sa paire de clés : une clé publique par ligne, et n'importe
laquelle des clés privées relit l'archive.

Pour protéger le fichier de la clé privée par une phrase de passe, le chiffrer lui-même :
`age --passphrase -o nomentrace-sauvegarde.key.age nomentrace-sauvegarde.key`, puis
supprimer l'original. Il faudra alors le déchiffrer avant chaque restauration.

### Le bucket

Menu › Stockage › Buckets (Storage › Buckets) › Créer un bucket.

1. Nom : `nomentrace-sauvegardes`. Niveau de stockage : Standard. Il est privé par défaut :
   le laisser ainsi.
2. Dans le bucket, Règles de conservation (Retention Rules) › Créer une règle : durée
   limitée, 30 jours, non verrouillée. Pendant 30 jours, une sauvegarde ne peut être ni
   écrasée ni supprimée, même par quelqu'un qui aurait volé l'adresse d'envoi.
3. Politiques de cycle de vie (Lifecycle Policy Rules) › Créer une règle : action
   « Supprimer », 31 jours. Les sauvegardes plus anciennes disparaissent d'elles-mêmes.

Le cycle de vie exige qu'Oracle ait le droit d'agir sur le bucket. Menu › Identité et
sécurité › Stratégies (Policies) › Créer une stratégie, dans le compartiment racine, avec
cette instruction (remplacer `eu-paris-1` par l'identifiant de sa région, visible dans
l'adresse de la console) :

```
Allow service objectstorage-eu-paris-1 to manage object-family in tenancy
```

Enfin, l'adresse d'envoi. Dans le bucket, Demandes pré-authentifiées (Pre-Authenticated
Requests) › Créer :

1. Cible : le bucket.
2. Type d'accès : autoriser les écritures d'objet seulement (Permit object writes), sans
   lecture ni listage.
3. Expiration : une date lointaine, un an par exemple. Noter dans son agenda de la
   renouveler avant.

Oracle affiche alors une adresse qui finit par `/o/`, une seule fois : la copier. Elle
permet d'écrire dans le bucket et rien d'autre.

### Sur la VM

```
sudo nano /etc/nomentrace/sauvegarde.env        # coller l'adresse après NOMENTRACE_SAUVEGARDE_URL=
sudo nano /etc/nomentrace/cles_sauvegarde.txt   # coller la ou les clés publiques age1…
sudo systemctl enable --now nomentrace-sauvegarde.timer
```

Lancer une première sauvegarde tout de suite pour vérifier :

```
sudo systemctl start nomentrace-sauvegarde
journalctl -u nomentrace-sauvegarde -n 20
```

Le journal doit finir par « Sauvegarde envoyée : nomentrace_principal_…zip.age », et le
fichier apparaître dans le bucket. `systemctl list-timers nomentrace-sauvegarde` donne la
date de la prochaine.

L'offre gratuite couvre 20 Go dans Object Storage. Avec 31 archives gardées, la taille
d'une archive, qui suit surtout celle des documents joints, doit rester sous 600 Mo
environ. La taille de chaque envoi est dans le journal.

Une sauvegarde qui échoue ne prévient personne : l'outil n'envoie aucun courriel. Jeter un
œil au bucket de temps en temps, ou à `systemctl status nomentrace-sauvegarde`.

## 8. Restaurer une sauvegarde

Faire l'exercice une fois, avant d'en avoir besoin, pour vérifier que la clé privée relit
bien les archives.

1. Dans la console Oracle, bucket › l'archive voulue › Télécharger.
2. La copier sur la VM, avec la clé privée :

   ```
   scp -i ~/.ssh/nomentrace nomentrace_principal_AAAAMMJJ_HHMMSS.zip.age nomentrace-sauvegarde.key ubuntu@IP_DE_LA_VM:
   ```

3. Sur la VM, restaurer puis effacer la clé privée :

   ```
   sudo bash /opt/nomentrace/deploiement/restaurer.sh nomentrace_principal_AAAAMMJJ_HHMMSS.zip.age --cle nomentrace-sauvegarde.key
   shred -u nomentrace-sauvegarde.key
   ```

Pour ne jamais poser la clé privée sur le serveur, déchiffrer plutôt sur son poste
(`age -d -i nomentrace-sauvegarde.key -o archive.zip ARCHIVE.zip.age`), copier
`archive.zip` sur la VM et le passer à `restaurer.sh` sans `--cle`.

Le script arrête le service, vérifie l'archive (une base endommagée, venue d'une version
plus récente ou un chemin suspect sont refusés avant toute modification), sauvegarde les
deux bases en place, remplace les bases et le dossier des documents, puis redémarre. Les
documents remplacés ne sont pas effacés : ils sont mis de côté dans
`/var/lib/nomentrace/echange/documents_avant_restauration_…`. Avec `--sans-documents`,
seules les bases sont remplacées. Une archive venue d'une version plus ancienne reçoit
les mises à jour de schéma au redémarrage.

L'archive téléchargée depuis l'interface (Paramètres › Export et sauvegardes) se restaure
de la même façon ; elle ne contient pas la base des comptes, qui est alors gardée telle
quelle.

## 9. Mettre à jour

### Publier une version

Le serveur installe des versions publiées, c'est-à-dire des étiquettes git `v…`, plutôt
que l'état courant de `main`, où un travail peut être en cours. Une mise à jour de schéma
ne se défait pas : on ne publie qu'une version vérifiée.

À chaque envoi sur GitHub, l'intégration continue (`.github/workflows/tests.yml`) lance
le lint, les tests et la vérification des scripts de ce dossier. Quand elle est au vert
sur le commit voulu, on le publie depuis son poste :

```
git tag v1.1
git push origin v1.1
```

### Mise à jour à la main

```
sudo bash /opt/nomentrace/deploiement/mettre_a_jour.sh          # dernière version publiée
sudo bash /opt/nomentrace/deploiement/mettre_a_jour.sh v1.1     # version précise
sudo bash /opt/nomentrace/deploiement/mettre_a_jour.sh main     # tête de main, pour un essai
```

Le script arrête le service quelques secondes, copie les deux bases dans
`/var/backups/nomentrace/`, installe la version et ses dépendances, redémarre, et attend
jusqu'à une minute que `/api/sante` réponde. Si elle ne répond pas, il revient au code
précédent, remet les bases copiées, puisque la nouvelle version a pu les migrer, et
redémarre ; le journal du service est affiché pour comprendre l'échec. Les cinq dernières
copies sont gardées.

### Mise à jour automatique

```
sudo systemctl enable --now nomentrace-maj.timer
```

Toutes les quinze minutes, le serveur regarde s'il existe une étiquette `v*` plus récente
que la version installée, et s'y met à jour avec le même contrôle. Publier une étiquette
suffit alors à déployer. La minuterie ne fait qu'avancer : une version posée à la main
n'est jamais défaite par elle. Son journal : `journalctl -u nomentrace-maj`.

Le serveur tire les versions du dépôt ; GitHub n'a aucun accès à la VM, et aucune clé du
serveur n'est confiée à GitHub.

### Revenir en arrière plus tard

Le retour automatique couvre la version qui ne démarre pas. Une régression découverte des
jours après se corrige plutôt par une nouvelle version. Une version antérieure refuse de
démarrer sur une base déjà migrée par une plus récente ; y revenir impose de restaurer une
sauvegarde prise avant la mise à jour, et de perdre ce qui a été saisi depuis.

## 10. Au quotidien

| Pour | Commande |
|---|---|
| État du service | `systemctl status nomentrace` |
| Journal de l'application | `journalctl -u nomentrace -f` |
| Journal d'accès de Caddy | `sudo tail -f /var/log/caddy/nomentrace.log` |
| Redémarrer | `sudo systemctl restart nomentrace` |
| Minuteries | `systemctl list-timers 'nomentrace*'` |
| Place disque | `df -h /` |

Ubuntu installe seul ses mises à jour de sécurité (unattended-upgrades). Quand
`/var/run/reboot-required` existe, redémarrer la VM à une heure creuse avec
`sudo reboot` : tout repart seul. Caddy renouvelle seul le certificat.

Un réglage de `/etc/nomentrace/nomentrace.env`, comme la limite de connexions simultanées
`NOMENTRACE_CONCURRENCE`, se prend en compte par `sudo systemctl restart nomentrace`. Les
autres variables sont décrites dans [EXPLOITATION.md](../docs/EXPLOITATION.md).

## 11. En cas de problème

Le navigateur n'obtient aucune réponse : vérifier les règles entrantes 80 et 443 dans la
liste de sécurité d'Oracle, puis dans la VM avec `sudo iptables -L INPUT -n --line-numbers`
(les règles ACCEPT des ports 80 et 443 doivent précéder le REJECT).

Erreur de certificat : le nom ne pointe pas encore vers la VM, ou le port 80 est fermé.
`journalctl -u caddy -n 50` dit pourquoi ; Caddy réessaie seul.

Réponse « 502 » : Caddy répond mais Nomentrace est arrêté. `systemctl status nomentrace`
et `journalctl -u nomentrace -n 50`.

Le service ne démarre pas après une restauration manuelle de fichiers : vérifier qu'ils
appartiennent à l'utilisateur `nomentrace`
(`sudo chown -R nomentrace:nomentrace /var/lib/nomentrace`).

## Sécurité

Seul Caddy est exposé ; Nomentrace n'écoute que sur 127.0.0.1 et ne croit l'adresse du
visiteur et le schéma (https) transmis dans les en-têtes `X-Forwarded-*` que s'ils
viennent de là. Caddy limite la taille d'une requête à 100 Mo. Le service tourne sous un
utilisateur sans droits, ne peut écrire que dans ses données, et la VM n'accepte SSH que
par clé. Les protections de l'application elle-même, et ce qui reste à faire, sont dans
[SECURITE.md](../docs/SECURITE.md).
