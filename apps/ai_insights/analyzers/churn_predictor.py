"""
apps/ai_insights/analyzers/churn_predictor.py
----------------------------------------------
SCRUM-27 — Customer Churn Predictor v3.0

Pipeline:
  1. Feature engineering — pre-limited queryset (max 200 customers) for scalability
  2. Rule-based pre-scoring — free, no API calls
  3. AI refinement — top 5 HIGH/CRITICAL only, sequential with pauses

Fixes vs v2.0:
  - Import dynamique hacky supprimé → from django.conf import settings
  - Queryset pré-limité à 200 avant feature engineering (scalabilité)
  - confidence correctement calculée (medium si IA non appelée, low si IA échouée)
  - time.sleep() uniquement dans l'analyzer (pas dans la vue)
  - customer_name inclus dans le résultat (display only, never sent to AI)
  - aging_risk_score "unknown" dérivé depuis overdue_ratio

Security:
  Customer names and account codes are NEVER sent to AI.
  Each customer is referred to as "Customer #N" in prompts.
"""

import logging
import time
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Max, Sum, Q
from django.db.models.functions import TruncMonth

from apps.ai_insights.client import AIClient, AIClientError, RateLimitError

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

MIN_PURCHASES         = 3
RECENCY_CRITICAL_DAYS = 90
RECENCY_HIGH_DAYS     = 60
RECENCY_MEDIUM_DAYS   = 30
ANALYSIS_WINDOW_DAYS  = 365
PRE_FILTER_LIMIT      = 200   # max customers fetched before feature engineering
AI_LIMIT              = getattr(settings, "CHURN_AI_LIMIT", 5)
AI_INTER_CALL_DELAY   = 3     # seconds between sequential AI calls

SYSTEM_PROMPT = """You are a senior B2B customer retention analyst for a Libyan distribution company.

Your task: Given anonymized behavioral data for ONE specific customer, provide a precise,
data-driven churn assessment and a PERSONALIZED retention plan.

CRITICAL RULES:
1. Every action MUST reference specific numbers (days inactive, LYD amounts, percentages).
2. Actions must differ based on the dominant risk signal:
   - Recency: focus on re-engagement and understanding the gap.
   - Revenue trend: focus on competitive pricing and order recovery.
   - Payment risk: focus on financial restructuring before new orders.
3. Each action must be executable today by an account manager.
4. Confidence = "high" only if all 4 signals are consistent.

Currency: LYD (Libyan Dinar)

Return ONLY valid JSON — no markdown, no preamble:
{
  "refined_churn_score": <float 0.0–1.0>,
  "churn_label": "low" | "medium" | "high" | "critical",
  "ai_explanation": "<2-3 sentences specific to THIS customer's numbers>",
  "recommended_actions": [
    "<action 1 — cites exact numbers>",
    "<action 2 — addresses secondary signal>",
    "<action 3 — monitoring/escalation>"
  ],
  "key_risk_factors": ["<factor with value>", "<factor with value>"],
  "confidence": "high" | "medium" | "low"
}"""


class ChurnPredictor:

    def __init__(self):
        self._client = AIClient()

    def predict(self, company, top_n: int = 20, use_ai: bool = True) -> list[dict]:
        logger.info("[ChurnPredictor] company=%s top_n=%d use_ai=%s", company.id, top_n, use_ai)

        features = self._compute_features(company)
        if not features:
            return []

        scored = sorted(
            [self._rule_based_score(f) for f in features],
            key=lambda x: -x["churn_score"]
        )
        top = scored[:top_n]

        if not use_ai:
            return [self._format_result(r, ai_result=None, ai_called=False) for r in top]

        ai_call_count = 0
        results       = []

        for rank, customer_data in enumerate(top, start=1):
            should_call_ai = (
                customer_data["pre_label"] in ("high", "critical")
                and ai_call_count < AI_LIMIT
            )
            ai_result = None
            ai_called = False

            if should_call_ai:
                if ai_call_count > 0:
                    time.sleep(AI_INTER_CALL_DELAY)
                ai_called = True
                try:
                    ai_result = self._call_ai(customer_data, company.id, rank)
                    if ai_result and not ai_result.get("error"):
                        ai_call_count += 1
                    else:
                        ai_result = None
                except RateLimitError:
                    logger.warning("[ChurnPredictor] Rate limit hit at rank %d — stopping AI calls", rank)
                    # Stop all further AI calls for this batch
                    results.append(self._format_result(customer_data, None, ai_called=True))
                    for remaining in top[rank:]:
                        results.append(self._format_result(remaining, None, ai_called=False))
                    break
                except AIClientError as exc:
                    logger.warning("[ChurnPredictor] AI failed rank %d: %s", rank, exc)

            results.append(self._format_result(customer_data, ai_result, ai_called=ai_called))

        logger.info("[ChurnPredictor] Done: %d predictions, %d AI calls for company=%s",
                    len(results), ai_call_count, company.id)
        return results

    # ── Feature engineering ───────────────────────────────────────────────────

    def _compute_features(self, company) -> list[dict]:
        from apps.transactions.models import MaterialMovement
        from apps.aging.models import AgingReceivable, AgingSnapshot
        from apps.customers.models import Customer

        today       = date.today()
        period_from = today - timedelta(days=ANALYSIS_WINDOW_DAYS)

        # Pre-limit to top 200 by revenue before expensive feature engineering
        sales_per_customer = (
            MaterialMovement.objects
            .filter(company=company, movement_type="ف بيع", movement_date__gte=period_from)
            .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
            .values("customer_name")
            .annotate(
                purchase_count=Count("id"),
                last_purchase=Max("movement_date"),
                total_revenue=Sum("total_out"),
            )
            .order_by("-total_revenue")[:PRE_FILTER_LIMIT]
        )

        monthly_by_customer = (
            MaterialMovement.objects
            .filter(company=company, movement_type="ف بيع", movement_date__gte=period_from)
            .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
            .annotate(month=TruncMonth("movement_date"))
            .values("customer_name", "month")
            .annotate(monthly_revenue=Sum("total_out"))
            .order_by("customer_name", "month")
        )

        monthly_map: dict[str, list[float]] = {}
        for row in monthly_by_customer:
            monthly_map.setdefault(row["customer_name"], []).append(
                float(row["monthly_revenue"] or 0)
            )

        latest_snap      = (AgingSnapshot.objects.filter(company=company)
                            .order_by("-uploaded_at").first())
        aging_by_account : dict[str, dict] = {}
        if latest_snap:
            for rec in AgingReceivable.objects.filter(snapshot=latest_snap):
                key = rec.account_code or rec.account
                aging_by_account[key] = {
                    "risk_score":    rec.risk_score,
                    "overdue_ratio": float(rec.overdue_total / rec.total)
                                     if float(rec.total) > 0 else 0.0,
                    "total_lyd":     float(rec.total),
                    "overdue_lyd":   float(rec.overdue_total),
                }

        customer_by_name = {
            c.name: c for c in Customer.objects.filter(company=company)
        }

        features: list[dict] = []
        for row in sales_per_customer:
            if row["purchase_count"] < MIN_PURCHASES:
                continue
            cname      = row["customer_name"]
            last_date  = row["last_purchase"]
            total_rev  = float(row["total_revenue"] or 0)
            n_pur      = row["purchase_count"]
            days_since = (today - last_date).days if last_date else 999

            monthly_vals    = monthly_map.get(cname, [])
            avg_monthly_rev = sum(monthly_vals) / len(monthly_vals) if monthly_vals else 0.0
            avg_order_val   = total_rev / n_pur if n_pur > 0 else 0.0
            trend           = self._compute_trend(monthly_vals)

            customer_obj = customer_by_name.get(cname)
            account_code = customer_obj.account_code if customer_obj else ""
            aging        = aging_by_account.get(account_code, {})

            features.append({
                "customer_name":            cname,
                "customer_id":              str(customer_obj.id) if customer_obj else None,
                "account_code":             account_code,
                "days_since_last_purchase": days_since,
                "purchase_count_12m":       n_pur,
                "avg_monthly_revenue":      avg_monthly_rev,
                "avg_order_value":          avg_order_val,
                "revenue_trend":            trend,
                "aging_risk_score":         aging.get("risk_score", "unknown"),
                "overdue_ratio":            aging.get("overdue_ratio", 0.0),
                "overdue_lyd":              aging.get("overdue_lyd", 0.0),
                "total_receivable_lyd":     aging.get("total_lyd", 0.0),
            })

        logger.info("[ChurnPredictor] Feature computation complete: %d customers", len(features))
        return features

    @staticmethod
    def _compute_trend(monthly_vals: list[float]) -> float:
        if len(monthly_vals) < 6:
            return 1.0
        recent = sum(monthly_vals[-3:])
        prior  = sum(monthly_vals[-6:-3])
        if prior == 0:
            return 1.0 if recent == 0 else 2.0
        return round(recent / prior, 4)

    # ── Rule-based scoring ────────────────────────────────────────────────────

    def _rule_based_score(self, f: dict) -> dict:
        score = 0.0
        days  = f["days_since_last_purchase"]
        trend = f["revenue_trend"]
        risk  = f["aging_risk_score"]
        over  = f["overdue_ratio"]

        if days >= RECENCY_CRITICAL_DAYS: score += 0.40
        elif days >= RECENCY_HIGH_DAYS:   score += 0.28
        elif days >= RECENCY_MEDIUM_DAYS: score += 0.14

        if trend < 0.50:   score += 0.25
        elif trend < 0.70: score += 0.18
        elif trend < 0.85: score += 0.10
        elif trend < 0.95: score += 0.04

        score += {"critical": 0.25, "high": 0.18, "medium": 0.08,
                  "low": 0.00, "unknown": 0.05}.get(risk, 0.05)

        if over >= 0.75:   score += 0.10
        elif over >= 0.50: score += 0.06
        elif over >= 0.25: score += 0.02

        score = min(1.0, round(score, 4))
        label = ("critical" if score >= 0.75 else "high" if score >= 0.50
                 else "medium" if score >= 0.25 else "low")
        return {**f, "churn_score": score, "pre_label": label}

    # ── AI call ───────────────────────────────────────────────────────────────

    def _call_ai(self, f: dict, company_id, rank: int) -> dict | None:
        days     = f["days_since_last_purchase"]
        trend    = f["revenue_trend"]
        risk     = f["aging_risk_score"]
        over     = f["overdue_ratio"]
        over_lyd = f.get("overdue_lyd", 0.0)
        total    = f["total_receivable_lyd"]
        avg_rev  = f["avg_monthly_revenue"]
        score    = f["churn_score"]
        label    = f["pre_label"]

        signals = []
        if days >= RECENCY_CRITICAL_DAYS:
            signals.append(f"INACTIVE {days} DAYS (threshold: 90d)")
        if trend < 0.75:
            signals.append(f"REVENUE DECLINED {int((1-trend)*100)}% last quarter")
        if risk in ("critical", "high"):
            signals.append(f"PAYMENT {risk.upper()}: {int(over*100)}% of {total:,.0f} LYD overdue")
        dominant = signals[0] if signals else "multiple moderate signals"

        user_prompt = f"""Customer #{rank:03d} (anonymized) — B2B distribution, Libya

=== BEHAVIORAL METRICS ===
Days since last purchase: {days}d {"(CRITICAL >90d)" if days >= 90 else "(HIGH >60d)" if days >= 60 else ""}
Orders in 12 months: {f['purchase_count_12m']}
Avg monthly revenue: {avg_rev:,.2f} LYD
Avg order value: {f['avg_order_value']:,.2f} LYD

=== REVENUE TREND ===
Ratio last3m/prior3m: {trend:.4f} → {"DECLINING -{:.0f}%".format((1-trend)*100) if trend < 1 else "STABLE" if trend == 1 else "GROWING +{:.0f}%".format((trend-1)*100)}

=== PAYMENT & CREDIT ===
Aging risk: {risk}
Overdue: {over_lyd:,.2f} LYD ({int(over*100)}% of {total:,.2f} LYD)

=== PRE-ASSESSMENT ===
Score: {score:.4f} ({int(score*100)}%) — {label}
Dominant signal: {dominant}

Your actions must directly address: {dominant}"""

        return self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model="smart",
            max_tokens=600,
            analyzer="churn_predictor",
            company_id=str(company_id),
        )

    # ── Output formatting ─────────────────────────────────────────────────────

    def _format_result(self, f: dict, ai_result: dict | None, ai_called: bool = False) -> dict:
        churn_score = f["churn_score"]
        churn_label = f["pre_label"]

        if ai_result and not ai_result.get("error"):
            churn_score         = float(ai_result.get("refined_churn_score", churn_score))
            churn_label         = ai_result.get("churn_label", churn_label)
            ai_explanation      = ai_result.get("ai_explanation", "")
            recommended_actions = ai_result.get("recommended_actions", [])
            key_risk_factors    = ai_result.get("key_risk_factors", [])
            # AI was called and succeeded
            confidence          = ai_result.get("confidence", "medium")
        else:
            ai_explanation      = self._default_explanation(f)
            recommended_actions = self._default_actions(f)
            key_risk_factors    = self._default_risk_factors(f)
            # Confidence logic:
            #   "medium" → AI not called (low-risk customer, rule-based score is reliable)
            #   "low"    → AI was called but failed (rate limit or error)
            confidence = "low" if ai_called else "medium"

        # Derive aging_risk_score from overdue_ratio if missing
        aging_risk = f["aging_risk_score"]
        if aging_risk == "unknown":
            over  = f["overdue_ratio"]
            total = f["total_receivable_lyd"]
            if total == 0:           aging_risk = "low"
            elif over >= 0.75:       aging_risk = "critical"
            elif over >= 0.50:       aging_risk = "high"
            elif over >= 0.20:       aging_risk = "medium"
            else:                    aging_risk = "low"

        return {
            "customer_id":              f["customer_id"],
            "account_code":             f["account_code"],
            "customer_name":            f.get("customer_name", ""),  # display only
            "churn_score":              round(min(1.0, max(0.0, churn_score)), 4),
            "churn_label":              churn_label,
            "days_since_last_purchase": f["days_since_last_purchase"],
            "purchase_count_12m":       f["purchase_count_12m"],
            "avg_monthly_revenue_lyd":  round(f["avg_monthly_revenue"], 2),
            "avg_order_value_lyd":      round(f["avg_order_value"], 2),
            "revenue_trend":            f["revenue_trend"],
            "aging_risk_score":         aging_risk,
            "overdue_ratio":            round(f["overdue_ratio"], 4),
            "total_receivable_lyd":     round(f["total_receivable_lyd"], 2),
            "ai_explanation":           ai_explanation,
            "recommended_actions":      recommended_actions,
            "key_risk_factors":         key_risk_factors,
            "confidence":               confidence,
        }

    # ── Personalized fallbacks (real numbers, not generic text) ──────────────

    @staticmethod
    def _default_explanation(f: dict) -> str:
        parts = []
        days  = f["days_since_last_purchase"]
        trend = f["revenue_trend"]
        risk  = f["aging_risk_score"]
        over  = f["overdue_ratio"]
        rev   = f["avg_monthly_revenue"]

        if days >= RECENCY_CRITICAL_DAYS:
            parts.append(
                f"No purchase in {days} days — critical inactivity for an account "
                f"averaging {rev:,.0f} LYD/month."
            )
        elif days >= RECENCY_HIGH_DAYS:
            parts.append(f"Last order was {days} days ago, below expected frequency.")

        if trend < 0.75:
            parts.append(
                f"Revenue declined approximately {int((1-trend)*100)}% "
                f"compared to the prior quarter."
            )
        if risk in ("high", "critical"):
            parts.append(
                f"Payment behavior classified '{risk}' "
                f"with {int(over*100)}% of receivables overdue."
            )
        return " ".join(parts) or "Account shows a combination of behavioral churn signals."

    @staticmethod
    def _default_actions(f: dict) -> list[str]:
        actions  = []
        days     = f["days_since_last_purchase"]
        over     = f["overdue_ratio"]
        trend    = f["revenue_trend"]
        rev      = f["avg_monthly_revenue"]
        over_lyd = f.get("overdue_lyd", 0.0)
        total    = f["total_receivable_lyd"]

        if days >= RECENCY_HIGH_DAYS:
            actions.append(
                f"Schedule an executive outreach call within 48 hours — this account "
                f"has been inactive {days} days despite averaging {rev:,.0f} LYD/month."
            )
        if over > 0.50 and total > 0:
            actions.append(
                f"Finance to propose a structured repayment plan for the "
                f"{over_lyd:,.0f} LYD overdue ({int(over*100)}% of {total:,.0f} LYD outstanding)."
            )
        if trend < 0.75:
            actions.append(
                f"Prepare a commercial offer addressing the "
                f"{int((1-trend)*100)}% revenue decline — likely competitive pricing pressure."
            )
        actions.append("Flag for weekly monitoring and document all engagement attempts in CRM.")
        return actions[:4]

    @staticmethod
    def _default_risk_factors(f: dict) -> list[str]:
        factors = []
        if f["days_since_last_purchase"] >= RECENCY_CRITICAL_DAYS:
            factors.append(f"Inactive {f['days_since_last_purchase']}d (threshold: 90d)")
        if f["revenue_trend"] < 0.80:
            factors.append(f"Revenue −{int((1-f['revenue_trend'])*100)}% last quarter")
        if f["aging_risk_score"] in ("high", "critical"):
            factors.append(
                f"Payment risk: {f['aging_risk_score']} "
                f"({int(f['overdue_ratio']*100)}% overdue)"
            )
        if f["overdue_ratio"] > 0.50:
            factors.append(f"High overdue ratio: {int(f['overdue_ratio']*100)}%")
        return factors