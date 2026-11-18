# Héberger l'API sur Oracle Cloud (Always Free)

L'API tourne aujourd'hui sur Render gratuit : un dixième de processeur, 512 Mo, mise en veille après 15 minutes. Ce
guide la déplace sur une VM ARM Oracle Cloud toujours allumée (4 processeurs, 24 Go), avec Caddy pour le HTTPS, un
Redis local à la place d'Upstash et un **worker Celery** (avec son planificateur `beat`) qui exécute les tâches
planifiées, dont le calcul par lots des prévisions (Prophet compris). La base reste sur Supabase, le frontend sur
Vercel. Pourquoi : `docs/ADR.md`, ADR-014.

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
- Shape : **Ampere VM.Standard.A1.Flex**, 4 OCPU, 24 Go (tout le quota Always Free : le calcul ML en profite).
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

Le worker démarre après l'API (qui applique les migrations) :

```bash
cd ~/InvestAI/deploy/oracle
docker compose logs --tail 30 worker
docker compose exec worker celery -A app.tasks.celery_app inspect registered
```

Le premier calcul par lots des prévisions a lieu à 02 h 45 UTC ; pour ne pas attendre :

```bash
docker compose exec worker celery -A app.tasks.celery_app call app.domains.predictions.tasks.run_daily_predictions
docker compose logs -f worker
```

## 8. Déploiement automatique

À chaque CI verte sur `main`, `.github/workflows/deploy-oracle.yml` se connecte en SSH et lance `deploy.sh` avec
le commit dont la CI vient de passer, pas la tête de `main` : un merge plus récent peut avoir sa CI encore en cours.
`deploy.sh` refuse un commit absent de `main` et ignore un commit plus ancien que celui en place (une CI qui finit
en retard ne fait pas revenir en arrière). Lancé à la main sans argument, il prend la dernière version de `main`.

Clé dédiée au déploiement, sur ton PC, autorisée sur la VM à lancer **uniquement** `deploy.sh` : si le secret
GitHub fuitait, il ne donnerait pas de shell.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle_deploy -N "" -C github-deploy
echo "command=\"bash /home/ubuntu/InvestAI/deploy/oracle/deploy.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat ~/.ssh/oracle_deploy.pub)" \
  | ssh -i ~/.ssh/oracle_investai ubuntu@<IP> 'cat >> ~/.ssh/authorized_keys'
ssh-keyscan -t ed25519 <IP>
```

Copier la clé privée pour le secret sans l'afficher, depuis WSL : `clip.exe < ~/.ssh/oracle_deploy`. Passer par
PowerShell ajoute des fins de ligne Windows qui rendent la clé illisible.

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
`VITE_WS_URL` vers `https://api.<ton-domaine>`. Dans GitHub, *Settings → Secrets and variables → Actions →
Variables*, créer `API_BASE_URL` = `https://api.<ton-domaine>` : les workflows *Scheduled Tasks* et *Invariants
Watchdog* appelleront la VM au lieu de Render. Garder Render quelques jours en secours, puis le suspendre
(*Render → investai-api → Settings → Suspend*). Upstash n'est plus utilisé par InvestAI.

Tant que Render est éveillé, son planificateur interne exécute les mêmes tâches que le worker, sur la même base. Les
instantanés quotidiens le supportent (un par jour), mais deux synchronisations d'exchange lancées au même instant
peuvent chacune écrire leur transaction d'ajustement. Basculer `vercel.json` et `API_BASE_URL` le même jour : sans
trafic, Render s'endort au bout de 15 minutes et son planificateur s'arrête avec lui.

Si le réseau inspecte le TLS (pare-feu d'entreprise), un domaine tout juste créé peut être servi avec le certificat
du pare-feu tant qu'il n'est pas catégorisé : vérifier `/health/ready` depuis la VM
(`curl https://<domaine>/health/ready`) avant de conclure à une panne.

## Exploitation

```bash
cd ~/InvestAI/deploy/oracle
docker compose ps
docker compose logs -f api
docker compose restart api
```
