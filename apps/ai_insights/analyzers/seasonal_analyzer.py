"""
apps/ai_insights/analyzers/seasonal_analyzer.py
-------------------------------------------------
SCRUM-26 v2.0 - STL decomposition + Ramadan/Eid detection
"""

import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, stdev

from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth, TruncDate

from apps.ai_insights.client import AIClient, AIClientError

logger = logging.getLogger(__name__)

HISTORY_MONTHS   = 24
MIN_MONTHS       = 6
PEAK_THRESHOLD   = 1.15
TROUGH_THRESHOLD = 0.85
MONTH_NAMES = {1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
               7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"}

# ── Ramadan dates (Gregorian start, approximate) ──────────────────────────────
# Ramadan moves ~11 days earlier each Gregorian year.
RAMADAN_STARTS = {
    2020: date(2020, 4, 23), 2021: date(2021, 4, 12), 2022: date(2022, 4,  2),
    2023: date(2023, 3, 22), 2024: date(2024, 3, 11), 2025: date(2025, 3,  1),
    2026: date(2026, 2, 18), 2027: date(2027, 2,  8),
}
RAMADAN_DURATION_DAYS = 30
EID_AL_FITR_DAYS      = 3   # 3 days after Ramadan ends
EID_AL_ADHA = {             # approximate
    2022: date(2022, 7, 9), 2023: date(2023, 6, 28), 2024: date(2024, 6, 16),
    2025: date(2025, 6,  6), 2026: date(2026, 5, 27),
}

SYSTEM_PROMPT = """You are a supply chain & demand planning expert for WEEG, a BI platform for Libyan distribution companies.

You receive monthly seasonality indices and Islamic calendar event flags.
Return ONLY valid JSON:
{
  "seasonal_narrative": "<3-4 sentences>",
  "peak_season_story":  "<what drives peak demand>",
  "trough_season_story": "<what causes trough>",
  "stock_preparation_calendar": [{"month": "<name>", "action": "<action>", "lead_time_weeks": <int>, "rationale": "<why>"}],
  "staffing_implications": "<quantified staffing impact>",
  "ai_recommendations": ["<rec 1>", "<rec 2>", "<rec 3>"],
  "confidence": "high" | "medium" | "low"
}"""


class SeasonalAnalyzer:

    def __init__(self):
        self._client = AIClient()

    def analyze(self, company, use_ai: bool = True) -> dict:
        logger.info("[SeasonalAnalyzer] Starting for company=%s", company.id)
        monthly_series = self._build_monthly_series(company)
        if len(monthly_series) < MIN_MONTHS:
            return self._empty_result("Insufficient historical data (minimum 6 months required).")

        # STL-inspired decomposition
        detrended      = self._remove_trend_stl(monthly_series)
        indices        = self._compute_seasonality_indices(detrended, monthly_series)
        trend          = self._compute_trend(monthly_series)
        peaks, troughs = self._classify_months(indices)
        ramadan_flags  = self._detect_ramadan_effect(company, monthly_series)
        category_pats  = self._compute_category_patterns(company)
        upcoming_alert = self._check_upcoming_peak(peaks)
        current_season = self._current_season_label(indices)

        ai_result = None
        if use_ai:
            try:
                ai_result = self._call_ai(indices, peaks, troughs, trend, ramadan_flags, company.id)
            except AIClientError as exc:
                logger.warning("[SeasonalAnalyzer] AI unavailable: %s", exc)

        return self._format_result(indices, trend, peaks, troughs, category_pats,
                                    upcoming_alert, current_season, ramadan_flags, ai_result)

    # ── Monthly series ────────────────────────────────────────────────────────

    def _build_monthly_series(self, company) -> list:
        from apps.transactions.models import MaterialMovement
        today      = date.today()
        start_date = today.replace(day=1) - timedelta(days=HISTORY_MONTHS * 30)
        rows = (
            MaterialMovement.objects
            .filter(company=company, movement_type="ف بيع", movement_date__gte=start_date)
            .exclude(Q(customer_name__isnull=True) | Q(customer_name=""))
            .annotate(month=TruncMonth("movement_date"))
            .values("month").annotate(revenue=Sum("total_out"))
            .order_by("month")
        )
        return [{"year": r["month"].year, "month": r["month"].month,
                 "revenue": float(r["revenue"] or 0)} for r in rows]

    # ── STL-inspired decomposition ────────────────────────────────────────────

    @staticmethod
    def _remove_trend_stl(series: list) -> list:
        """
        Simple trend removal using centered 12-month moving average (CMA).
        This isolates the seasonal + irregular component before computing SI.
        Robust to level shifts that distort simple multiplicative decomposition.
        """
        n       = len(series)
        window  = 12
        cma     = []
        for i in range(n):
            half = window // 2
            lo   = max(0, i - half)
            hi   = min(n, i + half + 1)
            vals = [p["revenue"] for p in series[lo:hi] if p["revenue"] > 0]
            cma.append(sum(vals) / len(vals) if vals else series[i]["revenue"])

        detrended = []
        for i, row in enumerate(series):
            trend_val = cma[i] if cma[i] > 0 else 1.0
            ratio     = row["revenue"] / trend_val if trend_val > 0 else 1.0
            detrended.append({**row, "detrended": ratio})
        return detrended

    @staticmethod
    def _compute_seasonality_indices(detrended: list, raw: list) -> dict:
        by_month: dict[int, list] = defaultdict(list)
        for row in detrended:
            if row["detrended"] > 0:
                by_month[row["month"]].append(row["detrended"])

        overall_avg = sum(r["detrended"] for r in detrended if r["detrended"] > 0)
        n_valid     = sum(1 for r in detrended if r["detrended"] > 0)
        overall_avg = overall_avg / n_valid if n_valid > 0 else 1.0

        raw_avg_by_month = defaultdict(list)
        for r in raw:
            raw_avg_by_month[r["month"]].append(r["revenue"])

        indices = {}
        for month_num in range(1, 13):
            vals = by_month.get(month_num, [])
            if vals:
                si = (sum(vals) / len(vals)) / overall_avg if overall_avg > 0 else 1.0
            else:
                si = None
            raw_vals   = raw_avg_by_month.get(month_num, [])
            month_avg  = sum(raw_vals) / len(raw_vals) if raw_vals else 0.0
            indices[month_num] = {
                "month_num": month_num, "month_name": MONTH_NAMES[month_num],
                "seasonality_index": round(si, 4) if si is not None else None,
                "avg_monthly_revenue_lyd": round(month_avg, 2),
                "data_points": len(vals),
                "label": (
                    "peak"    if si and si >= PEAK_THRESHOLD   else
                    "trough"  if si and si <= TROUGH_THRESHOLD else
                    "normal"  if si else "no_data"
                ),
            }
        return indices

    # ── Ramadan / Eid detection ───────────────────────────────────────────────

    def _detect_ramadan_effect(self, company, series: list) -> dict:
        """
        For each year in the history, check if the month(s) overlapping with
        Ramadan show a deviation from the average seasonal index.
        Returns a dict with detected effects.
        """
        from apps.transactions.models import MaterialMovement

        effects = {}
        years_in_data = set(r["year"] for r in series)

        for year, start in RAMADAN_STARTS.items():
            if year not in years_in_data:
                continue
            end = start + timedelta(days=RAMADAN_DURATION_DAYS)

            # Revenue during Ramadan month vs same month prior year
            ramadan_rev = (
                MaterialMovement.objects
                .filter(company=company, movement_type="ف بيع",
                        movement_date__gte=start, movement_date__lte=end)
                .aggregate(total=Sum("total_out"))
            )
            daily_avg_ramadan = float(ramadan_rev["total"] or 0) / RAMADAN_DURATION_DAYS

            # Prior 30 days baseline
            prior_start = start - timedelta(days=30)
            prior_rev   = (
                MaterialMovement.objects
                .filter(company=company, movement_type="ف بيع",
                        movement_date__gte=prior_start, movement_date__lt=start)
                .aggregate(total=Sum("total_out"))
            )
            daily_avg_prior = float(prior_rev["total"] or 0) / 30

            if daily_avg_prior > 0:
                ramadan_index = daily_avg_ramadan / daily_avg_prior
                effects[year] = {
                    "year":           year,
                    "start":          str(start),
                    "end":            str(end),
                    "months":         [start.month, end.month],
                    "ramadan_index":  round(ramadan_index, 3),
                    "effect":         ("boost" if ramadan_index > 1.05 else
                                       "drop"  if ramadan_index < 0.95 else "neutral"),
                    "daily_avg_lyd":  round(daily_avg_ramadan, 2),
                }

        avg_effect = (sum(e["ramadan_index"] for e in effects.values()) / len(effects)
                      if effects else 1.0)
        return {
            "detected":          bool(effects),
            "years_analyzed":    list(effects.keys()),
            "avg_ramadan_index": round(avg_effect, 3),
            "dominant_effect":   (
                "sales boost during Ramadan" if avg_effect > 1.05 else
                "sales slowdown during Ramadan" if avg_effect < 0.95 else
                "minimal Ramadan effect"
            ),
            "annual_effects": effects,
            "adjustment_note": (
                f"Ramadan shifts ~11 days/year. "
                f"Avg daily sales {'increase' if avg_effect >= 1.0 else 'decrease'} "
                f"{abs(avg_effect - 1)*100:.0f}% during Ramadan."
                if effects else "Insufficient Ramadan data."
            ),
        }

    # ── Trend & helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_trend(series: list) -> dict:
        n = len(series)
        if n < 3:
            return {"direction": "insufficient_data", "slope_pct_per_month": 0.0, "r_squared": 0.0}
        x  = list(range(n))
        y  = [row["revenue"] for row in series]
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        den = sum((xi - mx) ** 2 for xi in x)
        if den == 0:
            return {"direction": "flat", "slope_pct_per_month": 0.0, "r_squared": 0.0}
        slope     = num / den
        intercept = my - slope * mx
        y_hat     = [slope * xi + intercept for xi in x]
        ss_res    = sum((yi - yhi) ** 2 for yi, yhi in zip(y, y_hat))
        ss_tot    = sum((yi - my) ** 2 for yi in y)
        r2        = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        slope_pct = (slope / my * 100) if my > 0 else 0.0
        direction = "growing" if slope_pct > 1 else "declining" if slope_pct < -1 else "stable"
        return {"direction": direction, "slope_pct_per_month": round(slope_pct, 3),
                "slope_lyd_per_month": round(slope, 2), "r_squared": round(r2, 4)}

    @staticmethod
    def _classify_months(indices: dict):
        peaks   = [m for m, v in indices.items() if v["label"] == "peak"]
        troughs = [m for m, v in indices.items() if v["label"] == "trough"]
        return peaks, troughs

    def _compute_category_patterns(self, company) -> list:
        try:
            from apps.transactions.models import MaterialMovement
            today      = date.today()
            start_date = today.replace(day=1) - timedelta(days=HISTORY_MONTHS * 30)
            rows = (
                MaterialMovement.objects
                .filter(company=company, movement_type="ف بيع", movement_date__gte=start_date)
                .annotate(month=TruncMonth("movement_date"))
                .values("month", "category")
                .annotate(revenue=Sum("total_out"))
                .order_by("category", "month")
            )
            by_cat = defaultdict(lambda: defaultdict(list))
            for row in rows:
                cat = row.get("category") or "Unclassified"
                by_cat[cat][row["month"].month].append(float(row["revenue"] or 0))
            results = []
            for cat, monthly_data in list(by_cat.items())[:8]:
                all_vals = [v for vs in monthly_data.values() for v in vs]
                if not all_vals:
                    continue
                overall_avg = sum(all_vals) / len(all_vals)
                month_si = {m: sum(vs) / len(vs) / overall_avg
                            for m, vs in monthly_data.items() if vs and overall_avg > 0}
                if not month_si:
                    continue
                peak_m   = max(month_si, key=month_si.get)
                trough_m = min(month_si, key=month_si.get)
                results.append({"category": cat,
                                 "peak_month": peak_m, "peak_month_name": MONTH_NAMES[peak_m],
                                 "peak_index": round(month_si[peak_m], 4),
                                 "trough_month": trough_m, "trough_month_name": MONTH_NAMES[trough_m],
                                 "trough_index": round(month_si[trough_m], 4)})
            return results
        except Exception:
            return []

    @staticmethod
    def _check_upcoming_peak(peaks: list) -> bool:
        today    = date.today()
        upcoming = today + timedelta(days=60)
        for month_num in peaks:
            year   = today.year
            target = date(year, month_num, 1)
            if target < today:
                target = date(year + 1, month_num, 1)
            if (target - today).days <= 60:
                return True
        return False

    @staticmethod
    def _current_season_label(indices: dict) -> str:
        m    = date.today().month
        info = indices.get(m, {})
        si   = info.get("seasonality_index", 1.0)
        name = info.get("month_name", "")
        lbl  = info.get("label", "normal")
        return (f"Peak season ({name} — SI={si:.2f})" if lbl == "peak" else
                f"Low season ({name} — SI={si:.2f})"  if lbl == "trough" else
                f"Normal demand ({name} — SI={si:.2f})")

    def _call_ai(self, indices, peaks, troughs, trend, ramadan_flags, company_id) -> dict | None:
        index_lines = []
        for m, v in sorted(indices.items()):
            si = v["seasonality_index"]
            if si:
                bar = "█" * min(20, int(si * 10))
                index_lines.append(f"  {v['month_name']:<12} SI={si:.4f}  {bar}  [{v['label'].upper()}]")
        ramadan_note = (
            f"Ramadan effect: {ramadan_flags['dominant_effect']} "
            f"(avg index={ramadan_flags['avg_ramadan_index']:.3f})"
            if ramadan_flags.get("detected") else "Ramadan effect: insufficient data"
        )
        user_prompt = (
            f"Seasonality — Libyan B2B Distribution | History: {HISTORY_MONTHS}mo\n"
            f"Trend: {trend['direction']} ({trend['slope_pct_per_month']:+.2f}%/mo, R²={trend['r_squared']:.3f})\n"
            f"{ramadan_note}\n\n"
            f"Monthly Seasonality Indices:\n" + "\n".join(index_lines) + "\n\n"
            f"Peak months: {', '.join(MONTH_NAMES[m] for m in peaks) or 'None'}\n"
            f"Trough months: {', '.join(MONTH_NAMES[m] for m in troughs) or 'None'}"
        )
        return self._client.complete(
            system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt,
            model="smart", max_tokens=800,
            analyzer="seasonal_analyzer", company_id=str(company_id),
        )

    def _format_result(self, indices, trend, peaks, troughs, category_pats,
                        upcoming_alert, current_season, ramadan_flags, ai_result) -> dict:
        narrative    = self._default_narrative(indices, peaks, troughs, trend)
        recs         = self._default_recommendations(peaks, troughs)
        stock_cal    = self._default_stock_calendar(peaks)
        staffing     = self._default_staffing(indices, peaks)
        confidence   = "medium"

        if ai_result and not ai_result.get("error"):
            narrative   = ai_result.get("seasonal_narrative",         narrative)
            recs        = ai_result.get("ai_recommendations",         recs)
            stock_cal   = ai_result.get("stock_preparation_calendar", stock_cal)
            staffing    = ai_result.get("staffing_implications",      staffing)
            confidence  = ai_result.get("confidence",                 "medium")

        return {
            "history_months": HISTORY_MONTHS,
            "current_season": current_season,
            "upcoming_peak_alert": upcoming_alert,
            "trend": trend,
            "seasonality_indices": indices,
            "peak_months": peaks,
            "peak_month_names": [MONTH_NAMES[m] for m in peaks],
            "trough_months": troughs,
            "trough_month_names": [MONTH_NAMES[m] for m in troughs],
            "category_patterns": category_pats,
            "ramadan_analysis": ramadan_flags,
            "seasonal_narrative": narrative,
            "stock_preparation_calendar": stock_cal,
            "staffing_implications": staffing,
            "ai_recommendations": recs,
            "confidence": confidence,
        }

    @staticmethod
    def _default_narrative(indices, peaks, troughs, trend) -> str:
        peak_names   = [MONTH_NAMES[m] for m in peaks]
        trough_names = [MONTH_NAMES[m] for m in troughs]
        parts = []
        if peak_names:
            avg_si = sum(indices[m]["seasonality_index"] for m in peaks
                         if indices[m]["seasonality_index"]) / max(len(peaks), 1)
            parts.append(f"Peak demand in {', '.join(peak_names)} (avg SI={avg_si:.2f} — {int((avg_si-1)*100)}% above average).")
        if trough_names:
            parts.append(f"Weakest demand in {', '.join(trough_names)}.")
        parts.append(f"Overall trend: {trend['direction']} at {trend['slope_pct_per_month']:+.2f}%/month.")
        return " ".join(parts)

    @staticmethod
    def _default_recommendations(peaks, troughs) -> list:
        recs = []
        if peaks:
            recs.append(f"Begin inventory build-up 6 weeks before {MONTH_NAMES[peaks[0]]} to avoid stock-outs.")
        if troughs:
            recs.append(f"Use {MONTH_NAMES[troughs[0]]} for supplier negotiations and warehouse reorganization.")
        recs.append("Review seasonality indices quarterly to detect demand pattern shifts.")
        return recs

    @staticmethod
    def _default_stock_calendar(peaks) -> list:
        return [{
            "month": MONTH_NAMES.get((m - 2) if m > 2 else m + 10, ""),
            "action": f"Place large orders ahead of {MONTH_NAMES[m]} peak",
            "lead_time_weeks": 6,
            "rationale": "SI ≥ 1.15 — build buffer stock 6 weeks in advance.",
        } for m in peaks]

    @staticmethod
    def _default_staffing(indices, peaks) -> str:
        if not peaks:
            return "No significant seasonal staffing implications detected."
        valid_si = [indices[m]["seasonality_index"] for m in peaks if indices[m]["seasonality_index"]]
        if not valid_si:
            return "Insufficient data for staffing recommendations."
        max_si   = max(valid_si)
        pct      = int((max_si - 1) * 100)
        return (f"During {', '.join(MONTH_NAMES[m] for m in peaks)}, expect up to {pct}% more order volume. "
                f"Plan for additional delivery staff and extended warehouse hours.")

    @staticmethod
    def _empty_result(reason: str) -> dict:
        return {"error": reason, "seasonality_indices": {}, "peak_months": [],
                "trough_months": [], "trend": {}, "category_patterns": [],
                "ramadan_analysis": {}, "ai_recommendations": [], "confidence": "low"}