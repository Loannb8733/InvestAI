# Déploiement InvestAI sur Railway

## Prérequis
- Compte Railway (https://railway.app)
- Railway CLI installé (`npm install -g @railway/cli`)

## Étapes de déploiement

### 1. Connexion Railway
```bash
railway login
```

### 2. Créer un nouveau projet
```bash
railway init
```
Choisissez "Empty Project"

### 3. Ajouter PostgreSQL
Dans le dashboard Railway :
1. Cliquez sur "+ New"
2. Sélectionnez "Database" → "PostgreSQL"
3. Notez les variables de connexion

### 4. Ajouter Redis
1. Cliquez sur "+ New"
2. Sélectionnez "Database" → "Redis"
3. Notez les variables de connexion

### 5. Déployer le Backend
```bash
cd backend
railway link
railway up
```

### 6. Configurer les variables d'environnement
Dans Railway Dashboard → Backend Service → Variables :

```
APP_ENV=production
DEBUG=false
SECRET_KEY=<générer avec: openssl rand -hex 32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Base de données (auto-rempli par Railway)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (auto-rempli par Railway)
REDIS_URL=${{Redis.REDIS_URL}}

# Email SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=loann.bourdier@gmail.com
SMTP_PASSWORD=<votre app password>
SMTP_FROM_EMAIL=loann.bourdier@gmail.com
SMTP_FROM_NAME=InvestAI
SMTP_TLS=true

# Encryption
FERNET_KEY=<générer avec: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# External APIs
FINNHUB_API_KEY=<votre clé>
```

### 7. Déployer le Worker Celery
Créez un nouveau service dans Railway :
1. "+ New" → "GitHub Repo" → sélectionnez le même repo
2. Settings → Root Directory: `backend`
3. Settings → Start Command: `celery -A app.tasks.celery_app worker --loglevel=info`

### 8. Déployer Celery Beat
Même processus avec la commande :
`celery -A app.tasks.celery_app beat --loglevel=info`

### 9. Configurer le Frontend Vercel
Dans Vercel Dashboard → Settings → Environment Variables :
```
VITE_API_URL=https://votre-backend.railway.app/api/v1
```

Redéployez le frontend :
```bash
cd frontend
vercel --prod
```

## URLs finales
- Frontend: https://frontend-ivory-rho-55.vercel.app
- Backend: https://votre-projet.railway.app
- API Docs: https://votre-projet.railway.app/docs

## Vérification
```bash
curl https://votre-projet.railway.app/health
```
