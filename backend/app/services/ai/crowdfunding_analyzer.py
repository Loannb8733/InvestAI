"""AI-powered crowdfunding project analysis using Claude API."""

import json
import logging
import uuid
from decimal import Decimal
from typing import Optional

import fitz  # PyMuPDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset import Asset
from app.models.crowdfunding_project import CrowdfundingProject
from app.models.portfolio import Portfolio
from app.models.project_audit import ProjectAudit

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
    """Analyzes crowdfunding project PDFs using Claude API."""

    def _extract_pdf_text(self, file_bytes: bytes) -> str:
        """Extract text from a PDF file using PyMuPDF."""
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text.strip())
        doc.close()
        return "\n\n---PAGE---\n\n".join(pages)

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
        import anthropic

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY non configurée — Audit Lab désactivé")

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

        # Call Claude API (async client to avoid blocking the event loop)
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        messages = self._build_messages(texts, munitions, total_capital)

        logger.info("Calling Claude API for crowdfunding analysis (%d documents)", len(texts))
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
        logger.info("Claude API response received (%d chars)", len(raw_text))

        # Parse JSON response
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw_text[start:end])
                except json.JSONDecodeError:
                    raise ValueError(f"Réponse Claude non-JSON : {raw_text[:200]}")
            else:
                raise ValueError(f"Réponse Claude non-JSON : {raw_text[:200]}")

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
