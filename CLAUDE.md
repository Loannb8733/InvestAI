# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

**InvestAI** - Plateforme multi-utilisateurs de gestion et d'analyse d'investissements (crypto, immobilier, actions, ETF).

## Stack Technique

### Backend
- **Framework**: Python 3.11+ / FastAPI
- **Base de données**: PostgreSQL + TimescaleDB (séries temporelles)
- **ORM**: SQLAlchemy 2.0
- **Auth**: JWT (15min) + refresh tokens, MFA (TOTP)
- **Cryptage**: Fernet (clés API), bcrypt cost 12+ (mots de passe)
- **Task Queue**: Celery + Redis
- **ML/IA**: scikit-learn, Prophet, TensorFlow, pandas, numpy

### Frontend
- **Framework**: React 18+ / TypeScript
- **State**: Zustand
- **UI**: Tailwind CSS + shadcn/ui
- **Charts**: Recharts
- **Tables**: TanStack Table
- **Forms**: React Hook Form + Zod

### Infrastructure
- Docker + Docker Compose
- Nginx (reverse proxy)
- Let's Encrypt (HTTPS)

## Structure du Projet

```
InvestAI/
├── backend/
│   ├── app/
│   │   ├── api/           # Routes FastAPI
│   │   ├── core/          # Config, sécurité, auth
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Logique métier
│   │   ├── tasks/         # Celery tasks
│   │   └── ml/            # Modèles IA/ML
│   ├── tests/
│   ├── alembic/           # Migrations BDD
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # Composants React
│   │   ├── pages/         # Pages principales
│   │   ├── hooks/         # Custom hooks
│   │   ├── stores/        # Zustand stores
│   │   ├── services/      # API calls
│   │   ├── types/         # TypeScript types
│   │   └── utils/         # Utilitaires
│   └── package.json
├── docker/
│   ├── backend/
│   ├── frontend/
│   └── nginx/
├── scripts/               # Scripts utilitaires
├── docker-compose.yml
└── .env.example
```

## Commandes de Développement

### Docker
```bash
# Démarrer tous les services
docker-compose up -d

# Logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Rebuild
docker-compose up -d --build

# Arrêter
docker-compose down
```

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
pytest -v tests/test_auth.py  # Test spécifique
pytest --cov=app              # Avec coverage

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend (sans Docker)
```bash
cd frontend
npm install

# Dev server
npm run dev

# Build
npm run build

# Tests
npm test
npm run test:coverage

# Lint
npm run lint
npm run lint:fix
```

## Base de Données

### Tables Principales
- `users` - Utilisateurs (admin/user roles)
- `portfolios` - Portefeuilles par utilisateur
- `assets` - Actifs (crypto, immo, actions, ETF)
- `transactions` - Historique des transactions
- `api_keys` - Clés API exchanges (cryptées Fernet)
- `alerts` - Alertes de prix/performance
- `predictions` - Prédictions IA
- `notes` - Journal d'investissement
- `calendar_events` - Calendrier financier

### Conventions
- Timestamps: `created_at`, `updated_at` (UTC)
- Soft delete: `deleted_at` nullable
- UUID pour les IDs exposés en API
- Montants financiers: `DECIMAL(18, 8)` pour crypto, `DECIMAL(12, 2)` pour fiat

## APIs Externes

| API | Usage | Limite Gratuite |
|-----|-------|-----------------|
| CoinGecko | Prix crypto | 50 req/min |
| Binance | Positions/trades | 1200 req/min |
| Kraken | Positions/trades | 15 req/sec |
| Crypto.com | Positions/trades | Variable |
| Yahoo Finance | Prix actions/ETF | Throttled |
| Exchangerate-API | Taux de change | 1500 req/mois |

## Sécurité

- JWT access token: 15 minutes
- Refresh token: 7 jours
- Rate limiting sur toutes les routes
- CORS strict (origines whitelistées)
- Validation Pydantic sur tous les inputs
- Parameterized queries (SQLAlchemy)
- Secrets en variables d'environnement uniquement

## Modules Fonctionnels

1. **Auth** - Login, MFA, gestion users (admin only)
2. **Assets** - CRUD crypto/immo/actions/ETF
3. **Dashboard** - Vue globale patrimoine
4. **Analytics** - Métriques, corrélations, diversification
5. **AI** - Prédictions, anomalies, sentiment
6. **Alerts** - Notifications prix/performance
7. **Reports** - PDF, Excel, fiscalité (2086)
8. **Journal** - Notes, documents
9. **Calendar** - Dividendes, loyers, échéances
10. **Simulations** - What-if, projections, FIRE

## Conventions de Code

### Python (Backend)
- Black pour le formatage
- isort pour les imports
- Type hints obligatoires
- Docstrings Google style

### TypeScript (Frontend)
- ESLint + Prettier
- Composants fonctionnels uniquement
- Types explicites (pas de `any`)
- Barrel exports par dossier

## Tests

- Backend: pytest, coverage > 70%
- Frontend: Vitest + React Testing Library
- E2E: Playwright (optionnel)
