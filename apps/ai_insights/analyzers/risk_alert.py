"""
apps/ai_insights/analyzers/risk_alert.py
-----------------------------------------
SCRUM-29 — Risk Alert Analyzer v2.0

Generates a detailed AI explanation for a single alert.
Smart English fallback using real data when AI is unavailable.
"""

import logging

from apps.ai_insights.client import AIClient, AIClientError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior financial analyst for WEEG, a BI platform for Libyan businesses.

Context:
- Currency: LYD (Libyan Dinar)
- Aging buckets: Current, 1-30d, 31-60d, 61-90d, 91-120d, 121-150d, 151-180d, 181-210d, 211-240d, 241-270d, 271-300d, 301-330d, +330d
- Risk levels: low (<20% overdue), medium (20-50%), high (50-75%), critical (>75%)

Task: Analyze ONE alert and return a concise, actionable analysis in English.

Rules:
1. Always cite exact figures — NEVER invent data.
2. Actions must be executable TODAY by a credit manager.
3. Be direct. No generic advice.

Return ONLY valid JSON — no markdown, no preamble:
{
  "summary": "<one sentence: what is happening and why it matters>",
  "root_cause": "<why this alert was triggered with exact figures>",
  "urgency_reason": "<why action is needed now>",
  "recommended_actions": ["<action 1>", "<action 2>", "<action 3>"],
  "risk_level_justification": "<why this severity level>",
  "confidence": "high" | "medium" | "low"
}"""


class RiskAlertAnalyzer:

    def __init__(self):
        self._client = AIClient()

    def explain(self, alert_data: dict, company_id: str = None) -> dict:
        user_prompt = self._build_user_prompt(alert_data)
        try:
            result = self._client.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model="smart",
                max_tokens=800,
                analyzer="risk_alert",
                company_id=company_id,
            )
            if result.get("error"):
                logger.warning("[RiskAlertAnalyzer] AI returned error: %s", result)
                return self._fallback(alert_data)
            return self._validate(result)
        except AIClientError as exc:
            logger.warning("[RiskAlertAnalyzer] AI unavailable: %s", exc)
            return self._fallback(alert_data)

    def _build_user_prompt(self, alert_data: dict) -> str:
        alert_type = alert_data.get("type", "unknown")
        severity   = alert_data.get("severity", "medium")
        message    = alert_data.get("message", "")
        detail     = alert_data.get("detail", "")
        meta       = alert_data.get("metadata", {})

        lines = [
            f"Alert type: {alert_type}",
            f"Severity: {severity}",
            f"Message: {message}",
            f"Detail: {detail}",
            "",
            "Financial data (anonymized):",
        ]

        if alert_type in ("overdue", "risk", "high_receivables"):
            lines += self._format_aging_data(meta)
        elif alert_type == "low_stock":
            lines += self._format_stock_data(meta)
        elif alert_type == "sales_drop":
            lines += self._format_sales_drop_data(meta)
        elif alert_type == "dso":
            lines += [
                f"  dso_days:       {meta.get('dso', 0)}",
                f"  target_days:    {meta.get('target', 60)}",
                f"  total_overdue:  {float(meta.get('totalOverdue', 0)):,.2f} LYD",
            ]
        elif alert_type == "concentration":
            lines += [
                f"  top3_pct:       {float(meta.get('top3Pct', 0)):.1f}%",
                f"  top3_total:     {float(meta.get('top3Total', 0)):,.2f} LYD",
                f"  grand_total:    {float(meta.get('grandTotal', 0)):,.2f} LYD",
                f"  top3_names:     {meta.get('top3Names', 'N/A')}",
            ]
        else:
            lines.append(f"  data: {str(meta)[:300]}")

        return "\n".join(lines)

    @staticmethod
    def _format_aging_data(meta: dict) -> list[str]:
        over_180 = sum(float(meta.get(f, 0)) for f in
                       ["d181_210","d211_240","d241_270","d271_300","d301_330","over_330"])
        total    = float(meta.get("total", 0))
        overdue  = float(meta.get("overdue_total", 0))
        pct      = (overdue / total * 100) if total > 0 else 0
        return [
            f"  total_receivable_lyd:  {total:,.2f}",
            f"  total_overdue_lyd:     {overdue:,.2f}  ({pct:.1f}% of total)",
            f"  current_lyd:           {float(meta.get('current', 0)):,.2f}",
            f"  1_30d_lyd:             {float(meta.get('d1_30', 0)):,.2f}",
            f"  31_60d_lyd:            {float(meta.get('d31_60', 0)):,.2f}",
            f"  61_90d_lyd:            {float(meta.get('d61_90', 0)):,.2f}",
            f"  91_120d_lyd:           {float(meta.get('d91_120', 0)):,.2f}",
            f"  121_180d_lyd:          {float(meta.get('d121_150', 0)) + float(meta.get('d151_180', 0)):,.2f}",
            f"  over_180d_lyd:         {over_180:,.2f}",
            f"  risk_classification:   {meta.get('risk_score', 'unknown')}",
        ]

    @staticmethod
    def _format_stock_data(meta: dict) -> list[str]:
        return [
            f"  category:    {meta.get('product_category', 'N/A')}",
            f"  quantity:    {float(meta.get('total_qty', 0)):.0f} units",
            f"  value_lyd:   {float(meta.get('total_value', 0)):,.2f}",
        ]

    @staticmethod
    def _format_sales_drop_data(meta: dict) -> list[str]:
        prev = meta.get("prev", {})
        curr = meta.get("curr", {})
        pct  = meta.get("pctChange", 0)
        return [
            f"  previous_month:        {prev.get('month_label', '?')}",
            f"  previous_sales_lyd:    {float(prev.get('total_sales', 0)):,.2f}",
            f"  current_month:         {curr.get('month_label', '?')}",
            f"  current_sales_lyd:     {float(curr.get('total_sales', 0)):,.2f}",
            f"  change_pct:            {float(pct):.1f}%",
        ]

    @staticmethod
    def _validate(result: dict) -> dict:
        return {
            "summary":                  result.get("summary", "Analysis unavailable."),
            "root_cause":               result.get("root_cause", ""),
            "urgency_reason":           result.get("urgency_reason", ""),
            "recommended_actions":      result.get("recommended_actions", []),
            "risk_level_justification": result.get("risk_level_justification", ""),
            "confidence":               result.get("confidence", "low"),
        }

    def _fallback(self, alert_data: dict) -> dict:
        """
        Smart English rule-based fallback using real alert data.
        Used when AI is unavailable — returns actionable content, not generic text.
        """
        alert_type = alert_data.get("type", "unknown")
        severity   = alert_data.get("severity", "medium")
        message    = alert_data.get("message", "")
        detail     = alert_data.get("detail", "")
        meta       = alert_data.get("metadata", {})

        if alert_type in ("overdue", "risk", "high_receivables"):
            total    = float(meta.get("total", 0))
            overdue  = float(meta.get("overdue_total", 0))
            risk     = meta.get("risk_score", severity)
            pct      = (overdue / total * 100) if total > 0 else 0
            over_180 = sum(float(meta.get(f, 0)) for f in
                           ["d181_210","d211_240","d241_270","d271_300","d301_330","over_330"])
            return {
                "summary": (
                    f"This account has {overdue:,.0f} LYD overdue out of "
                    f"{total:,.0f} LYD total receivable ({pct:.0f}%) — risk classified as '{risk}'."
                ),
                "root_cause": (
                    f"{overdue:,.0f} LYD ({pct:.0f}% of outstanding) has exceeded its due date."
                    + (f" Of which {over_180:,.0f} LYD has been overdue for more than 6 months." if over_180 > 0 else "")
                ),
                "urgency_reason": (
                    f"An unpaid balance of {overdue:,.0f} LYD increases the risk of "
                    f"irrecoverability with each week of inaction."
                ),
                "recommended_actions": [
                    f"Contact the client to negotiate a structured repayment plan for the {overdue:,.0f} LYD outstanding balance.",
                    "Suspend all new deliveries until the overdue balance is significantly reduced.",
                    "Escalate to the finance director if no written commitment is received within 48 hours.",
                    "Document all communications in the CRM for audit trail purposes.",
                ],
                "risk_level_justification": (
                    f"Severity '{severity}': {pct:.0f}% of the outstanding balance "
                    f"({overdue:,.0f} / {total:,.0f} LYD) is overdue."
                ),
                "confidence":      "medium",
                "_ai_unavailable": True,
            }

        elif alert_type == "dso":
            dso    = int(meta.get("dso", 0))
            total  = float(meta.get("totalOverdue", 0))
            return {
                "summary": (
                    f"The company's DSO stands at {dso} days — significantly above the 60-day target. "
                    f"Total overdue portfolio: {total:,.0f} LYD."
                ),
                "root_cause": (
                    f"The weighted average collection period across all customers is {dso} days, "
                    f"meaning invoices take {dso} days on average to be paid."
                ),
                "urgency_reason": (
                    f"Every day the DSO exceeds the target increases cash flow pressure. "
                    f"At {dso} days, the company is carrying {dso - 60} extra days of financing risk."
                ),
                "recommended_actions": [
                    "Identify the top 5 customers with the longest outstanding balances and prioritize collection calls.",
                    "Review payment terms — consider tightening credit limits for customers with chronic delays.",
                    "Set a 30-day target to reduce DSO to below 75 days through accelerated collections.",
                    "Introduce early payment incentives (small discounts) to encourage faster settlement.",
                ],
                "risk_level_justification": (
                    f"DSO of {dso} days exceeds the 60-day threshold. "
                    + ("Classified critical — collection cycle is severely extended." if dso > 90
                       else "Classified medium — collection cycle needs attention.")
                ),
                "confidence":      "medium",
                "_ai_unavailable": True,
            }

        elif alert_type == "concentration":
            top3_pct   = float(meta.get("top3Pct", 0))
            top3_total = float(meta.get("top3Total", 0))
            grand      = float(meta.get("grandTotal", 0))
            names      = meta.get("top3Names", "top 3 clients")
            return {
                "summary": (
                    f"Top 3 clients ({names}) account for {top3_pct:.0f}% of total receivables "
                    f"({top3_total:,.0f} LYD of {grand:,.0f} LYD) — dangerously high concentration."
                ),
                "root_cause": (
                    f"Revenue and receivables are overly concentrated in 3 accounts. "
                    f"If any one of them delays payment or churns, cash flow is immediately impacted."
                ),
                "urgency_reason": (
                    f"A {top3_pct:.0f}% concentration means the loss of a single client "
                    f"could remove up to {top3_total / 3:,.0f} LYD from the receivables portfolio overnight."
                ),
                "recommended_actions": [
                    "Develop a diversification strategy — actively onboard new clients to reduce dependency.",
                    f"Negotiate payment security (advance payments or bank guarantees) with the top 3 accounts.",
                    "Set a 6-month target to reduce top-3 concentration below 40% of total receivables.",
                    "Alert the finance director and board about this structural risk.",
                ],
                "risk_level_justification": (
                    f"Concentration at {top3_pct:.0f}% exceeds the 50% critical threshold. "
                    + ("Classified critical — extreme dependency." if top3_pct > 70
                       else "Classified medium — requires active diversification.")
                ),
                "confidence":      "medium",
                "_ai_unavailable": True,
            }

        elif alert_type == "low_stock":
            qty = float(meta.get("total_qty", 0))
            val = float(meta.get("total_value", 0))
            cat = meta.get("product_category", "")
            return {
                "summary": (
                    f"Critical stock shortage{' — ' + cat if cat else ''}: "
                    f"{qty:.0f} units remaining (residual value: {val:,.0f} LYD)."
                ),
                "root_cause": (
                    f"Stock has dropped to {qty:.0f} units across all branches, "
                    f"with a residual value of {val:,.0f} LYD."
                ),
                "urgency_reason": (
                    "Every day of stock-out generates lost sales "
                    "and risks pushing customers toward competitors."
                ),
                "recommended_actions": [
                    "Place an urgent reorder with the supplier immediately.",
                    "Identify blocked customer orders and notify them of expected restocking dates.",
                    "Check for possible inter-branch stock transfers to cover critical demand.",
                ],
                "risk_level_justification": f"Stock at {qty:.0f} units — critical threshold reached.",
                "confidence":      "medium",
                "_ai_unavailable": True,
            }

        elif alert_type == "sales_drop":
            prev       = meta.get("prev", {})
            curr       = meta.get("curr", {})
            pct        = float(meta.get("pctChange", 0))
            prev_sales = float(prev.get("total_sales", 0))
            curr_sales = float(curr.get("total_sales", 0))
            diff       = prev_sales - curr_sales
            return {
                "summary": (
                    f"Revenue declined {abs(pct):.1f}% between "
                    f"{prev.get('month_label','?')} and {curr.get('month_label','?')} "
                    f"— a loss of {diff:,.0f} LYD."
                ),
                "root_cause": (
                    f"{prev.get('month_label','?')}: {prev_sales:,.0f} LYD → "
                    f"{curr.get('month_label','?')}: {curr_sales:,.0f} LYD "
                    f"(−{diff:,.0f} LYD / −{abs(pct):.1f}%)."
                ),
                "urgency_reason": (
                    f"A {abs(pct):.1f}% revenue drop left unaddressed may signal "
                    "customer loss, undetected stock-out, or competitive pressure."
                ),
                "recommended_actions": [
                    "Analyze cancelled or delayed orders during this period.",
                    "Identify which products and customers account for most of the decline.",
                    "Meet with the sales team within 48 hours to understand root causes on the ground.",
                ],
                "risk_level_justification": (
                    f"Monthly revenue decline of {abs(pct):.1f}% — alert threshold (>15%) exceeded."
                ),
                "confidence":      "medium",
                "_ai_unavailable": True,
            }

        else:
            return {
                "summary":                  message,
                "root_cause":               detail,
                "urgency_reason":           "Immediate review is recommended.",
                "recommended_actions": [
                    "Manually review the relevant account or product.",
                    "Escalate to the appropriate department if the issue persists.",
                ],
                "risk_level_justification": f"Severity '{severity}' based on automatic threshold rules.",
                "confidence":               "medium",
                "_ai_unavailable":          True,
            }