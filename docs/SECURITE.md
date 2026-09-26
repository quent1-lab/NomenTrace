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

Le verrouillage d'un compte peut servir à nuire. Cinq mauvais mots de passe bloquent un
compte quinze minutes, y compris pour son titulaire muni du bon mot de passe ; il suffit de
connaître une adresse pour bloquer quelqu'un à répétition. C'est le prix d'une protection
simple contre la force brute. Compter les échecs par couple compte et adresse IP, avec une
limite plus large par compte seul, l'adoucirait.

L'adresse IP d'un visiteur est lue dans l'en-tête `X-Forwarded-For` quand la requête vient
d'un proxy de confiance, ce qu'Uvicorn accorde par défaut à `127.0.0.1`. Derrière Caddy,
c'est juste à deux conditions : Caddy réécrit cet en-tête au lieu de relayer celui du
visiteur, et Uvicorn ne fait confiance qu'à Caddy. Sinon la limite par adresse et l'adresse
enregistrée dans les sessions se falsifient. Cette limite reste de toute façon secondaire :
derrière le réseau d'une école, tout le monde sort par la même adresse.

Sous Windows, un fichier statique se lit aussi sous un nom détourné (`/js/api.js::$DATA`,
flux de données NTFS). Seuls des fichiers déjà publics sont concernés et le phénomène
n'existe pas sous Linux, où tournera le serveur.

Le contrôle d'origine compare l'hôte et le port, pas le schéma : une page `https` et une
page `http` du même hôte et du même port sont traitées pareil. Sans effet pratique, puisque
les deux ne partagent jamais un port ; à resserrer quand l'outil ne sera plus servi qu'en
HTTPS.

## Ce que l'hébergement devra apporter

L'outil ne chiffre pas lui-même les échanges : exposé au-delà du poste, il doit être servi
en HTTPS. Le proxy devra limiter la taille des requêtes et le débit sur `/api/session`,
Uvicorn tourner avec `--limit-concurrency` et ne faire confiance qu'au proxy pour l'adresse
des visiteurs. La base des comptes, absente de l'archive complète, devra être sauvegardée à
part et protégée comme elle.

## Signaler une faille

Le dépôt est public : une faille se signale par un message privé à son propriétaire plutôt
que par un ticket, le temps de la corriger.
