"""
services/classifier.py — AI risk classifier for contract clauses.

For each clause, we ask GPT-4o-mini to classify it against a
15-category risk taxonomy and return structured JSON.

Key design decisions:
  1. GROUNDED — the LLM only reasons over the clause text provided.
     It never invents risks not present in the text.
  2. STRUCTURED OUTPUT — we enforce a strict JSON schema so parsing
     never fails.
  3. ZERO = safe — if no risk is found, severity returns 0 and we
     skip the clause in the UI.
"""
import json
import openai
from dataclasses import dataclass
from typing import Optional
from app.config import OPENAI_API_KEY, CHAT_MODEL
import logging

logger = logging.getLogger(__name__)
client = openai.OpenAI(api_key=OPENAI_API_KEY)


# ── Risk taxonomy ───────────────────────────────────────────────────────
# 15 categories that cover the most common contract risks for everyday users

RISK_CATEGORIES = {
    "liability_cap": {
        "name": "Liability Cap",
        "description": "Limits how much the other party must pay if something goes wrong",
        "red_flags": ["30 days", "fees paid", "aggregate liability", "in no event shall"]
    },
    "unilateral_amendment": {
        "name": "Unilateral Amendment",
        "description": "Allows one party to change contract terms without your consent",
        "red_flags": ["modify at any time", "reserves the right to change", "continued use constitutes"]
    },
    "auto_renewal": {
        "name": "Auto-Renewal",
        "description": "Contract renews automatically, often locking you in for another full term",
        "red_flags": ["automatically renew", "auto-renew", "unless cancelled", "successive term"]
    },
    "broad_ip_assignment": {
        "name": "Broad IP Assignment",
        "description": "Claims ownership of work or content you create using their service",
        "red_flags": ["sole and exclusive property", "work product", "assigns all rights", "work for hire"]
    },
    "non_compete": {
        "name": "Non-Compete / Non-Solicitation",
        "description": "Restricts your ability to work in your field after the contract ends",
        "red_flags": ["shall not compete", "non-compete", "restraint of trade", "solicit"]
    },
    "data_sharing": {
        "name": "Data Sharing / Privacy",
        "description": "Allows your personal or business data to be shared with third parties",
        "red_flags": ["share with third parties", "sell your data", "aggregate data", "anonymised data"]
    },
    "termination_for_convenience": {
        "name": "Termination For Convenience",
        "description": "Allows the other party to end the contract at any time for any reason",
        "red_flags": ["terminate for convenience", "at any time without cause", "immediately terminate"]
    },
    "arbitration_waiver": {
        "name": "Arbitration / Dispute Resolution",
        "description": "Forces disputes into arbitration, often limiting your legal rights",
        "red_flags": ["binding arbitration", "waive right to jury", "class action waiver", "arbitrator"]
    },
    "jurisdiction": {
        "name": "Governing Law / Jurisdiction",
        "description": "Specifies which country or state's laws apply and where disputes must be filed",
        "red_flags": ["governed by the laws of", "jurisdiction of", "courts of"]
    },
    "penalty_clause": {
        "name": "Penalty / Liquidated Damages",
        "description": "Requires you to pay a fixed penalty amount if certain conditions are breached",
        "red_flags": ["liquidated damages", "penalty", "forfeit", "damages of"]
    },
    "indemnification": {
        "name": "Indemnification",
        "description": "Makes you financially responsible for legal costs or damages the other party faces",
        "red_flags": ["shall indemnify", "hold harmless", "defend and indemnify", "indemnification"]
    },
    "confidentiality": {
        "name": "Confidentiality",
        "description": "Restricts what information you can share and for how long",
        "red_flags": ["confidential information", "shall not disclose", "proprietary information"]
    },
    "force_majeure": {
        "name": "Force Majeure",
        "description": "Allows the other party to suspend obligations during events beyond their control",
        "red_flags": ["force majeure", "acts of god", "beyond reasonable control", "excuse performance"]
    },
    "notice_period": {
        "name": "Notice Requirements",
        "description": "Specifies strict notice periods and methods that could cause you to lose rights",
        "red_flags": ["written notice", "days prior notice", "certified mail", "days before"]
    },
    "payment_terms": {
        "name": "Payment Terms",
        "description": "Unusual payment conditions such as non-refundable fees, late penalties, or unusual billing cycles",
        "red_flags": ["non-refundable", "late fee", "interest on overdue", "upfront payment"]
    }
}


# ── Prompt template ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a contract risk analyst. Your job is to analyse a single contract clause and determine if it contains any of the specified risk categories.

RULES:
1. Only analyse what is EXPLICITLY stated in the clause text provided.
2. Do NOT infer or assume risks that are not clearly present in the text.
3. If no significant risk is found, return severity: 0.
4. Return ONLY valid JSON matching the exact schema below. No preamble, no markdown.

JSON SCHEMA:
{
  "category_key": "<one of the 15 category keys, or 'none'>",
  "category_name": "<human-readable category name>",
  "severity": <integer 0-5>,
  "risk_level": "<none|low|medium|high>",
  "explanation": "<plain English explanation for a non-lawyer, 2-3 sentences max>",
  "flagged_text": "<exact quote from clause that is the source of risk, or empty string>",
  "negotiate_tip": "<specific, actionable negotiation advice, or empty string>"
}

SEVERITY SCALE:
0 = No risk found
1 = Minor concern, informational only
2 = Low risk — worth knowing about
3 = Medium risk — consider negotiating
4 = High risk — strongly recommend changing
5 = Critical risk — do not sign without changing this"""


def classify_clause(clause_text: str, clause_title: str = "") -> dict:
    """
    Classify a single clause against all 15 risk categories.
    Returns a dict matching the JSON schema above.
    """
    # Build the category list for the prompt
    categories_text = "\n".join(
        f"- {key}: {info['name']} — {info['description']}"
        for key, info in RISK_CATEGORIES.items()
    )

    user_prompt = f"""CLAUSE TITLE: {clause_title or "Untitled clause"}

CLAUSE TEXT:
{clause_text}

RISK CATEGORIES TO CHECK:
{categories_text}

Analyse this clause and return JSON."""

    try:
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,       # Low temp = consistent, factual output
            max_tokens=500,
            response_format={"type": "json_object"}  # Force JSON output
        )

        raw = response.choices[0].message.content
        result = json.loads(raw)

        # Validate and sanitise the response
        result = _sanitise_result(result)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for clause '{clause_title}': {e}")
        return _empty_result()
    except Exception as e:
        logger.error(f"Classification failed for clause '{clause_title}': {e}")
        return _empty_result()


def classify_clauses_batch(clauses: list[dict]) -> list[dict]:
    """
    Classify a list of clauses sequentially.
    Each clause dict must have: text, title (optional).
    Returns list of classification results in same order.
    """
    results = []
    for i, clause in enumerate(clauses):
        logger.info(f"Classifying clause {i+1}/{len(clauses)}: {clause.get('title', '')[:40]}")
        result = classify_clause(
            clause_text=clause.get("text", ""),
            clause_title=clause.get("title", "")
        )
        results.append(result)
    return results


def compute_document_risk_score(risk_results: list[dict]) -> float:
    """
    Compute an overall document risk score (0–100).

    Formula:
      - Each clause contributes: severity × weight
      - High severity clauses are weighted more heavily
      - Normalised to 0–100
    """
    if not risk_results:
        return 0.0

    # Only score clauses that have actual risk (severity > 0)
    scored = [r for r in risk_results if r.get("severity", 0) > 0]

    if not scored:
        return 5.0  # Slight non-zero to indicate "reviewed but clean"

    # Weighted sum — severity 5 counts 3x more than severity 1
    weight_map = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}
    total_weight = sum(weight_map.get(r["severity"], 0) for r in scored)
    max_possible = len(scored) * weight_map[5]

    # Scale to 0–100, apply a mild curve so scores spread nicely
    raw = (total_weight / max_possible) * 100 if max_possible > 0 else 0
    # Boost: even 1 high-risk clause should push score above 60
    has_critical = any(r["severity"] >= 4 for r in scored)
    if has_critical:
        raw = max(raw, 60.0)

    return round(min(raw, 100.0), 1)


# ── Helpers ─────────────────────────────────────────────────────────────

def _sanitise_result(result: dict) -> dict:
    """Ensure all required keys exist and values are valid."""
    severity = int(result.get("severity", 0))
    severity = max(0, min(5, severity))  # Clamp to 0–5

    risk_level = result.get("risk_level", "none")
    if risk_level not in ("none", "low", "medium", "high"):
        risk_level = _severity_to_level(severity)

    return {
        "category_key":   result.get("category_key", "none"),
        "category_name":  result.get("category_name", ""),
        "severity":       severity,
        "risk_level":     risk_level,
        "explanation":    result.get("explanation", ""),
        "flagged_text":   result.get("flagged_text", ""),
        "negotiate_tip":  result.get("negotiate_tip", "")
    }


def _empty_result() -> dict:
    return {
        "category_key": "none", "category_name": "",
        "severity": 0, "risk_level": "none",
        "explanation": "", "flagged_text": "", "negotiate_tip": ""
    }


def _severity_to_level(severity: int) -> str:
    if severity >= 4: return "high"
    if severity >= 2: return "medium"
    if severity >= 1: return "low"
    return "none"
