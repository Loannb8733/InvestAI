# Audit — Sécurité & intégrité des données

> **Périmètre** : analyse statique uniquement (lecture seule du dépôt). Aucune attaque, aucun scan réseau, aucune requête vers la production.
> **Stack auditée** : Python/FastAPI + SQLAlchemy (async/asyncpg) + Postgres/Supabase + Celery/Redis (backend Render) ; Vite/React (frontend Vercel).
> **Date** : 2026-06-03

---

## 1. Résumé exécutif

**Posture de sécurité : 7,5 / 10.**

La base est solide pour un produit à ce stade : secrets non commités, chiffrement Fernet (avec rotation) des clés d'API d'exchange, contrôle d'autorisation par `user_id` **cohérent** sur l'ensemble des endpoints métier, hachage bcrypt (12 rounds), MFA TOTP, révocation de refresh tokens (jti + blocklist Redis), lockout anti-bruteforce, en-têtes de sécurité et CORS verrouillé en production. `npm audit --omit=dev` retourne **0 vulnérabilité** et les dépendances Python sont épinglées sur des versions corrigées des CVE connues.

Les faiblesses restantes sont essentiellement des fuites d'information et des durcissements, pas des trous d'autorisation. Aucun IDOR exploitable n'a été identifié.

**Top 3 des risques les plus exploitables :**

1. **Énumération de comptes au `/register`** — `auth.py:145-149` renvoie « Un compte avec cet email existe déjà », permettant à un attaquant de cartographier les emails inscrits (les flux forgot-password / resend sont, eux, correctement protégés).
2. **Fuite de détails d'exception vers le client** — `api_keys.py` (import-history ~1404-1407 et sync ~1601-1604) renvoie `f"...{type(e).__name__}: {e}"` dans la réponse HTTP, exposant des détails internes (noms de classes, fragments de messages d'erreur d'exchange).
3. **Webhook Telegram authentifié de façon conditionnelle** — `telegram_webhook.py:54-57` : la vérification du secret n'a lieu **que si** `TELEGRAM_WEBHOOK_SECRET` est défini. Si la variable est absente en production, le webhook accepte des requêtes non authentifiées (atténué par la vérification `chat_id` ↔ utilisateur).

---

## 2. Constats par sévérité

### 🔴 Critique

_Aucun constat critique._ Pas de secret commité, pas d'IDOR exploitable, pas d'injection SQL, pas de RCE.

### 🟠 Élevé

| ID | Sévérité | OWASP | Fichier:ligne | Vulnérabilité | Impact | Recommandation |
|----|----------|-------|---------------|---------------|--------|----------------|
| H-01 | 🟠 Élevé | A07 Identification & Auth | `backend/app/api/v1/endpoints/telegram_webhook.py:54-57` | La validation du secret du webhook est conditionnelle (`if settings.TELEGRAM_WEBHOOK_SECRET:`). Si l'env n'est pas configuré en prod, le endpoint `/telegram/webhook` accepte des `callback_query` non authentifiés. | Un tiers pourrait forger des callbacks. Atténué par `_verify_chat_id` (le chat_id doit correspondre à un utilisateur enregistré) et le parsing strict, mais la défense en profondeur est rompue. | Rendre le secret **obligatoire en production** : échouer au démarrage (ou retourner 403 systématiquement) si `is_production and not TELEGRAM_WEBHOOK_SECRET` lorsque le bot est activé. |
| H-02 | 🟠 Élevé | A09 Logging / A04 Insecure Design | `backend/app/api/v1/endpoints/api_keys.py:~1404-1407` (import-history) et `~1601-1604` (sync) | Les exceptions sont renvoyées au client sous la forme `f"...{type(e).__name__}: {e}"`. | Divulgation d'informations : structure interne, messages d'erreur bruts des exchanges (pouvant inclure des fragments de requête signée, des chemins, des états internes). | Logger l'exception complète côté serveur, renvoyer un message générique au client (`"Une erreur est survenue lors de la synchronisation"`), comme c'est déjà fait dans `system.py`. |

### 🟡 Moyen

| ID | Sévérité | OWASP | Fichier:ligne | Vulnérabilité | Impact | Recommandation |
|----|----------|-------|---------------|---------------|--------|----------------|
| M-01 | 🟡 Moyen | A07 Identification & Auth | `backend/app/api/v1/endpoints/auth.py:145-149` | Énumération de comptes : `/register` confirme explicitement l'existence d'un email. | Cartographie des emails inscrits → ciblage phishing / credential stuffing. | Renvoyer un message générique (« Si cet email n'est pas déjà utilisé, le compte est créé ») ou un 201 neutre, comme les flux forgot/resend. |
| M-02 | 🟡 Moyen | A07 Identification & Auth | `backend/app/core/security.py:15-21` | Token binding faible : le fingerprint = `sha256(user_agent)[:16]`. Un User-Agent est trivialement rejouable par un attaquant ayant volé le token. | Le « binding » donne un faux sentiment de sécurité ; il n'empêche pas le rejeu d'un token volé depuis un autre client clonant l'UA. | Documenter la limite, ou renforcer avec un facteur côté serveur (IP /24, ou session id stocké). Ne pas considérer comme une protection anti-vol de token. |
| M-03 | 🟡 Moyen | A05 Misconfiguration | `backend/app/main.py` (endpoint `admin_fix_mirrors`, ~799-858, ~1045) | L'endpoint admin de correction renvoie un dump de debug (types/IDs/symboles de transactions) dans un tableau `log`. | Bien qu'admin-only, l'exposition de données détaillées dans la réponse augmente la surface en cas de compromission d'un compte admin. | Réduire le contenu du `log` (compteurs agrégés) ou le réserver à `DEBUG`. Envisager de retirer ces endpoints one-shot de la prod. |
| M-04 | 🟡 Moyen | A05 Misconfiguration | `backend/app/core/rate_limit.py:10-19` | `_get_real_client_ip` fait confiance à `X-Forwarded-For` / `X-Real-IP` sans validation du proxy de confiance. | Un client peut spoofer son IP via l'en-tête et contourner le rate limiting par IP (brute force, abus). | Ne lire `X-Forwarded-For` que derrière un proxy de confiance unique (prendre l'avant-dernier hop, ou faire confiance uniquement à l'IP injectée par Render). |
| M-05 | 🟡 Moyen | A05 Misconfiguration | `backend/app/core/config.py:125-127` | Pour Redis `rediss://` (Upstash), `ssl_cert_reqs=CERT_NONE` est ajouté automatiquement → vérification du certificat TLS désactivée pour la connexion Redis. | MITM possible sur le canal Redis (tokens de session/blocklist, cache, broker Celery) si l'attaquant est sur le chemin réseau. | Utiliser `CERT_REQUIRED` avec le bundle CA d'Upstash. À défaut, documenter le risque résiduel. |

### 🔵 Faible

| ID | Sévérité | OWASP | Fichier:ligne | Vulnérabilité | Impact | Recommandation |
|----|----------|-------|---------------|---------------|--------|----------------|
| L-01 | 🔵 Faible | A01 Broken Access Control | `backend/app/api/v1/endpoints/api_keys.py:~1678` (`get_import_status`) | Le polling lit `_import_tasks[task_id]` sans vérifier la propriété (task_id = hex aléatoire). | Un attaquant devrait deviner un task_id aléatoire ; surface très limitée, mais pas de contrôle d'ownership. | Stocker `user_id` avec la tâche et vérifier `task.user_id == current_user.id`. |
| L-02 | 🔵 Faible | A07 Identification & Auth | `backend/app/api/v1/endpoints/websocket.py:56-67` | `verify_ws_token` valide signature + `type=="access"` mais ne lie pas la connexion à un `user_id`. | Faible : le flux WS ne diffuse que des **prix de marché publics** (pas de données par utilisateur). Tout token valide y accède. | Acceptable en l'état ; si des données privées transitent un jour par le WS, extraire et binder le `user_id`. |
| L-03 | 🔵 Faible | A09 Logging | `backend/app/api/deps.py:155-176` (`get_optional_current_user`) | « Fail open » silencieux : toute exception → `None` (utilisateur anonyme). | Comportement attendu pour un auth optionnel, mais masque les erreurs de décodage. | Logger en `debug` les échecs inattendus pour faciliter le diagnostic. |
| L-04 | 🔵 Faible | A04 Insecure Design | `backend/app/api/v1/endpoints/auth.py` (Redis blocklist) | En cas d'indisponibilité de Redis, la blocklist de tokens révoqués « fail open ». | Un refresh token révoqué pourrait être réutilisé pendant une panne Redis. | Décider explicitement de la stratégie (fail open vs fail closed) et la documenter ; alerter sur l'indisponibilité de Redis. |

---

## 3. Secrets & dépendances

### Secrets

- **Aucun secret commité.** `git ls-files` ne contient que `.env.example`, `.env.production.example` et `backend/alembic/env.py`. Les fichiers `.env`/`.env.production` ne sont pas suivis. ✅
- Les fichiers d'exemple n'utilisent que des **placeholders** (`CHANGE_ME`, `CHANGE_ME_GENERATE_WITH_COMMAND_ABOVE`) avec les commandes de génération en commentaire. ✅
- `SECRET_KEY` et `FERNET_KEY` sont **requis sans valeur par défaut** (`config.py:20,27`) ; des validateurs imposent ≥32 caractères et rejettent les valeurs faibles connues. ✅
- `COOKIE_SECURE` est forcé à `True` hors `development` via un validateur (`config.py:34-41`). ✅

### Dépendances

- **Frontend** : `npm audit --omit=dev` → **0 vulnérabilité** (production). ✅
- **Backend** (`backend/requirements.txt`) : versions épinglées, CVE documentées en commentaire et corrigées :
  - `python-jose[cryptography]==3.4.0` (CVE-2024-33663 confusion d'algorithme, CVE-2024-33664 DoS JWE) ✅
  - `python-multipart==0.0.9` (CVE-2024-24762 ReDoS) ✅
  - `cryptography==43.0.3`, `aiohttp==3.10.11` (CVE-2024-23334 path traversal) ✅
- Point d'attention (statique) : `python-jose` reste une lib peu maintenue ; envisager une migration vers `pyjwt` à terme. `bcrypt==4.0.1` est ancien (compatibilité passlib historique) — surveiller.

---

## 4. Ce qui est déjà bien fait

- **Chiffrement au repos des clés d'exchange** : `MultiFernet` avec rotation (`FERNET_OLD_KEYS`), `encrypt_api_key`/`decrypt_api_key` (`security.py:98-137`). Les clés ne sont jamais exposées : `APIKeyResponse` exclut les champs chiffrés.
- **Contrôle d'autorisation cohérent (anti-IDOR)** : toutes les requêtes métier filtrent par `user_id` ou par propriété de portefeuille — vérifié sur `api_keys`, `transactions`, `portfolios`, `assets`, `notes`, `crowdfunding` (`_get_project_for_user` via join Asset→Portfolio→user_id). Endpoints `users`/`system` correctement gardés par `get_current_admin_user`.
- **Authentification robuste** : bcrypt 12 rounds ; JWT HS256 access 15 min / refresh révocable (jti + blocklist) ; lockout login (10 échecs / 900 s) ; anti-rejeu TOTP ; MFA avec backup codes hachés.
- **Pas d'injection SQL** : ORM SQLAlchemy partout ; les rares `text()` (data fixes one-shot dans `main.py`) sont paramétrés. Parsers CSV/PDF sûrs (`Decimal` + `InvalidOperation`, PyMuPDF sur flux, strip des caractères de contrôle, **aucun `eval`/`exec`**).
- **Signature des appels exchange** : Binance HMAC-SHA256 avec `recvWindow`, synchro d'horloge serveur, TLS 1.2+ avec `CERT_REQUIRED` et vérification du hostname (`binance.py:48-56,99-110`).
- **Idempotence des synchronisations** : déduplication par `internal_hash` (`_add_transaction_if_new`) **et** `external_id`, plus retries Celery bornés. La génération de l'échéancier crowdfunding préserve les entrées déjà réconciliées (`reconciliation_service.py:31-74`).
- **Durcissement réseau** : CORS verrouillé en prod (whitelist Vercel ; wildcard `*.vercel.app` uniquement hors prod) ; en-têtes `X-Content-Type-Options=nosniff`, `X-Frame-Options=DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS en prod ; OpenAPI/docs désactivés hors `DEBUG`.
- **Rate limiting** par catégorie (`auth_login` 5/min, `auth_register` 3/min, etc.).
- **Validation d'entrées** : Pydantic strict (regex sur `telegram_chat_id`, devises, longueur/complexité des mots de passe) ; upload PDF crowdfunding limité (extension `.pdf`, 10 Mo, 5 fichiers max).

---

## 5. Synthèse (< 300 mots)

**Posture globale : 7,5 / 10.** InvestAI présente une base de sécurité saine et cohérente pour un produit fintech à ce stade. Les fondamentaux sont en place : chiffrement Fernet (avec rotation) des clés d'exchange au repos, autorisation par `user_id` appliquée **uniformément** sur tous les endpoints métier (aucun IDOR exploitable trouvé), authentification robuste (bcrypt 12 rounds, JWT avec refresh révocable, MFA TOTP, lockout anti-bruteforce), absence d'injection SQL (ORM + `text()` paramétré, parsers sans `eval`), secrets non commités, et dépendances à jour (`npm audit` : 0 vuln ; CVE Python corrigées et documentées).

**Constats** : 0 🔴 Critique · 2 🟠 Élevé · 5 🟡 Moyen · 4 🔵 Faible. Les faiblesses sont des fuites d'information et des durcissements, non des défauts d'autorisation.

**Top 3 des risques exploitables :**
1. Énumération de comptes au `/register` — `auth.py:145-149`.
2. Fuite de détails d'exception vers le client — `api_keys.py:~1404-1407` et `~1601-1604`.
3. Authentification conditionnelle du webhook Telegram — `telegram_webhook.py:54-57` (à rendre obligatoire en prod).

**Confirmation du correctif récent cookies/CORS** : ✅ **le correctif tient.** `_set_auth_cookies` (`auth.py:96-123`) pose bien `SameSite=None; Secure` lorsque `COOKIE_SECURE` est actif (cookies cross-site Vercel↔Render), avec repli en `Lax` en dev local HTTP. `COOKIE_SECURE` est forcé à `True` hors `development` (`config.py:34-41`), et le CORS de production restreint les origines à la whitelist Vercel (wildcard `*.vercel.app` désactivé en prod). La cohérence cookie/CORS est correcte.
