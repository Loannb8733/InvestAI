# Héberger l'API sur Oracle Cloud (Always Free)

L'API tourne aujourd'hui sur Render gratuit : un dixième de processeur, mise en veille après 15 minutes. Ce guide la
déplace sur une VM ARM Oracle Cloud toujours allumée (2 processeurs, 12 Go), avec Caddy pour le HTTPS et un Redis
local à la place d'Upstash. La base reste sur Supabase, le frontend sur Vercel.

Fichiers : `deploy/oracle/` (`docker-compose.yml`, `Caddyfile`, `.env.example`, `setup-vm.sh`, `deploy.sh`) et
`.github/workflows/deploy-oracle.yml`.

## 1. Compte Oracle Cloud

1. S'inscrire sur https://www.oracle.com/cloud/free/ (carte bancaire demandée pour vérification).
2. **Région d'origine : Germany Central (Frankfurt).** Elle ne peut plus être changée ensuite, et Supabase est à
   Francfort.
3. Recommandé : *Billing → Upgrade and Manage Payment* pour passer en paiement à l'usage. Les ressources Always Free
   restent gratuites, et une instance gratuite jugée inactive (moins de 20 % d'utilisation sur 7 jours) n'est plus
   récupérée. Créer un budget avec alerte à 1 € (*Billing → Budgets*) pour être prévenu de toute dépense.

## 2. Clé SSH dédiée

Sur ton PC (WSL) :

```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle_investai -C investai-oracle
```

## 3. La VM

*Compute → Instances → Create instance* :

- Image : **Canonical Ubuntu 24.04**.
- Shape : **Ampere VM.Standard.A1.Flex**, 2 OCPU, 12 Go.
- Réseau : sous-réseau public, adresse IPv4 publique attribuée.
- SSH : coller le contenu de `~/.ssh/oracle_investai.pub`.

« Out of capacity » : réessayer plus tard ou changer de domaine de disponibilité (AD-1, AD-2, AD-3).

## 4. Ouvrir les ports

*Networking → Virtual Cloud Networks → (le VCN) → Security Lists → Default → Add Ingress Rules* :

| Source | Protocole | Port |
|---|---|---|
| 0.0.0.0/0 | TCP | 80 |
| 0.0.0.0/0 | TCP | 443 |
| 0.0.0.0/0 | UDP | 443 |

Le pare-feu interne de la VM est ouvert par `setup-vm.sh`.

## 5. Nom de domaine

Créer un enregistrement DNS **A** `api.<ton-domaine>` vers l'IP publique de la VM (sans domaine : un nom gratuit
DuckDNS). Caddy obtient le certificat HTTPS tout seul au premier démarrage.

## 6. Installer

```bash
ssh -i ~/.ssh/oracle_investai ubuntu@<IP>
git clone https://github.com/Loannb8733/InvestAI.git
bash InvestAI/deploy/oracle/setup-vm.sh
exit
```

Se reconnecter (le groupe docker est pris en compte), puis remplir le fichier d'environnement :

```bash
nano ~/InvestAI/deploy/oracle/.env
```

- `API_DOMAIN` : le domaine de l'étape 5.
- **`SECRET_KEY` et `FERNET_KEY` : exactement les valeurs de Render** (onglet Environment). Une autre `FERNET_KEY`
  rendrait illisibles les clés d'API d'exchanges chiffrées en base ; une autre `SECRET_KEY` déconnecterait tout le
  monde.
- `DATABASE_URL` et les autres valeurs : celles de Render.
- Ne pas mettre `REDIS_URL` : `docker-compose.yml` pointe l'API vers le Redis local.

## 7. Démarrer

```bash
bash ~/InvestAI/deploy/oracle/deploy.sh
curl https://api.<ton-domaine>/health/ready
```

`/health/ready` doit répondre `"database":"ok"` et `"redis":"ok"`. Le premier build prend une dizaine de minutes.

## 8. Déploiement automatique

À chaque CI verte sur `main`, `.github/workflows/deploy-oracle.yml` se connecte en SSH et lance `deploy.sh`. Clé
dédiée au déploiement, sur ton PC :

```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle_deploy -N "" -C github-deploy
ssh-copy-id -i ~/.ssh/oracle_deploy.pub -o "IdentityFile ~/.ssh/oracle_investai" ubuntu@<IP>
ssh-keyscan -t ed25519 <IP>
```

Dans GitHub, *Settings → Secrets and variables → Actions*, créer :

| Secret | Valeur |
|---|---|
| `ORACLE_HOST` | l'IP de la VM |
| `ORACLE_USER` | `ubuntu` |
| `ORACLE_SSH_KEY` | le contenu de `~/.ssh/oracle_deploy` (clé privée) |
| `ORACLE_KNOWN_HOSTS` | la ligne rendue par `ssh-keyscan` |

Tant que `ORACLE_HOST` n'existe pas, le workflow ne fait rien.

## 9. Basculer le frontend

Une fois `/health/ready` correct, changer dans `vercel.json` la destination des réécritures `/api/v1/:path*` et
`VITE_WS_URL` vers `https://api.<ton-domaine>`. Garder Render quelques jours en secours, puis le suspendre
(*Render → investai-api → Settings → Suspend*). Upstash n'est plus utilisé par InvestAI.

## Exploitation

```bash
cd ~/InvestAI/deploy/oracle
docker compose ps
docker compose logs -f api
docker compose restart api
```
