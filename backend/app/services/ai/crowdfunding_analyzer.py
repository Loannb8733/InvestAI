"""AI-powered crowdfunding project analysis with multi-provider fallback."""

import json
import logging
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset import Asset
from app.models.crowdfunding_project import CrowdfundingProject
from app.models.portfolio import Portfolio
from app.models.project_audit import ProjectAudit
from app.services.ai.pdf_parser import PDFParser

logger = logging.getLogger(__name__)

_ANALYSIS_SCHEMA = {
    "project_name": "string — nom du projet",
    "operator": "string — nom de l'opérateur / promoteur",
    "location": "string — localisation du projet",
    "document_type": "string — 'deck', 'fici', ou 'mixed'",
    "tri": "number — taux de rendement interne annualisé en %",
    "duration_min": "integer — durée minimale en mois",
    "duration_max": "integer — durée maximale en mois",
    "collection_amount": "number — montant de la collecte en euros",
    "margin_percent": "number — marge brute promoteur en %",
    "ltv": "number — Loan-to-Value en % (dette senior / valeur du bien)",
    "ltc": "number — Loan-to-Cost en % (dette totale / coût total du projet)",
    "pre_sales_percent": "number — taux de pré-commercialisation en % (0 si non mentionné)",
    "equity_contribution": "number — apport en fonds propres de l'opérateur en euros",
    "guarantees": [
        {
            "type": "string — ex: 'Hypothèque légale de prêteur de deniers'",
            "rank": "string — ex: '1er rang', '2ème rang', ou null",
            "description": "string — description de la garantie",
            "strength": "string — 'forte', 'moyenne', ou 'faible'",
        }
    ],
    "admin_status": "string — ex: 'PC purgé', 'Déclaration préalable', 'PC en cours'",
    "score_operator": "integer 1-10 — solidité de l'opérateur",
    "score_location": "integer 1-10 — qualité de la localisation",
    "score_guarantees": "integer 1-10 — solidité des garanties",
    "score_risk_return": "integer 1-10 — rapport rendement/risque",
    "score_admin": "integer 1-10 — état administratif du projet",
    "risk_score": "integer 1-10 — score global de robustesse (10=très sûr)",
    "points_forts": ["string — max 5 points forts"],
    "points_vigilance": ["string — max 5 points de vigilance"],
    "red_flags": ["string — risques critiques détectés"],
    "verdict": "string — 'INVESTIR', 'VIGILANCE', ou 'NE_PAS_INVESTIR'",
}

_SYSTEM_PROMPT = """Tu es un analyste senior en immobilier et crowdfunding avec 15 ans d'expérience.
Tu analyses des documents de projets de crowdfunding immobilier (DECK commerciaux et FICI réglementaires).

Règles d'analyse :
- TRI : taux de rendement interne annualisé tel qu'indiqué dans le document
- LTV (Loan-to-Value) : dette senior / valeur du bien estimée × 100
- LTC (Loan-to-Cost) : dette totale / coût total du projet × 100
- Marge : marge brute promoteur = (CA prévisionnel - coût total) / CA prévisionnel × 100
- Pré-commercialisation : % des lots déjà vendus ou réservés (0 si non mentionné)
- Garanties : identifie le rang exact (1er, 2ème) et le type (hypothèque, caution, GAPD, nantissement)
- Score : note de 1 à 10 sur chaque pilier (10 = excellent)

Règles de scoring :
- Opérateur : CA, ancienneté, fonds propres engagés, historique de remboursement
- Localisation : tension du marché, prix/m² vs marché, attractivité
- Garanties : rang de l'hypothèque, nombre et qualité des sûretés
- Rendement/Risque : TRI vs risque, marge de sécurité, LTV/LTC
- Administratif : PC purgé, assurances, conformité réglementaire

Red flags automatiques à détecter :
- LTV > 80%
- Marge < 10%
- Pré-commercialisation = 0% sur un projet VEFA
- Pas d'hypothèque de 1er rang
- Opérateur sans historique vérifié
- PC non purgé

Tu dois TOUJOURS répondre en JSON valide, sans markdown ni commentaires."""


class CrowdfundingAnalyzerService:
    """Analyzes crowdfunding project PDFs with multi-provider fallback.

    Provider priority: Ollama (local/free) → Gemini (cloud/free) → Anthropic (cloud/paid) → Static regex.
    """

    def __init__(self) -> None:
        self._pdf_parser = PDFParser()

    def _extract_pdf_text(self, file_bytes: bytes) -> str:
        """Extract text from a PDF file using PDFParser."""
        return self._pdf_parser.extract_text(file_bytes)

    def _build_messages(
        self,
        texts: list[str],
        munitions: float,
        total_capital: float,
    ) -> list[dict]:
        """Build the Claude API messages."""
        combined = "\n\n===DOCUMENT===\n\n".join(texts)

        user_prompt = f"""Analyse les documents suivants pour un projet de crowdfunding immobilier.

DOCUMENTS :
{combined}

CONTEXTE INVESTISSEUR :
- Capital total du portefeuille : {total_capital:.2f} €
- Munitions disponibles (cash) : {munitions:.2f} €
- Règle d'allocation : max 5% du capital total par projet

Extrais toutes les données et retourne un JSON avec exactement cette structure :
{json.dumps(_ANALYSIS_SCHEMA, ensure_ascii=False, indent=2)}

Réponds UNIQUEMENT avec le JSON, sans aucun texte autour."""

        return [{"role": "user", "content": user_prompt}]

    def _validate_and_enrich(self, data: dict) -> dict:
        """Add automatic red flags based on thresholds."""
        red_flags = list(data.get("red_flags", []))

        ltv = data.get("ltv")
        if ltv is not None and ltv > 80:
            flag = f"LTV élevé ({ltv:.1f}%) — risque d'endettement excessif"
            if not any("LTV" in f for f in red_flags):
                red_flags.append(flag)

        margin = data.get("margin_percent")
        if margin is not None and margin < 10:
            flag = f"Marge faible ({margin:.1f}%) — peu de marge de sécurité"
            if not any("Marge" in f or "marge" in f for f in red_flags):
                red_flags.append(flag)

        pre_sales = data.get("pre_sales_percent")
        if pre_sales is not None and pre_sales == 0:
            flag = "Pas de pré-commercialisation — risque de sortie"
            if not any("pré-commercialisation" in f.lower() for f in red_flags):
                red_flags.append(flag)

        guarantees = data.get("guarantees", [])
        has_first_rank = any(g.get("rank", "").startswith("1") for g in guarantees)
        if guarantees and not has_first_rank:
            flag = "Pas d'hypothèque de 1er rang — garantie affaiblie"
            if not any("1er rang" in f for f in red_flags):
                red_flags.append(flag)

        data["red_flags"] = red_flags

        # Override verdict if critical red flags
        if len(red_flags) >= 3:
            data["verdict"] = "NE_PAS_INVESTIR"
        elif len(red_flags) >= 2 and data.get("verdict") == "INVESTIR":
            data["verdict"] = "VIGILANCE"

        return data

    async def _compute_diversification(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        audit_data: dict,
    ) -> dict:
        """Compute diversification impact of adding this project to portfolio.

        Returns dict with diversification_impact, correlation_score, portfolio_concentration.
        """
        # Get user's existing portfolio composition
        result = await db.execute(
            select(Asset, Portfolio)
            .join(Portfolio, Asset.portfolio_id == Portfolio.id)
            .where(Portfolio.user_id == user_id)
        )
        rows = result.all()

        # Build portfolio breakdown
        asset_type_values: dict[str, float] = {}
        total_value = 0.0
        crowdfunding_locations: list[str] = []
        crowdfunding_count = 0

        for asset, portfolio in rows:
            val = float(asset.current_price or 0) * float(asset.quantity or 0)
            total_value += val
            atype = asset.asset_type.value if asset.asset_type else "other"
            asset_type_values[atype] = asset_type_values.get(atype, 0) + val

        # Get crowdfunding project locations
        cf_result = await db.execute(
            select(CrowdfundingProject)
            .join(Asset, CrowdfundingProject.asset_id == Asset.id)
            .join(Portfolio, Asset.portfolio_id == Portfolio.id)
            .where(Portfolio.user_id == user_id)
        )
        for project in cf_result.scalars().all():
            crowdfunding_count += 1
            # We don't have location on the project model, use platform as proxy
            if project.platform:
                crowdfunding_locations.append(project.platform)

        # Concentration analysis
        new_location = (audit_data.get("location") or "").lower()

        # Geographic concentration
        geo_concentration = 0.0
        if new_location and crowdfunding_locations:
            same_region = sum(
                1
                for loc in crowdfunding_locations
                if any(word in loc.lower() for word in new_location.split() if len(word) > 3)
            )
            if crowdfunding_count > 0:
                geo_concentration = same_region / crowdfunding_count

        # Asset type concentration
        cf_value = asset_type_values.get("crowdfunding", 0)
        new_amount = audit_data.get("collection_amount", 0) or 0
        type_concentration = 0.0
        if total_value > 0:
            type_concentration = (cf_value + new_amount) / (total_value + new_amount)

        # Risk/return: high TRI with low guarantees = high correlation risk
        tri = audit_data.get("tri") or 0
        risk_score = audit_data.get("risk_score") or 5
        risk_return_score = min(1.0, (tri / 15.0) * (1 - risk_score / 10.0))

        # Overall correlation (weighted average of concentrations)
        correlation = round(
            geo_concentration * 0.3 + type_concentration * 0.4 + risk_return_score * 0.3,
            2,
        )
        correlation = min(1.0, max(0.0, correlation))

        # Impact verdict
        if correlation > 0.6:
            impact = "degrade"
        elif correlation > 0.3:
            impact = "neutre"
        else:
            impact = "ameliore"

        concentration = {
            "geographic": {
                "score": round(geo_concentration, 2),
                "detail": f"{int(geo_concentration * 100)}% de projets dans la même zone",
            },
            "asset_type": {
                "score": round(type_concentration, 2),
                "detail": f"Crowdfunding = {type_concentration * 100:.1f}% du portefeuille après investissement",
            },
            "risk_return": {
                "score": round(risk_return_score, 2),
                "detail": f"TRI {tri}% avec score risque {risk_score}/10",
            },
        }

        return {
            "diversification_impact": impact,
            "correlation_score": correlation,
            "portfolio_concentration": concentration,
        }

    async def _call_anthropic(self, messages: list[dict]) -> str:
        """Call Anthropic Claude API and return raw text response."""
        try:
            import anthropic
        except ImportError:
            raise ValueError("Le package 'anthropic' n'est pas installé. Utilisez Ollama ou installez anthropic.")

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        logger.info("Calling Claude API for crowdfunding analysis")
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=messages,
                timeout=90.0,
            )
        except anthropic.AuthenticationError as exc:
            raise ValueError("Clé API Anthropic invalide — vérifiez ANTHROPIC_API_KEY") from exc
        except anthropic.RateLimitError as exc:
            raise ValueError("Limite de requêtes Anthropic atteinte — réessayez dans quelques minutes") from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            logger.error("Anthropic API connectivity error: %s", exc)
            raise ValueError("Timeout ou erreur de connexion à l'API Anthropic") from exc
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            raise ValueError(f"Erreur API Anthropic : {exc}") from exc

        raw_text = response.content[0].text
        logger.info("Claude response received (%d chars)", len(raw_text))
        return raw_text

    async def _call_groq(self, messages: list[dict]) -> str:
        """Call Groq API (free tier, fast inference) and return raw text response."""
        import httpx

        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": messages[0]["content"]},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }

        logger.info("Calling Groq API (llama-3.1-8b-instant) for crowdfunding analysis")
        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.TimeoutException as exc:
                raise ValueError("Timeout de connexion à l'API Groq") from exc
            except httpx.ConnectError as exc:
                raise ValueError("Erreur de connexion à l'API Groq") from exc

        if resp.status_code == 401:
            raise ValueError("Clé API Groq invalide — vérifiez GROQ_API_KEY")
        if resp.status_code == 429:
            raise ValueError("Limite de requêtes Groq atteinte — réessayez dans quelques minutes")
        if resp.status_code != 200:
            raise ValueError(f"Erreur Groq (HTTP {resp.status_code}) : {resp.text[:200]}")

        data = resp.json()
        try:
            raw_text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Réponse Groq inattendue : {str(data)[:200]}") from exc

        logger.info("Groq response received (%d chars)", len(raw_text))
        return raw_text

    async def _call_gemini(self, messages: list[dict]) -> str:
        """Call Google Gemini API (free tier) and return raw text response."""
        import httpx

        # Build the prompt from system + user messages
        parts = [{"text": _SYSTEM_PROMPT}]
        for msg in messages:
            parts.append({"text": msg["content"]})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash"
            f":generateContent?key={settings.GEMINI_API_KEY}"
        )

        logger.info("Calling Gemini API for crowdfunding analysis")
        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                resp = await client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                raise ValueError("Timeout de connexion à l'API Gemini") from exc
            except httpx.ConnectError as exc:
                raise ValueError("Erreur de connexion à l'API Gemini") from exc

        if resp.status_code == 400:
            detail = resp.json().get("error", {}).get("message", resp.text[:200])
            raise ValueError(f"Erreur Gemini : {detail}")
        if resp.status_code == 429:
            raise ValueError("Limite de requêtes Gemini atteinte — réessayez dans quelques minutes")
        if resp.status_code != 200:
            raise ValueError(f"Erreur Gemini (HTTP {resp.status_code}) : {resp.text[:200]}")

        data = resp.json()
        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Réponse Gemini inattendue : {str(data)[:200]}") from exc

        logger.info("Gemini response received (%d chars)", len(raw_text))
        return raw_text

    def _is_ollama_reachable(self) -> bool:
        """Check if OLLAMA_URL points to a likely reachable host.

        In production (Render, Railway), Docker-internal hostnames like 'ollama'
        are not reachable. In development (Docker Compose), they are.
        """
        if settings.APP_ENV == "production":
            from urllib.parse import urlparse

            parsed = urlparse(settings.OLLAMA_URL)
            hostname = parsed.hostname or ""
            if hostname and "." not in hostname and hostname not in ("localhost", "127"):
                return False
        return True

    async def _call_ollama(self, messages: list[dict]) -> str:
        """Call local Ollama API and return raw text response."""
        import httpx

        if not self._is_ollama_reachable():
            raise ValueError(f"Ollama skipped (Docker-internal URL: {settings.OLLAMA_URL})")

        url = f"{settings.OLLAMA_URL}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": messages[0]["content"]},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 4096},
        }

        logger.info("Calling Ollama (%s) at %s", settings.OLLAMA_MODEL, url)
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.error("Ollama connection failed: %s: %s", type(exc).__name__, exc)
                raise ValueError(f"Ollama non disponible ({settings.OLLAMA_URL})") from exc

        if resp.status_code != 200:
            raise ValueError(f"Erreur Ollama (HTTP {resp.status_code}) : {resp.text[:200]}")

        data = resp.json()
        raw_text = data.get("message", {}).get("content", "")
        if not raw_text:
            raise ValueError("Réponse Ollama vide")

        logger.info("Ollama response received (%d chars)", len(raw_text))
        return raw_text

    def _analyze_statically(self, file_contents: list[tuple[str, bytes]]) -> dict:
        """Fallback: extract KPIs using regex when no LLM is available."""
        from app.services.ai.pdf_parser import ExtractedFinancials

        all_financials: list[ExtractedFinancials] = []
        for filename, content in file_contents:
            try:
                fin = self._pdf_parser.extract_financials(content)
                all_financials.append(fin)
            except Exception as exc:
                logger.warning("Static extraction failed for %s: %s", filename, exc)

        # Merge: take first non-None value from each document
        merged = ExtractedFinancials()
        for fin in all_financials:
            for fld in [
                "chiffre_affaires",
                "prix_revient",
                "marge_brute",
                "marge_brute_percent",
                "tri",
                "duration_min",
                "duration_max",
                "collecte",
                "ltv",
                "ltc",
                "pre_commercialisation",
                "fonds_propres",
            ]:
                if getattr(merged, fld) is None and getattr(fin, fld) is not None:
                    setattr(merged, fld, getattr(fin, fld))

        # Build output matching _ANALYSIS_SCHEMA
        data: dict = {
            "project_name": "Analyse statique (sans IA)",
            "operator": None,
            "location": None,
            "document_type": "mixed",
            "tri": merged.tri,
            "duration_min": merged.duration_min,
            "duration_max": merged.duration_max,
            "collection_amount": merged.collecte,
            "margin_percent": merged.marge_brute_percent,
            "ltv": merged.ltv,
            "ltc": merged.ltc,
            "pre_sales_percent": merged.pre_commercialisation or 0,
            "equity_contribution": merged.fonds_propres,
            "guarantees": [],
            "admin_status": None,
            "points_forts": [],
            "points_vigilance": ["Analyse statique (regex) — résultats partiels, relecture recommandée"],
            "red_flags": [],
            "verdict": "VIGILANCE",
        }

        # Auto-score based on extracted values
        scores = {}
        scores["score_operator"] = 5  # Unknown
        scores["score_location"] = 5  # Unknown
        scores["score_admin"] = 5  # Unknown

        # Score guarantees
        scores["score_guarantees"] = 3  # No guarantee info from regex

        # Score risk/return
        margin = merged.marge_brute_percent
        if margin is not None and margin >= 20:
            scores["score_risk_return"] = 7
        elif margin is not None and margin >= 10:
            scores["score_risk_return"] = 5
        else:
            scores["score_risk_return"] = 3

        # Risk score = average
        avg = sum(scores.values()) / len(scores)
        scores["risk_score"] = round(avg)
        data.update(scores)

        # Auto-generate points forts
        if merged.tri and merged.tri >= 8:
            data["points_forts"].append(f"TRI attractif de {merged.tri}%")
        if margin and margin >= 20:
            data["points_forts"].append(f"Marge promoteur confortable ({margin:.1f}%)")
        if merged.ltv and merged.ltv < 60:
            data["points_forts"].append(f"LTV conservateur ({merged.ltv:.1f}%)")
        if merged.fonds_propres and merged.fonds_propres > 100000:
            data["points_forts"].append("Fonds propres significatifs de l'opérateur")

        logger.info(
            "Static analysis: TRI=%s, margin=%s, LTV=%s, collecte=%s",
            merged.tri,
            merged.marge_brute_percent,
            merged.ltv,
            merged.collecte,
        )
        return data

    async def analyze_documents(
        self,
        db: AsyncSession,
        file_contents: list[tuple[str, bytes]],
        user_id: uuid.UUID,
        project_id: Optional[uuid.UUID] = None,
        munitions: float = 0.0,
        total_capital: float = 0.0,
    ) -> ProjectAudit:
        """Analyze uploaded PDF documents and persist results.

        Args:
            db: Database session.
            file_contents: List of (filename, bytes) tuples.
            user_id: Current user ID.
            project_id: Optional linked crowdfunding project.
            munitions: Available cash for investment.
            total_capital: Total portfolio value.

        Returns:
            Persisted ProjectAudit instance.
        """
        # Extract text from PDFs
        texts = []
        file_names = []
        for filename, content in file_contents:
            file_names.append(filename)
            try:
                text = self._extract_pdf_text(content)
            except Exception as exc:
                logger.error("Failed to extract text from %s: %s", filename, exc)
                raise ValueError(f"Impossible de lire le PDF '{filename}' — fichier corrompu ou protégé") from exc
            if text.strip():
                texts.append(text)

        if not texts:
            raise ValueError("Aucun texte extractible des PDFs fournis")

        messages = self._build_messages(texts, munitions, total_capital)

        # Provider cascade: Groq → Gemini → Anthropic → Ollama → Static
        # Cloud providers first (fast, reliable), Ollama last (slow on CPU)
        providers: list[tuple[str, object]] = []
        if settings.GROQ_API_KEY:
            providers.append(("Groq", self._call_groq))
        if settings.GEMINI_API_KEY:
            providers.append(("Gemini", self._call_gemini))
        if settings.ANTHROPIC_API_KEY:
            providers.append(("Anthropic", self._call_anthropic))
        if settings.OLLAMA_URL:
            providers.append(("Ollama", self._call_ollama))

        raw_text = None
        data = None
        for provider_name, provider_fn in providers:
            try:
                raw_text = await provider_fn(messages)
                break
            except Exception as exc:
                logger.warning("Provider %s failed: %s", provider_name, exc)
                continue

        if raw_text is not None:
            # Parse JSON response from LLM
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                start = raw_text.find("{")
                end = raw_text.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        data = json.loads(raw_text[start:end])
                    except json.JSONDecodeError:
                        logger.warning("LLM returned non-JSON, falling back to static: %s", raw_text[:100])
                        data = None

        # Ultimate fallback: static regex analysis
        if data is None:
            logger.info("All LLM providers failed or unavailable — using static analysis")
            data = self._analyze_statically(file_contents)
            raw_text = json.dumps(data, ensure_ascii=False)

        # Validate and enrich
        data = self._validate_and_enrich(data)

        # Compute diversification analysis
        diversification = await self._compute_diversification(db, user_id, data)
        data.update(diversification)

        # Calculate suggested investment (reduce if highly correlated)
        max_allocation = total_capital * 0.05 if total_capital > 0 else 500.0
        correlation = data.get("correlation_score", 0)
        if correlation > 0.5:
            max_allocation *= 0.4  # 2% instead of 5%
        elif correlation > 0.3:
            max_allocation *= 0.7  # ~3.5% instead of 5%
        suggested = min(max_allocation, munitions * 0.5) if munitions > 0 else max_allocation
        data["suggested_investment"] = round(suggested, 2)

        # Add diversification warning to points_vigilance if needed
        if data.get("diversification_impact") == "degrade":
            vigilance = data.get("points_vigilance", [])
            vigilance.append(
                f"Corrélation élevée ({correlation:.0%}) avec le portefeuille existant — allocation réduite à {max_allocation:.0f}€"
            )
            data["points_vigilance"] = vigilance

        # Persist to database
        audit = ProjectAudit(
            id=uuid.uuid4(),
            user_id=user_id,
            project_id=project_id,
            file_names=file_names,
            document_type=data.get("document_type"),
            project_name=data.get("project_name"),
            operator=data.get("operator"),
            location=data.get("location"),
            tri=Decimal(str(data["tri"])) if data.get("tri") is not None else None,
            duration_min=data.get("duration_min"),
            duration_max=data.get("duration_max"),
            collection_amount=(
                Decimal(str(data["collection_amount"])) if data.get("collection_amount") is not None else None
            ),
            margin_percent=(Decimal(str(data["margin_percent"])) if data.get("margin_percent") is not None else None),
            ltv=Decimal(str(data["ltv"])) if data.get("ltv") is not None else None,
            ltc=Decimal(str(data["ltc"])) if data.get("ltc") is not None else None,
            pre_sales_percent=(
                Decimal(str(data["pre_sales_percent"])) if data.get("pre_sales_percent") is not None else None
            ),
            equity_contribution=(
                Decimal(str(data["equity_contribution"])) if data.get("equity_contribution") is not None else None
            ),
            guarantees=data.get("guarantees", []),
            admin_status=data.get("admin_status"),
            score_operator=data.get("score_operator"),
            score_location=data.get("score_location"),
            score_guarantees=data.get("score_guarantees"),
            score_risk_return=data.get("score_risk_return"),
            score_admin=data.get("score_admin"),
            risk_score=data.get("risk_score"),
            points_forts=data.get("points_forts", []),
            points_vigilance=data.get("points_vigilance", []),
            red_flags=data.get("red_flags", []),
            verdict=data.get("verdict", "VIGILANCE"),
            suggested_investment=Decimal(str(data.get("suggested_investment", 0))),
            raw_analysis=raw_text,
            diversification_impact=data.get("diversification_impact"),
            correlation_score=(
                Decimal(str(data["correlation_score"])) if data.get("correlation_score") is not None else None
            ),
            portfolio_concentration=data.get("portfolio_concentration", {}),
        )
        db.add(audit)
        await db.flush()

        logger.info(
            "Audit saved: %s — verdict=%s, risk_score=%s",
            audit.id,
            audit.verdict,
            audit.risk_score,
        )
        return audit


crowdfunding_analyzer = CrowdfundingAnalyzerService()
