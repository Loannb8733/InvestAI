import json
from typing import Any

ANALYSIS_SCHEMA = {
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

SYSTEM_PROMPT = """Tu es un analyste senior en immobilier et crowdfunding avec 15 ans d'expérience.
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

Tu dois TOUJOURS répondre en JSON valide, sans markdown ni commentaires."""  # noqa: RUF001


def build_messages(texts: list[str], cash: float, total_capital: float) -> list[dict[str, str]]:
    """Message utilisateur : les documents, le contexte de l'investisseur et le schéma JSON attendu."""
    combined = "\n\n===DOCUMENT===\n\n".join(texts)
    user_prompt = f"""Analyse les documents suivants pour un projet de crowdfunding immobilier.

DOCUMENTS :
{combined}

CONTEXTE INVESTISSEUR :
- Capital total du portefeuille : {total_capital:.2f} €
- Munitions disponibles (cash) : {cash:.2f} €
- Règle d'allocation : max 5% du capital total par projet

Extrais toutes les données et retourne un JSON avec exactement cette structure :
{json.dumps(ANALYSIS_SCHEMA, ensure_ascii=False, indent=2)}

Réponds UNIQUEMENT avec le JSON, sans aucun texte autour."""
    return [{"role": "user", "content": user_prompt}]


def parse_answer(raw_text: str) -> Any:
    """JSON de la réponse, extrait d'un éventuel texte autour des accolades ; None s'il est illisible."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if not (start >= 0 and end > start):
            return None
        try:
            data = json.loads(raw_text[start:end])
        except json.JSONDecodeError:
            return None
    return data
