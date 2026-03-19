"""
apps/ai_insights/analyzers/high_value_churn.py
------------------------------------------------
SCRUM-HVC — High-Value Customer Churn Detection

Detects customers with lifetime / 12-month revenue ≥ HIGH_VALUE_THRESHOLD_LYD
(default 50,000,000 LYD) who show churn risk signals, predicts likely outcomes
if no action is taken, and generates tailored retention recommendations.

Pipeline:
  1. Screen — filter customers whose avg_monthly_revenue × 12 ≥ threshold
  2. Feature engineering — reuse ChurnPredictor._compute_features()
  3. Rule-based risk scoring — immediate, no API cost
  4. Outcome prediction — GPT-4o: what happens if we do nothing?
  5. Retention playbook — GPT-4o: what should we do, and in what order?

Security:
  Customer names and account codes are NEVER sent to OpenAI.
  Each customer is referred to as "HVC-#N" in all prompts.

Output per at-risk high-value customer:
  {
    "customer_id":                str | null,
    "account_code":               str,
    "annual_revenue_lyd":         float,
    "monthly_revenue_lyd":        float,
    "churn_score":                float,          0.0–1.0
    "churn_label":                str,            low/medium/high/critical
    "days_since_last_purchase":   int,
    "revenue_trend":              float,
    "aging_risk_score":           str,
    "overdue_ratio":              float,
    "total_receivable_lyd":       float,

    # AI outputs
    "risk_summary":               str,            2-3 sentence diagnosis
    "predicted_outcomes":         list[dict],     [{scenario, probability, revenue_impact_lyd}]
    "retention_playbook":         list[dict],     [{priority, action, owner, deadline_days}]
    "early_warning_signals":      list[str],
    "confidence":                 str,
    "estimated_revenue_at_risk":  float,
  }

Prompt version: v1.0
"""

import logging
from datetime import date, timedelta

from django.db.models import Count, Max, Sum, Q
from django.db.models.functions import TruncMonth

from apps.ai_insights.client import AIClient, AIClientError

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

HIGH_VALUE_THRESHOLD_LYD  = 50_000_000   # Annual revenue threshold
ANALYSIS_WINDOW_DAYS      = 365
MIN_PURCHASES             = 3
RECENCY_CRITICAL_DAYS     = 90
RECENCY_HIGH_DAYS         = 60
RECENCY_MEDIUM_DAYS       = 30

# ── System prompts ────────────────────────────────────────────────────────────

OUTCOME_SYSTEM_PROMPT = """You are a senior B2B revenue retention analyst for a Libyan \
distribution company using WEEG BI platform.

You are given anonymized behavioral data for ONE high-value customer \
(annual revenue ≥ 50,000,000 LYD). Your job: predict what will happen \
if the company takes NO retention action over the next 90 days.

Rules:
  1. Reference the exact numbers in your prediction.
  2. Be direct and quantitative — estimate revenue impact in LYD.
  3. Scenarios must be mutually exclusive and cover the realistic probability space.
  4. Currency is LYD (Libyan Dinar).

Return ONLY valid JSON — no markdown, no preamble:
{
  "risk_summary": "<2-3 sentences: what the data reveals about this customer right now>",
  "early_warning_signals": ["<signal 1>", "<signal 2>", "<signal 3>"],
  "predicted_outcomes": [
    {
      "scenario":            "<scenario name, e.g. 'Full Churn'>",
      "probability":         <float 0.0–1.0>,
      "description":         "<what happens in this scenario>",
      "revenue_impact_lyd":  <negative float — revenue lost over 12 months>,
      "time_to_materialize": "<e.g. '30–60 days'>"
    }
  ],
  "estimated_revenue_at_risk": <float — probability-weighted revenue loss>,
  "confidence": "high" | "medium" | "low"
}"""


PLAYBOOK_SYSTEM_PROMPT = """You are a senior B2B customer success manager for a Libyan \
distribution company using WEEG BI platform.

You are given anonymized behavioral data for ONE high-value customer \
(annual revenue ≥ 50,000,000 LYD) who is at risk of churn.

Your job: create a concrete, prioritized retention playbook that a sales or \
account manager can execute starting TODAY.

Rules:
  1. Actions must be executable immediately — no vague advice.
  2. Assign each action an owner role (e.g. Account Manager, Finance, Director).
  3. Order by urgency (priority 1 = most urgent).
  4. Deadline is in calendar days from today.
  5. Currency is LYD.

Return ONLY valid JSON — no markdown, no preamble:
{
  "retention_playbook": [
    {
      "priority":      <int 1–5>,
      "action":        "<specific action to take>",
      "rationale":     "<why this action addresses the risk>",
      "owner":         "<role responsible>",
      "deadline_days": <int — days from today to complete>,
      "success_metric": "<how to measure if it worked>"
    }
  ]
}"""


class HighValueChurnDetector:
    """
    Detects high-value customers at churn risk and generates outcome
    predictions + retention playbooks using GPT-4o.

    Usage:
        detector = HighValueChurnDetector()
        results  = detector.detect(
            company,
            threshold_lyd=50_000_000,
            top_n=10,
            use_ai=True,
        )
    """

    def __init__(self):
        self._client = AIClient()

    # ── Public ────────────────────────────────────────────────────────────────

    def detect(
        self,
        company,
        threshold_lyd: float = HIGH_VALUE_THRESHOLD_LYD,
        top_n: int = 10,
        use_ai: bool = True,
    ) -> dict:
        """
        Identify high-value customers at churn risk.

        Returns:
            {
                "threshold_lyd":        float,
                "total_hv_customers":   int,
                "at_risk_count":        int,
                "total_revenue_at_risk":float,
                "customers":            list[dict],
            }
        """
        logger.info(
            "[HighValueChurnDetector] Starting for company=%s threshold=%s",
            company.id, threshold_lyd,
        )

        all_features = self._compute_features(company)

        # Filter to high-value customers
        hv_features = [
            f for f in all_features
            if (f["avg_monthly_revenue"] * 12) >= threshold_lyd
        ]

        logger.info(
            "[HighValueChurnDetector] %d total customers, %d high-value (≥%s LYD/yr)",
            len(all_features), len(hv_features), threshold_lyd,
        )

        # Rule-based pre-score all HV customers
        scored = [self._rule_based_score(f) for f in hv_features]

        # Filter: only customers with medium/high/critical churn risk
        at_risk = [s for s in scored if s["pre_label"] in ("medium", "high", "critical")]
        at_risk.sort(key=lambda x: -x["churn_score"])
        at_risk = at_risk[:top_n]

        # Limit AI calls to top 3 accounts to stay within rate limits.
        # Lower-ranked accounts use rule-based fallback (still personalized).
        import time as _time
        HV_AI_LIMIT = 3
        results = []
        for rank, customer_data in enumerate(at_risk, start=1):
            if use_ai and rank <= HV_AI_LIMIT:
                if rank > 1:
                    _time.sleep(5)   # pause between accounts
                outcome_ai  = self._call_outcome_ai(customer_data, company.id, rank)
                _time.sleep(3)
                playbook_ai = self._call_playbook_ai(customer_data, company.id, rank)
            else:
                outcome_ai  = None
                playbook_ai = None

            results.append(self._format_result(customer_data, outcome_ai, playbook_ai))

        total_at_risk_revenue = sum(
            r.get("estimated_revenue_at_risk", 0) for r in results
        )

        logger.info(
            "[HighValueChurnDetector] Done: %d at-risk HV customers, "
            "%.0f LYD total revenue at risk for company=%s",
            len(results), total_at_risk_revenue, company.id,
        )

        return {
            "threshold_lyd":         threshold_lyd,
            "total_hv_customers":    len(hv_features),
            "at_risk_count":         len(results),
            "total_revenue_at_risk": round(total_at_risk_revenue, 2),
            "customers":             results,
        }

    # ── Feature engineering ───────────────────────────────────────────────────
    # Mirrors ChurnPredictor._compute_features() — kept here for independence.

    def _compute_features(self, company) -> list[dict]:
        from apps.transactions.models import MaterialMovement
        from apps.aging.models import AgingReceivable, AgingSnapshot
        from apps.customers.models import Customer

        today       = date.today()
        period_from = today - timedelta(days=ANALYSIS_WINDOW_DAYS)

        sales_per_customer = (
            MaterialMovement.objects
            .filter(
                company=company,
                movement_type="ف بيع",
                movement_date__gte=period_from,
            )
            .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
            .values("customer_name")
            .annotate(
                purchase_count=Count("id"),
                last_purchase=Max("movement_date"),
                total_revenue=Sum("total_out"),
            )
        )

        monthly_by_customer = (
            MaterialMovement.objects
            .filter(
                company=company,
                movement_type="ف بيع",
                movement_date__gte=period_from,
            )
            .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
            .annotate(month=TruncMonth("movement_date"))
            .values("customer_name", "month")
            .annotate(monthly_revenue=Sum("total_out"))
            .order_by("customer_name", "month")
        )

        monthly_map: dict[str, list[float]] = {}
        for row in monthly_by_customer:
            cname = row["customer_name"]
            monthly_map.setdefault(cname, []).append(
                float(row["monthly_revenue"] or 0)
            )

        latest_snap = (
            AgingSnapshot.objects
            .filter(company=company)
            .order_by("-uploaded_at")
            .first()
        )
        aging_by_account: dict[str, dict] = {}
        if latest_snap:
            for rec in AgingReceivable.objects.filter(snapshot=latest_snap):
                key = rec.account_code or rec.account
                aging_by_account[key] = {
                    "risk_score":    rec.risk_score,
                    "overdue_ratio": (
                        float(rec.overdue_total / rec.total)
                        if float(rec.total) > 0 else 0.0
                    ),
                    "total_lyd": float(rec.total),
                }

        customer_by_name: dict[str, Customer] = {
            c.name: c
            for c in Customer.objects.filter(company=company)
        }

        features: list[dict] = []
        for row in sales_per_customer:
            if row["purchase_count"] < MIN_PURCHASES:
                continue

            cname        = row["customer_name"]
            last_date    = row["last_purchase"]
            total_rev    = float(row["total_revenue"] or 0)
            n_purchases  = row["purchase_count"]
            days_since   = (today - last_date).days if last_date else 999

            monthly_vals    = monthly_map.get(cname, [])
            avg_monthly_rev = sum(monthly_vals) / len(monthly_vals) if monthly_vals else 0.0
            avg_order_val   = total_rev / n_purchases if n_purchases > 0 else 0.0
            trend           = self._compute_trend(monthly_vals)

            customer_obj = customer_by_name.get(cname)
            account_code = customer_obj.account_code if customer_obj else ""
            aging        = aging_by_account.get(account_code, {})

            features.append({
                "customer_name":            cname,
                "customer_id":              str(customer_obj.id) if customer_obj else None,
                "account_code":             account_code,
                "days_since_last_purchase": days_since,
                "purchase_count_12m":       n_purchases,
                "avg_monthly_revenue":      avg_monthly_rev,
                "avg_order_value":          avg_order_val,
                "revenue_trend":            trend,
                "aging_risk_score":         aging.get("risk_score", "unknown"),
                "overdue_ratio":            aging.get("overdue_ratio", 0.0),
                "total_receivable_lyd":     aging.get("total_lyd", 0.0),
            })

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
        """
        Identical weight breakdown to ChurnPredictor:
          Recency      → 0.40
          Trend        → 0.25
          Credit risk  → 0.25
          Overdue      → 0.10
        """
        score = 0.0
        days  = f["days_since_last_purchase"]
        trend = f["revenue_trend"]
        risk  = f["aging_risk_score"]
        over  = f["overdue_ratio"]

        if days >= RECENCY_CRITICAL_DAYS:
            score += 0.40
        elif days >= RECENCY_HIGH_DAYS:
            score += 0.28
        elif days >= RECENCY_MEDIUM_DAYS:
            score += 0.14

        if trend < 0.50:
            score += 0.25
        elif trend < 0.70:
            score += 0.18
        elif trend < 0.85:
            score += 0.10
        elif trend < 0.95:
            score += 0.04

        credit_map = {
            "critical": 0.25, "high": 0.18,
            "medium":   0.08, "low":  0.00, "unknown": 0.05,
        }
        score += credit_map.get(risk, 0.05)

        if over >= 0.75:
            score += 0.10
        elif over >= 0.50:
            score += 0.06
        elif over >= 0.25:
            score += 0.02

        score = min(1.0, round(score, 4))

        if score >= 0.75:
            label = "critical"
        elif score >= 0.50:
            label = "high"
        elif score >= 0.25:
            label = "medium"
        else:
            label = "low"

        return {**f, "churn_score": score, "pre_label": label}

    # ── AI calls ──────────────────────────────────────────────────────────────

    def _build_customer_prompt(self, f: dict, rank: int) -> str:
        annual_rev = f["avg_monthly_revenue"] * 12
        return f"""Customer: HVC-{rank:03d} (anonymized — high-value B2B account)
Annual revenue (LYD):          {annual_rev:,.0f}
Monthly avg revenue (LYD):     {f['avg_monthly_revenue']:,.2f}

--- Purchase Behavior ---
Days since last purchase:      {f['days_since_last_purchase']}
Purchase count (12 months):    {f['purchase_count_12m']}
Avg order value (LYD):         {f['avg_order_value']:,.2f}
Revenue trend ratio:           {f['revenue_trend']:.4f}
  (1.0=stable | <1.0=declining | >1.0=growing)
  (last 3 months / prior 3 months)

--- Credit & Payment ---
Aging risk score:              {f['aging_risk_score']}
  (low=<20% overdue | medium=20-50% | high=50-75% | critical=>75%)
Overdue ratio:                 {f['overdue_ratio']:.2%}
Total outstanding (LYD):       {f['total_receivable_lyd']:,.2f}

--- Rule-Based Pre-Assessment ---
Churn score:                   {f['churn_score']:.4f}
Churn label:                   {f['pre_label']}"""

    def _call_outcome_ai(self, f: dict, company_id, rank: int) -> dict | None:
        try:
            return self._client.complete(
                system_prompt=OUTCOME_SYSTEM_PROMPT,
                user_prompt=self._build_customer_prompt(f, rank),
                model="smart",
                max_tokens=700,
                analyzer="hv_churn_outcome",
                company_id=str(company_id),
            )
        except AIClientError as exc:
            logger.warning("[HighValueChurnDetector] Outcome AI failed rank=%d: %s", rank, exc)
            return None

    def _call_playbook_ai(self, f: dict, company_id, rank: int) -> dict | None:
        try:
            return self._client.complete(
                system_prompt=PLAYBOOK_SYSTEM_PROMPT,
                user_prompt=self._build_customer_prompt(f, rank),
                model="smart",
                max_tokens=700,
                analyzer="hv_churn_playbook",
                company_id=str(company_id),
            )
        except AIClientError as exc:
            logger.warning("[HighValueChurnDetector] Playbook AI failed rank=%d: %s", rank, exc)
            return None

    # ── Output formatting ─────────────────────────────────────────────────────

    def _format_result(
        self,
        f: dict,
        outcome_ai: dict | None,
        playbook_ai: dict | None,
    ) -> dict:
        annual_rev = round(f["avg_monthly_revenue"] * 12, 2)

        # Defaults (used when AI is unavailable)
        risk_summary           = self._default_risk_summary(f)
        early_warning_signals  = self._default_early_warnings(f)
        predicted_outcomes     = self._default_outcomes(f)
        retention_playbook     = self._default_playbook(f)
        estimated_at_risk      = round(annual_rev * f["churn_score"], 2)
        confidence             = "medium"

        if outcome_ai and not outcome_ai.get("error"):
            risk_summary          = outcome_ai.get("risk_summary", risk_summary)
            early_warning_signals = outcome_ai.get("early_warning_signals", early_warning_signals)
            predicted_outcomes    = outcome_ai.get("predicted_outcomes", predicted_outcomes)
            estimated_at_risk     = float(outcome_ai.get("estimated_revenue_at_risk", estimated_at_risk))
            confidence            = outcome_ai.get("confidence", "medium")

        if playbook_ai and not playbook_ai.get("error"):
            retention_playbook = playbook_ai.get("retention_playbook", retention_playbook)

        return {
            "customer_id":               f["customer_id"],
            "account_code":              f["account_code"],
            "customer_name":             f.get("customer_name", ""),  # display only — never sent to AI
            "annual_revenue_lyd":        annual_rev,
            "monthly_revenue_lyd":       round(f["avg_monthly_revenue"], 2),
            "churn_score":               round(min(1.0, max(0.0, f["churn_score"])), 4),
            "churn_label":               f["pre_label"],
            "days_since_last_purchase":  f["days_since_last_purchase"],
            "purchase_count_12m":        f["purchase_count_12m"],
            "avg_order_value_lyd":       round(f["avg_order_value"], 2),
            "revenue_trend":             f["revenue_trend"],
            "aging_risk_score":          f["aging_risk_score"],
            "overdue_ratio":             round(f["overdue_ratio"], 4),
            "total_receivable_lyd":      round(f["total_receivable_lyd"], 2),
            "risk_summary":              risk_summary,
            "early_warning_signals":     early_warning_signals,
            "predicted_outcomes":        predicted_outcomes,
            "retention_playbook":        retention_playbook,
            "estimated_revenue_at_risk": round(abs(estimated_at_risk), 2),
            "confidence":                confidence,
        }

    # ── Fallback generators (used when AI is unavailable) ─────────────────────

    @staticmethod
    def _default_risk_summary(f: dict) -> str:
        parts = []
        if f["days_since_last_purchase"] >= RECENCY_CRITICAL_DAYS:
            parts.append(
                f"This high-value customer has been inactive for "
                f"{f['days_since_last_purchase']} days — a critical churn signal."
            )
        if f["revenue_trend"] < 0.75:
            pct = int((1 - f["revenue_trend"]) * 100)
            parts.append(f"Revenue has declined ~{pct}% quarter-over-quarter.")
        if f["aging_risk_score"] in ("high", "critical"):
            parts.append(
                f"Payment behavior is rated '{f['aging_risk_score']}', "
                "suggesting financial stress or dissatisfaction."
            )
        return " ".join(parts) or "Customer shows multiple high-value churn indicators."

    @staticmethod
    def _default_early_warnings(f: dict) -> list[str]:
        warnings = []
        if f["days_since_last_purchase"] >= RECENCY_CRITICAL_DAYS:
            warnings.append(f"No purchase in {f['days_since_last_purchase']} days")
        if f["revenue_trend"] < 0.80:
            warnings.append("Quarterly revenue declining")
        if f["aging_risk_score"] in ("high", "critical"):
            warnings.append(f"Payment risk: {f['aging_risk_score']}")
        if f["overdue_ratio"] > 0.50:
            warnings.append(f"Overdue ratio at {f['overdue_ratio']:.0%}")
        return warnings or ["Churn score above threshold"]

    @staticmethod
    def _default_outcomes(f: dict) -> list[dict]:
        annual = f["avg_monthly_revenue"] * 12
        score  = f["churn_score"]
        return [
            {
                "scenario":            "Full Churn",
                "probability":         round(score * 0.6, 2),
                "description":         "Customer stops purchasing entirely within 90 days.",
                "revenue_impact_lyd":  -round(annual, 0),
                "time_to_materialize": "30–90 days",
            },
            {
                "scenario":            "Partial Reduction",
                "probability":         round(score * 0.3, 2),
                "description":         "Customer reduces orders by 50%, moves some volume to competitors.",
                "revenue_impact_lyd":  -round(annual * 0.5, 0),
                "time_to_materialize": "60–120 days",
            },
            {
                "scenario":            "Recovery",
                "probability":         round(max(0, 1 - score), 2),
                "description":         "Customer resumes normal purchasing pattern with intervention.",
                "revenue_impact_lyd":  0,
                "time_to_materialize": "N/A",
            },
        ]

    @staticmethod
    def _default_playbook(f: dict) -> list[dict]:
        actions = []
        if f["days_since_last_purchase"] >= RECENCY_HIGH_DAYS:
            actions.append({
                "priority":       1,
                "action":         "Schedule executive-level call within 48 hours to understand concerns.",
                "rationale":      "Inactivity at this revenue level requires immediate senior attention.",
                "owner":          "Account Director",
                "deadline_days":  2,
                "success_metric": "Call completed, next steps documented.",
            })
        if f["overdue_ratio"] > 0.40:
            actions.append({
                "priority":       2,
                "action":         "Finance team to propose a structured payment plan to reduce outstanding balance.",
                "rationale":      "High overdue ratio may be blocking new orders.",
                "owner":          "Finance Manager",
                "deadline_days":  5,
                "success_metric": "Payment arrangement agreed in writing.",
            })
        if f["revenue_trend"] < 0.75:
            actions.append({
                "priority":       3,
                "action":         "Prepare a tailored commercial proposal: volume discount or exclusive pricing.",
                "rationale":      "Revenue decline suggests competitor pricing pressure.",
                "owner":          "Sales Manager",
                "deadline_days":  7,
                "success_metric": "Proposal sent; customer confirms review.",
            })
        actions.append({
            "priority":       len(actions) + 1,
            "action":         "Add to weekly high-value at-risk monitoring dashboard.",
            "rationale":      "Continuous visibility prevents further slippage.",
            "owner":          "Sales Operations",
            "deadline_days":  1,
            "success_metric": "Account flagged and monitored weekly.",
        })
        return actions