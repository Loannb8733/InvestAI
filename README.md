# InvestAI

Plateforme multi-utilisateurs de gestion et d'analyse d'investissements (crypto, immobilier, actions, ETF).

## Stack Technique

- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy / PostgreSQL + TimescaleDB
- **Frontend**: React 18 / TypeScript / Tailwind CSS / Zustand
- **Infrastructure**: Docker / Redis / Celery / Nginx

## Démarrage Rapide

### Prérequis

- Docker et Docker Compose
- Git

### Installation

1. Cloner le repository :
```bash
git clone <repository-url>
cd InvestAI
```

2. Copier le fichier d'environnement :
```bash
cp .env.example .env
```

3. Configurer les variables d'environnement dans `.env` :
```bash
# Générer une clé secrète
python -c "import secrets; print(secrets.token_hex(32))"

# Générer une clé Fernet
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

4. Lancer les services :
```bash
docker-compose up -d
```

5. Créer un utilisateur admin :
```bash
docker-compose exec backend python scripts/create_admin.py
```

6. Accéder à l'application :
- Frontend: http://localhost:3000
- API: http://localhost:8000/api/v1/docs

## Développement

### Backend (sans Docker)

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Lancer le serveur
uvicorn app.main:app --reload --port 8000

# Tests
pytest
```

### Frontend (sans Docker)

```bash
cd frontend
npm install
npm run dev
```

## Architecture

```
InvestAI/
├── backend/           # API FastAPI
│   ├── app/
│   │   ├── api/       # Routes
│   │   ├── core/      # Config, sécurité
│   │   ├── models/    # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # Logique métier
│   │   ├── tasks/     # Celery tasks
│   │   └── ml/        # Modèles IA
│   └── tests/
├── frontend/          # React app
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── stores/
│       └── services/
├── docker/            # Config Docker
└── scripts/           # Scripts utilitaires
```

## Fonctionnalités

- **Authentification** : JWT + MFA (TOTP)
- **Gestion des actifs** : Crypto, Actions, ETF, Immobilier
- **Dashboard** : Vue globale du patrimoine
- **Analyses** : Métriques, corrélations, diversification
- **IA/ML** : Prédictions, détection d'anomalies
- **Alertes** : Notifications prix/performance
- **Rapports** : PDF, Excel, fiscalité

## Licence

Projet privé - Tous droits réservés
