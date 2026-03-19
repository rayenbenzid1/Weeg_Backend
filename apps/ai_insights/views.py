"""
apps/ai_insights/views.py
--------------------------
Six endpoints : SCRUM-27 (Churn), SCRUM-29 (Risk Alerts), AI Usage Stats.

  POST   /api/ai-insights/alerts/explain/
  POST   /api/ai-insights/alerts/resolve/
  DELETE /api/ai-insights/alerts/resolve/<alert_id>/
  GET    /api/ai-insights/alerts/resolutions/
  GET    /api/ai-insights/churn/
  GET    /api/ai-insights/churn/high-value/
  GET    /api/ai-insights/usage/          ← dashboard coûts AI (nouveau)

Architecture rules :
  - Views orchestrate; never call AI directly.
  - On RateLimitError → immediate fallback, no sleep, no retry in the view.
  - Fallback results cached for 5 minutes only (not 1 hour).
  - AI results cached for their full TTL.
"""

import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum, Count, Avg
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AlertResolution
from .serializers import (
    AlertExplainInputSerializer,
    AlertResolveInputSerializer,
    AlertResolutionSerializer,
)

logger = logging.getLogger(__name__)

# ── Cache TTLs ────────────────────────────────────────────────────────────────
EXPLAIN_CACHE_TTL       = 60 * 60        # 1 h  — réponse AI réussie
EXPLAIN_FALLBACK_TTL    = 60 * 5         # 5 min — fallback rule-based
CHURN_CACHE_TTL         = 60 * 60 * 6   # 6 h  — churn predictions
HV_CHURN_CACHE_TTL      = 60 * 60 * 6   # 6 h  — high-value churn


def _explain_cache_key(company_id: str, payload: dict) -> str:
    h = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]
    return f"ai:explain:{company_id}:{h}"


def _churn_cache_key(company_id: str, top_n: int, use_ai: bool) -> str:
    return f"ai:churn:{company_id}:n{top_n}:ai{int(use_ai)}"


def _hv_churn_cache_key(company_id: str, threshold: float, top_n: int, use_ai: bool) -> str:
    return f"ai:hv_churn:{company_id}:t{int(threshold)}:n{top_n}:ai{int(use_ai)}"


def _require_company(request):
    company = getattr(request.user, "company", None)
    if not company:
        return None, Response(
            {"error": "Your account is not linked to a company. Contact your administrator."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return company, None


def _get_fallback(alert_data: dict) -> dict:
    """Rule-based fallback using real alert data — no AI required."""
    from .analyzers.risk_alert import RiskAlertAnalyzer
    analyzer = RiskAlertAnalyzer.__new__(RiskAlertAnalyzer)
    return analyzer._fallback(alert_data)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Alert Explain
# ─────────────────────────────────────────────────────────────────────────────

class AlertExplainView(APIView):
    """
    POST /api/ai-insights/alerts/explain/

    Returns AI explanation for one alert.
    - AI result    → cached 1 hour
    - Fallback     → cached 5 minutes (retry sooner when AI comes back)
    - Rate limited → immediate fallback, no blocking
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company, err = _require_company(request)
        if err:
            return err

        serializer = AlertExplainInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        alert_data = dict(serializer.validated_data)

        cache_key = _explain_cache_key(str(company.id), alert_data)
        cached    = cache.get(cache_key)
        if cached:
            return Response({**cached, "cached": True})

        # Attempt AI — fall back immediately on rate limit
        try:
            from .analyzers.risk_alert import RiskAlertAnalyzer
            result = RiskAlertAnalyzer().explain(
                alert_data=alert_data,
                company_id=str(company.id),
            )
        except Exception as exc:
            logger.warning("[AlertExplainView] AI unavailable (%s) — using rule-based fallback", exc)
            result = _get_fallback(alert_data)

        # Cache AI results for 1h, fallbacks for 5min
        is_fallback = result.get("_ai_unavailable", False)
        ttl = EXPLAIN_FALLBACK_TTL if is_fallback else EXPLAIN_CACHE_TTL
        cache.set(cache_key, result, timeout=ttl)

        return Response({**result, "cached": False}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Alert Resolve
# ─────────────────────────────────────────────────────────────────────────────

class AlertResolveView(APIView):
    """
    POST   /api/ai-insights/alerts/resolve/        → mark as resolved (idempotent)
    DELETE /api/ai-insights/alerts/resolve/<id>/   → re-open
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company, err = _require_company(request)
        if err:
            return err

        serializer = AlertResolveInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        resolution, created = AlertResolution.objects.get_or_create(
            company=company,
            alert_id=data["alert_id"],
            defaults={
                "alert_type":  data["alert_type"],
                "resolved_by": request.user,
                "notes":       data.get("notes", ""),
            },
        )

        return Response({
            "alert_id":    data["alert_id"],
            "resolved":    True,
            "created":     created,
            "resolved_by": request.user.get_full_name() or request.user.email,
            "resolved_at": resolution.resolved_at.isoformat(),
        })

    def delete(self, request, alert_id: str):
        company, err = _require_company(request)
        if err:
            return err

        deleted, _ = AlertResolution.objects.filter(
            company=company, alert_id=alert_id
        ).delete()

        if deleted:
            return Response({"alert_id": alert_id, "reopened": True})
        return Response(
            {"error": "Resolution not found — alert may already be open."},
            status=status.HTTP_404_NOT_FOUND,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Alert Resolutions List
# ─────────────────────────────────────────────────────────────────────────────

class AlertResolutionsView(APIView):
    """GET /api/ai-insights/alerts/resolutions/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        resolutions = (
            AlertResolution.objects
            .filter(company=company)
            .select_related("resolved_by")
            .order_by("-resolved_at")
        )
        serialized = AlertResolutionSerializer(resolutions, many=True).data
        return Response({
            "count":        resolutions.count(),
            "resolved_ids": [r["alert_id"] for r in serialized],
            "resolutions":  serialized,
        })


# ─────────────────────────────────────────────────────────────────────────────
# 4. Churn Prediction
# ─────────────────────────────────────────────────────────────────────────────

class ChurnPredictionView(APIView):
    """
    GET /api/ai-insights/churn/

    Query params:
        top_n=<int>    — max customers returned (default 20, max 50)
        use_ai=<bool>  — enable AI refinement (default true)
        refresh=<bool> — bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        try:
            top_n = min(50, max(1, int(request.query_params.get("top_n", 20))))
        except (TypeError, ValueError):
            top_n = 20

        use_ai  = request.query_params.get("use_ai",  "true").lower()  != "false"
        refresh = request.query_params.get("refresh", "false").lower() == "true"
        cache_key = _churn_cache_key(str(company.id), top_n, use_ai)

        if not refresh:
            cached = cache.get(cache_key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.churn_predictor import ChurnPredictor
            predictions = ChurnPredictor().predict(
                company=company, top_n=top_n, use_ai=use_ai,
            )
        except Exception as exc:
            logger.error("[ChurnPredictionView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({
                "error": "Churn prediction temporarily unavailable.",
                "predictions": [],
                "summary": {"total": 0, "critical": 0, "high": 0,
                            "medium": 0, "low": 0, "avg_churn_score": 0.0},
                "ai_success_rate": 0,
                "cached": False,
            })

        summary         = self._build_summary(predictions)
        ai_success_rate = self._ai_success_rate(predictions)
        payload = {
            "company_id":      str(company.id),
            "top_n":           top_n,
            "ai_used":         use_ai,
            "ai_success_rate": ai_success_rate,
            "summary":         summary,
            "predictions":     predictions,
        }
        cache.set(cache_key, payload, timeout=CHURN_CACHE_TTL)
        return Response({**payload, "cached": False})

    @staticmethod
    def _build_summary(predictions: list[dict]) -> dict:
        if not predictions:
            return {"total": 0, "critical": 0, "high": 0,
                    "medium": 0, "low": 0, "avg_churn_score": 0.0}
        return {
            "total":           len(predictions),
            "critical":        sum(1 for p in predictions if p["churn_label"] == "critical"),
            "high":            sum(1 for p in predictions if p["churn_label"] == "high"),
            "medium":          sum(1 for p in predictions if p["churn_label"] == "medium"),
            "low":             sum(1 for p in predictions if p["churn_label"] == "low"),
            "avg_churn_score": round(
                sum(p["churn_score"] for p in predictions) / len(predictions), 4
            ),
        }

    @staticmethod
    def _ai_success_rate(predictions: list[dict]) -> int:
        """Returns the percentage of predictions powered by AI (not rule-based fallback)."""
        if not predictions:
            return 0
        ai_powered = sum(1 for p in predictions if p.get("confidence") != "medium"
                         or p.get("_ai_used", False))
        return round(ai_powered / len(predictions) * 100)


# ─────────────────────────────────────────────────────────────────────────────
# 5. High-Value Churn
# ─────────────────────────────────────────────────────────────────────────────

class HighValueChurnView(APIView):
    """
    GET /api/ai-insights/churn/high-value/

    Query params:
        threshold=<float>  — annual revenue threshold in LYD (default 100,000)
        top_n=<int>        — max at-risk customers (default 10, max 25)
        use_ai=<bool>      — enable AI outcomes + playbook (default true)
        refresh=<bool>     — bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        try:
            threshold = float(request.query_params.get("threshold", 100_000))
        except (TypeError, ValueError):
            threshold = 100_000

        try:
            top_n = min(25, max(1, int(request.query_params.get("top_n", 10))))
        except (TypeError, ValueError):
            top_n = 10

        use_ai  = request.query_params.get("use_ai",  "true").lower()  != "false"
        refresh = request.query_params.get("refresh", "false").lower() == "true"
        cache_key = _hv_churn_cache_key(str(company.id), threshold, top_n, use_ai)

        if not refresh:
            cached = cache.get(cache_key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.high_value_churn import HighValueChurnDetector
            result = HighValueChurnDetector().detect(
                company=company, threshold_lyd=threshold, top_n=top_n, use_ai=use_ai,
            )
        except Exception as exc:
            logger.error("[HighValueChurnView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({
                "error": "High-value churn detection temporarily unavailable.",
                "threshold_lyd": threshold, "total_hv_customers": 0,
                "at_risk_count": 0, "total_revenue_at_risk": 0.0,
                "customers": [], "cached": False,
            })

        payload = {
            "company_id":            str(company.id),
            "threshold_lyd":         threshold,
            "total_hv_customers":    result["total_hv_customers"],
            "at_risk_count":         result["at_risk_count"],
            "total_revenue_at_risk": result["total_revenue_at_risk"],
            "ai_used":               use_ai,
            "customers":             result["customers"],
        }
        cache.set(cache_key, payload, timeout=HV_CHURN_CACHE_TTL)
        return Response({**payload, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# 6. AI Usage Dashboard (NOUVEAU — pour présentation CEO)
# ─────────────────────────────────────────────────────────────────────────────

class AIUsageView(APIView):
    """
    GET /api/ai-insights/usage/

    Returns AI consumption metrics for the current company.
    Used by the CEO dashboard to show cost transparency.

    Query params:
        days=<int>  — lookback window in days (default 30)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        try:
            days = min(90, max(1, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30

        from datetime import datetime, timedelta, timezone
        from .models import AIUsageLog

        since = datetime.now(timezone.utc) - timedelta(days=days)

        qs = AIUsageLog.objects.filter(
            company=company,
            created_at__gte=since,
        )

        totals = qs.aggregate(
            total_calls=Count("id"),
            total_tokens=Sum("tokens_used"),
            total_cost=Sum("cost_usd"),
        )

        by_analyzer = list(
            qs.values("analyzer")
            .annotate(calls=Count("id"), tokens=Sum("tokens_used"), cost=Sum("cost_usd"))
            .order_by("-calls")
        )

        # Fallback rate from churn cache — approximate
        churn_cache_key = _churn_cache_key(str(company.id), 20, True)
        cached_churn    = cache.get(churn_cache_key)
        ai_success_rate = cached_churn.get("ai_success_rate", None) if cached_churn else None

        return Response({
            "period_days":      days,
            "total_calls":      totals["total_calls"] or 0,
            "total_tokens":     totals["total_tokens"] or 0,
            "total_cost_usd":   float(totals["total_cost"] or 0),
            "by_analyzer":      by_analyzer,
            "ai_success_rate":  ai_success_rate,
            "model":            getattr(settings, "AI_MODEL_SMART", "gpt-4o-mini"),
            "provider":         getattr(settings, "AI_PROVIDER", "openai"),
        })