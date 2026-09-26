# Sécurité

Ce document dit comment Nomentrace se protège, ce qu'un audit a vérifié, et ce qui reste à
régler. Les réglages d'une instance sont dans [EXPLOITATION.md](EXPLOITATION.md), les
droits de chaque rôle dans [UTILISATION.md](UTILISATION.md) et le fonctionnement du code
dans [ARCHITECTURE.md](ARCHITECTURE.md).

## Ce que l'outil protège, et comment

Deux choses comptent : que personne ne lise ni ne modifie les données sans en avoir le
droit, et que l'outil reste disponible pour l'équipe.

La confidentialité et l'intégrité reposent sur les comptes. En mode connecté, chaque
requête est rattachée à une session gardée en base, et la règle de la route demandée est
vérifiée par le serveur (table `REGLES` de `backend/services/droits.py`) ; une route
oubliée dans cette table est réservée à l'administrateur. Les mots de passe sont hachés par
scrypt aux paramètres de l'OWASP, les jetons de session et d'invitation ne sont gardés que
par leur empreinte. Toute écriture doit venir d'une page de l'outil (contrôle de l'en-tête
`Origin`). La politique de sécurité du contenu interdit tout script qui ne vient pas de
l'outil. Le SQL passe par des paramètres liés, et les rares noms de colonne insérés dans
une requête sont d'abord comparés à une liste écrite dans le code.

Le mode local, sans compte, n'accepte que les requêtes émises depuis le poste et adressées
à `127.0.0.1` ou `localhost`.

## Exigences du mot de passe

Le mot de passe se choisit par le lien d'invitation. Il doit compter 12 caractères au
moins et mêler minuscule, majuscule, chiffre et caractère spécial ; une phrase de 20
caractères ou plus en est dispensée, parce que sa longueur la protège mieux qu'un mélange
de symboles. Il ne doit reprendre ni le nom ni le début de l'adresse mail, compter au moins
six caractères différents, et ne pas être un mot de passe courant à peine décoré
(« Motdepasse2026! » est refusé). La page coche ces règles pendant la saisie ; c'est le
serveur qui décide (`exigences_mot_de_passe` dans `backend/services/authentification.py`).

## Audit du 25 septembre 2026

L'audit a combiné une relecture du code et des attaques réelles contre une instance en
mode connecté, peuplée du jeu d'essai, avec un compte de chaque rôle, un compte désactivé
et un compte rattaché à un autre projet.

Ce qui a tenu. Aucune route non publique ne répond sans session. Les cookies forgés (vide,
aléatoire, injection SQL, très long) sont refusés. Les injections SQL par le tri, les
filtres d'attribut, la recherche et l'historique sont rejetées, et la base reste intacte.
Un contributeur ne touche pas aux composants d'un autre bloc, même en passant par le
reclassement, la création ou les affectations. Un contributeur « achats » ne valide pas un
fournisseur, un contributeur « ensembles » ne fixe pas de budget. Le dernier
administrateur ne peut pas se rétrograder. Un administrateur ne gère pas les comptes d'un
autre projet. Un lien d'invitation ne sert qu'une fois. Une écriture venue d'une autre
origine est refusée. Les tentatives de traversée de répertoire sur les fichiers statiques
échouent. Le temps de réponse d'une connexion ne dit pas si le compte existe.

Une faille critique a été trouvée et corrigée. Toutes les routes s'exécutent dans un pool
de quarante fils, et chaque connexion y calcule un scrypt volontairement lent. Le compteur
d'échecs n'étant incrémenté qu'après ce calcul, une rafale de connexions, même sans compte,
passait le contrôle, occupait tous les fils et gelait le reste de l'application. Avec 240
connexions simultanées, une simple requête attendait près de cinquante secondes, et l'outil
restait inutilisable trois minutes. N'importe qui pouvant joindre le serveur pouvait donc
le rendre indisponible pour toute l'équipe. Désormais, au-delà de six connexions ou
invitations traitées en même temps, la requête suivante est refusée aussitôt (503), sans
occuper de fil. Refait après correctif, le même essai laisse l'outil répondre en une
seconde.

## Points restants

Le verrouillage d'un compte pouvait servir à nuire : cinq mauvais mots de passe, tapés par
n'importe qui, bloquaient le titulaire lui-même. Il est corrigé depuis l'audit. Les cinq
échecs sont comptés par couple compte et adresse IP, si bien qu'un tiers ne bloque que sa
propre adresse ; une limite de cinquante échecs par compte, toutes adresses confondues,
arrête une attaque répartie. Reste un cas : un tiers qui partage l'adresse du titulaire,
comme deux élèves derrière le réseau de l'école, peut encore le bloquer quinze minutes.

Sous Windows, un fichier statique se lit aussi sous un nom détourné (`/js/api.js::$DATA`,
flux de données NTFS). Seuls des fichiers déjà publics sont concernés et le phénomène
n'existe pas sous Linux, où tournera le serveur.

Caddy, tel qu'il est distribué, ne sait pas limiter le débit des requêtes : il faudrait
une version recompilée avec un module tiers. La connexion n'a donc pas de limite de débit
au niveau du proxy. Elle reste protégée par l'application : six traitements simultanés au
plus, verrouillages par compte et par adresse.

Une sauvegarde nocturne qui échoue ne prévient personne, et l'adresse d'envoi vers le
bucket expire à la date choisie à sa création : à surveiller, comme l'indique le guide de
déploiement.

## L'hébergement

Le dossier `deploiement/` sert l'outil derrière Caddy, qui chiffre les échanges en HTTPS
avec un certificat Let's Encrypt et redirige http vers https. Nomentrace n'écoute que sur
`127.0.0.1` ; seul Caddy est exposé, et le pare-feu de la machine n'ouvre que les ports 22,
80 et 443. SSH n'accepte que les clés.

L'adresse IP d'un visiteur, dont dépendent la limite par adresse et l'adresse enregistrée
dans les sessions, est lue dans l'en-tête `X-Forwarded-For`. En mode connecté, Uvicorn ne
croit cet en-tête, et `X-Forwarded-Proto`, que s'ils viennent de `127.0.0.1`, donc de
Caddy, qui remplace celui qu'envoie le visiteur par sa vraie adresse. En mode local, ces
en-têtes sont ignorés. La limite par adresse reste secondaire : derrière le réseau d'une
école, tout le monde sort par la même adresse.

Le contrôle d'origine compare désormais le schéma en plus de l'hôte et du port : une page
servie en `http` ne peut pas écrire sur l'instance servie en `https`. Uvicorn refuse
aussitôt (503) les connexions au-delà de `NOMENTRACE_CONCURRENCE`, cent par défaut, et
Caddy les requêtes de plus de 100 Mo (413), sans rien transmettre.

Le service tourne sous un utilisateur système sans shell et, par les protections de
systemd, ne peut écrire que dans ses données ; le code appartient à root. Chaque nuit,
l'archive complète, base des comptes comprise, est chiffrée par `age` pour une clé publique
avant de quitter la machine ; la clé privée n'est jamais sur le serveur. L'adresse d'envoi
vers le bucket ne permet que d'écrire, et une règle de conservation interdit d'écraser ou
de supprimer une sauvegarde pendant trente jours : un intrus sur la machine ne peut ni lire
ni détruire les sauvegardes déjà envoyées.

Une mise à jour ratée revient d'elle-même à la version précédente, bases comprises. Une
version antérieure refuse de démarrer sur une base migrée par une version plus récente.

## Signaler une faille

Le dépôt est public : une faille se signale par un message privé à son propriétaire plutôt
que par un ticket, le temps de la corriger.
