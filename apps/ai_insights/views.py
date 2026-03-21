"""
apps/ai_insights/views.py
--------------------------
Twelve endpoints covering all Intelligent Analysis SCRUM tickets:

  SCRUM-24  GET  /api/ai-insights/kpis/              KPI analysis
  SCRUM-25  GET  /api/ai-insights/anomalies/          Anomaly detection
  SCRUM-26  GET  /api/ai-insights/seasonal/           Seasonal trends
  SCRUM-27  GET  /api/ai-insights/churn/              Customer churn prediction
  SCRUM-28  GET  /api/ai-insights/stock/              Stock optimization
  SCRUM-29  POST /api/ai-insights/alerts/explain/     Risk alert explanation
  SCRUM-30  GET  /api/ai-insights/predict/            Revenue & demand forecast
  SCRUM-35  GET  /api/ai-insights/critical/           Critical situation detector

  Support:
  POST   /api/ai-insights/alerts/resolve/
  DELETE /api/ai-insights/alerts/resolve/<id>/
  GET    /api/ai-insights/alerts/resolutions/
  GET    /api/ai-insights/churn/high-value/
  GET    /api/ai-insights/usage/

Architecture rules:
  - Views orchestrate; never call AI directly.
  - RateLimitError → immediate fallback, no sleep, no retry in the view.
  - All analyzers are cached; refresh=true bypasses cache.
  - Cache TTLs are longer for AI results, shorter for fallbacks.
"""

import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum, Count
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
EXPLAIN_CACHE_TTL    = 60 * 60        # 1 h
EXPLAIN_FALLBACK_TTL = 60 * 5         # 5 min
CHURN_CACHE_TTL      = 60 * 60 * 6   # 6 h
HV_CHURN_CACHE_TTL   = 60 * 60 * 6   # 6 h
KPI_CACHE_TTL        = 60 * 60 * 2   # 2 h
ANOMALY_CACHE_TTL    = 60 * 60 * 4   # 4 h  (12-month rolling window)
SEASONAL_CACHE_TTL   = 60 * 60 * 12  # 12 h  (seasonality changes slowly)
STOCK_CACHE_TTL      = 60 * 60 * 2   # 2 h
PREDICT_CACHE_TTL    = 60 * 60 * 6   # 6 h
CRITICAL_CACHE_TTL   = 60 * 30       # 30 min (executive dashboard refreshes often)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_company(request):
    company = getattr(request.user, "company", None)
    if not company:
        return None, Response(
            {"error": "Your account is not linked to a company. Contact your administrator."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return company, None


def _explain_cache_key(company_id: str, payload: dict) -> str:
    h = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]
    return f"ai:explain:{company_id}:{h}"


def _cache_key(prefix: str, company_id: str, **kwargs) -> str:
    suffix = ":".join(f"{k}{v}" for k, v in sorted(kwargs.items()))
    return f"ai:{prefix}:{company_id}:{suffix}"


def _parse_bool(val: str, default: bool = True) -> bool:
    return default if val is None else val.lower() != "false"


def _get_fallback(alert_data: dict) -> dict:
    from .analyzers.risk_alert import RiskAlertAnalyzer
    analyzer = RiskAlertAnalyzer.__new__(RiskAlertAnalyzer)
    return analyzer._fallback(alert_data)


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-29 — Alert Explain
# ─────────────────────────────────────────────────────────────────────────────

class AlertExplainView(APIView):
    """POST /api/ai-insights/alerts/explain/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company, err = _require_company(request)
        if err:
            return err

        serializer = AlertExplainInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        alert_data = dict(serializer.validated_data)
        cache_key  = _explain_cache_key(str(company.id), alert_data)
        cached     = cache.get(cache_key)
        if cached:
            return Response({**cached, "cached": True})

        try:
            from .analyzers.risk_alert import RiskAlertAnalyzer
            result = RiskAlertAnalyzer().explain(
                alert_data=alert_data, company_id=str(company.id),
            )
        except Exception as exc:
            logger.warning("[AlertExplainView] AI unavailable (%s) — using fallback", exc)
            result = _get_fallback(alert_data)

        is_fallback = result.get("_ai_unavailable", False)
        cache.set(cache_key, result, timeout=EXPLAIN_FALLBACK_TTL if is_fallback else EXPLAIN_CACHE_TTL)
        return Response({**result, "cached": False}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Alert Resolve
# ─────────────────────────────────────────────────────────────────────────────

class AlertResolveView(APIView):
    """
    POST   /api/ai-insights/alerts/resolve/
    DELETE /api/ai-insights/alerts/resolve/<id>/
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
            {"error": "Resolution not found."},
            status=status.HTTP_404_NOT_FOUND,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Alert Resolutions List
# ─────────────────────────────────────────────────────────────────────────────

class AlertResolutionsView(APIView):
    """GET /api/ai-insights/alerts/resolutions/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        resolutions = (
            AlertResolution.objects.filter(company=company)
            .select_related("resolved_by").order_by("-resolved_at")
        )
        serialized = AlertResolutionSerializer(resolutions, many=True).data
        return Response({
            "count":        resolutions.count(),
            "resolved_ids": [r["alert_id"] for r in serialized],
            "resolutions":  serialized,
        })


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-24 — KPI Analyzer
# ─────────────────────────────────────────────────────────────────────────────

class KPIAnalysisView(APIView):
    """
    GET /api/ai-insights/kpis/

    Query params:
        use_ai=<bool>     enable AI narrative (default true)
        refresh=<bool>    bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("kpi", str(company.id), ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.kpi_analyzer import KPIAnalyzer
            branch = request.query_params.get("branch") or None
            result = KPIAnalyzer().analyze(company, use_ai=use_ai, branch=branch)
        except Exception as exc:
            logger.error("[KPIAnalysisView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({"error": "KPI analysis temporarily unavailable.", "cached": False},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        cache.set(key, result, timeout=KPI_CACHE_TTL)
        return Response({**result, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-25 — Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────

class AnomalyDetectionView(APIView):
    """
    GET /api/ai-insights/anomalies/

    Query params:
        use_ai=<bool>     explain top anomalies with AI (default true)
        refresh=<bool>    bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("anomalies", str(company.id), ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.anomaly_detector import AnomalyDetector
            result = AnomalyDetector().detect(company, use_ai=use_ai)
        except Exception as exc:
            logger.error("[AnomalyDetectionView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({"error": "Anomaly detection temporarily unavailable.", "cached": False},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        cache.set(key, result, timeout=ANOMALY_CACHE_TTL)
        return Response({**result, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-26 — Seasonal Analyzer
# ─────────────────────────────────────────────────────────────────────────────

class SeasonalAnalysisView(APIView):
    """
    GET /api/ai-insights/seasonal/

    Query params:
        use_ai=<bool>     AI seasonal narrative (default true)
        refresh=<bool>    bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("seasonal", str(company.id), ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.seasonal_analyzer import SeasonalAnalyzer
            result = SeasonalAnalyzer().analyze(company, use_ai=use_ai)
        except Exception as exc:
            logger.error("[SeasonalAnalysisView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({"error": "Seasonal analysis temporarily unavailable.", "cached": False},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        cache.set(key, result, timeout=SEASONAL_CACHE_TTL)
        return Response({**result, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-27 — Churn Prediction
# ─────────────────────────────────────────────────────────────────────────────

class ChurnPredictionView(APIView):
    """
    GET /api/ai-insights/churn/

    Query params:
        top_n=<int>        max customers returned (default 20, max 50)
        use_ai=<bool>      enable AI refinement (default true)
        refresh=<bool>     bypass cache (default false)
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

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("churn", str(company.id), n=top_n, ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.churn_predictor import ChurnPredictor
            predictions = ChurnPredictor().predict(company=company, top_n=top_n, use_ai=use_ai)
        except Exception as exc:
            logger.error("[ChurnPredictionView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({
                "error": "Churn prediction temporarily unavailable.",
                "predictions": [], "summary": {}, "cached": False,
            })

        summary = self._build_summary(predictions)
        payload = {
            "company_id":  str(company.id),
            "top_n":       top_n,
            "ai_used":     use_ai,
            "summary":     summary,
            "predictions": predictions,
        }
        cache.set(key, payload, timeout=CHURN_CACHE_TTL)
        return Response({**payload, "cached": False})

    @staticmethod
    def _build_summary(predictions):
        if not predictions:
            return {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "avg_churn_score": 0.0}
        return {
            "total":           len(predictions),
            "critical":        sum(1 for p in predictions if p["churn_label"] == "critical"),
            "high":            sum(1 for p in predictions if p["churn_label"] == "high"),
            "medium":          sum(1 for p in predictions if p["churn_label"] == "medium"),
            "low":             sum(1 for p in predictions if p["churn_label"] == "low"),
            "avg_churn_score": round(sum(p["churn_score"] for p in predictions) / len(predictions), 4),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-28 — Stock Optimizer
# ─────────────────────────────────────────────────────────────────────────────

class StockOptimizationView(APIView):
    """
    GET /api/ai-insights/stock/

    Query params:
        use_ai=<bool>     AI recommendations for Class A items (default true)
        refresh=<bool>    bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("stock", str(company.id), ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.stock_optimizer import StockOptimizer
            result = StockOptimizer().optimize(company, use_ai=use_ai)
        except Exception as exc:
            logger.error("[StockOptimizationView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({"error": "Stock optimization temporarily unavailable.", "cached": False},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        cache.set(key, result, timeout=STOCK_CACHE_TTL)
        return Response({**result, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-30 — Predictor
# ─────────────────────────────────────────────────────────────────────────────

class PredictionView(APIView):
    """
    GET /api/ai-insights/predict/

    Query params:
        use_ai=<bool>     AI forecast narrative (default true)
        refresh=<bool>    bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("predict", str(company.id), ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.predictor import Predictor
            result = Predictor().predict(company, use_ai=use_ai)
        except Exception as exc:
            logger.error("[PredictionView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({"error": "Prediction engine temporarily unavailable.", "cached": False},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        cache.set(key, result, timeout=PREDICT_CACHE_TTL)
        return Response({**result, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# SCRUM-35 — Critical Detector
# ─────────────────────────────────────────────────────────────────────────────

class CriticalDetectionView(APIView):
    """
    GET /api/ai-insights/critical/

    Cross-module executive risk briefing. Aggregates signals from all analyzers.
    Short cache (30 min) — CEO dashboard refreshes frequently.

    Query params:
        use_ai=<bool>     AI executive briefing (default true)
        refresh=<bool>    bypass cache (default false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company, err = _require_company(request)
        if err:
            return err

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("critical", str(company.id), ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
            if cached:
                return Response({**cached, "cached": True})

        try:
            from .analyzers.critical_detector import CriticalDetector
            user_role = getattr(request.user, "role", "manager") or "manager"
            result = CriticalDetector().detect(company, use_ai=use_ai, user_role=user_role)
        except Exception as exc:
            logger.error("[CriticalDetectionView] Failed company=%s: %s", company.id, exc, exc_info=True)
            return Response({
                "error": "Critical detection temporarily unavailable.",
                "critical_count": 0, "situations": [], "cached": False,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        cache.set(key, result, timeout=CRITICAL_CACHE_TTL)
        return Response({**result, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# High-Value Churn
# ─────────────────────────────────────────────────────────────────────────────

class HighValueChurnView(APIView):
    """GET /api/ai-insights/churn/high-value/"""
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

        use_ai  = _parse_bool(request.query_params.get("use_ai"))
        refresh = _parse_bool(request.query_params.get("refresh"), default=False)
        key     = _cache_key("hv_churn", str(company.id), t=int(threshold), n=top_n, ai=int(use_ai))

        if not refresh:
            cached = cache.get(key)
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
        cache.set(key, payload, timeout=HV_CHURN_CACHE_TTL)
        return Response({**payload, "cached": False})


# ─────────────────────────────────────────────────────────────────────────────
# AI Usage Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class AIUsageView(APIView):
    """GET /api/ai-insights/usage/"""
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
        qs    = AIUsageLog.objects.filter(company=company, created_at__gte=since)

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

        return Response({
            "period_days":    days,
            "total_calls":    totals["total_calls"] or 0,
            "total_tokens":   totals["total_tokens"] or 0,
            "total_cost_usd": float(totals["total_cost"] or 0),
            "by_analyzer":    by_analyzer,
            "model":          getattr(settings, "AI_MODEL_SMART", "gpt-4o-mini"),
            "provider":       getattr(settings, "AI_PROVIDER", "openai"),
        })