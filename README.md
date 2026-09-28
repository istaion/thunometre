# thunometre

Site ultraléger pour situer son « thunomètre » (score de capacités financières et
score de privilège, entiers éventuellement négatifs) sur un nuage de points, par
rapport aux autres personnes.

- **Admin** (`/admin`, protégé par identifiant et mot de passe) : saisit un nom
  libre (mail, prénom, numéro + date…), ce qui crée un lien personnel `/p/<uuid>`
  à envoyer. Voit le nuage avec le nom de chaque point au survol, et la liste des
  personnes (copier le lien, supprimer).
- **Client** (`/p/<uuid>`) : saisit ou modifie ses deux scores, et voit le nuage
  avec son point en couleur. Les autres points sont anonymes. Deux calculateurs
  (privilège, capacités financières) aident à obtenir les scores ; ils tournent
  entièrement dans le navigateur (`static/calc.js`, qui contient aussi les règles
  de calcul) : les réponses ne sont ni envoyées ni stockées.

Aucune dépendance : Python 3 (bibliothèque standard) + SQLite. Une seule table
`points (uuid, name, privilege, income)`.

## Lancer

```sh
ADMIN_USER='marine' ADMIN_PASSWORD='un-mot-de-passe' python3 server.py
```

Options : `PORT` (8000), `HOST` (127.0.0.1), `DB_PATH` (`thunometre.db`).

L'admin se connecte sur `/admin` avec cet identifiant et ce mot de passe.

## Déploiement sur Render

Le fichier `render.yaml` décrit le service (Blueprint). Dans Render :
**New → Blueprint**, choisir le dépôt, puis renseigner `ADMIN_USER` et
`ADMIN_PASSWORD` (mot de passe long et aléatoire).

- Plan **Starter** obligatoire : la base SQLite vit sur un disque persistant
  (`/var/data`), indisponible sur le plan gratuit, dont le disque est effacé à
  chaque redémarrage.
- Render fournit le HTTPS, indispensable ici (authentification HTTP Basic, liens
  clients qui valent mot de passe).

## Autre hébergement

Mettre le serveur derrière un reverse proxy HTTPS (Caddy, nginx). Exemple Caddy :

```
thunometre.example.org {
  reverse_proxy 127.0.0.1:8000
}
```
