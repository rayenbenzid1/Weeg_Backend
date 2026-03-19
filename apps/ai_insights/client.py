"""
apps/ai_insights/client.py
--------------------------
Wrapper AI — OpenAI ou Anthropic selon AI_PROVIDER dans les settings.

RÈGLES :
  1. Seul ce fichier appelle openai.* / anthropic.*
  2. Toutes les sorties sont JSON.
  3. Les noms/codes clients ne sont JAMAIS envoyés ici.
  4. time.sleep() est INTERDIT dans les vues Django synchrones.
     En cas de rate limit, on lève AIClientError immédiatement
     pour que la vue retourne le fallback sans bloquer le worker.

Configuration dans .env :
    AI_PROVIDER       = "openai"          # ou "anthropic"
    OPENAI_API_KEY    = "sk-proj-..."
    ANTHROPIC_API_KEY = "sk-ant-..."
    AI_MODEL_SMART    = "gpt-4o-mini"
    AI_MODEL_FAST     = "gpt-4o-mini"
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """Levée quand l'appel AI échoue — la vue doit retourner le fallback."""
    pass


class RateLimitError(AIClientError):
    """Sous-classe spécifique pour rate limit — permet de distinguer les causes."""
    pass


class AIClient:
    """
    Façade unifiée OpenAI / Anthropic.

    Pas de time.sleep() — en cas de rate limit, on lève RateLimitError
    immédiatement et la vue retourne le fallback rule-based.
    La mise en cache côté vue empêche les appels répétés.
    """

    # Modèles OpenAI qui supportent response_format=json_object
    _OAI_JSON_MODE = {
        "gpt-4o", "gpt-4o-mini", "gpt-4o-2024-08-06",
        "gpt-4-turbo", "gpt-3.5-turbo-1106", "gpt-3.5-turbo-0125",
    }

    def __init__(self):
        self._provider    = getattr(settings, "AI_PROVIDER",       "openai").lower()
        self._model_smart = getattr(settings, "AI_MODEL_SMART",    "gpt-4o-mini")
        self._model_fast  = getattr(settings, "AI_MODEL_FAST",     "gpt-4o-mini")
        self._oai_key     = getattr(settings, "OPENAI_API_KEY",    "") or ""
        self._ant_key     = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
        self._oai_client  = None
        self._ant_client  = None

    # ── Lazy client initialisation ────────────────────────────────────────────

    def _get_openai(self):
        if self._oai_client is None:
            if not self._oai_key.strip():
                raise AIClientError("OPENAI_API_KEY manquant dans .env")
            import openai
            self._oai_client = openai.OpenAI(api_key=self._oai_key.strip())
        return self._oai_client

    def _get_anthropic(self):
        if self._ant_client is None:
            if not self._ant_key.strip():
                raise AIClientError("ANTHROPIC_API_KEY manquant dans .env")
            import anthropic
            self._ant_client = anthropic.Anthropic(api_key=self._ant_key.strip())
        return self._ant_client

    # ── JSON extraction robuste ───────────────────────────────────────────────

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """Extrait un dict JSON depuis une réponse brute, quelle que soit sa forme."""
        if not raw:
            return {"error": "empty_response"}
        # 1. Tentative directe
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            pass
        # 2. Bloc ```json ... ```
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 3. Premier objet JSON dans le texte libre
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning("[AIClient] JSON parse failed. Raw (300 chars): %s", raw[:300])
        return {"error": "parse_failed", "raw_slice": raw[:500]}

    # ── Interface publique ────────────────────────────────────────────────────

    def complete(
        self,
        system_prompt: str,
        user_prompt:   str,
        model:         str = "fast",
        max_tokens:    int = 800,
        analyzer:      str = "unknown",
        company_id:    str = None,
    ) -> dict:
        """
        Envoie une requête AI et retourne toujours un dict JSON.

        Raises:
            RateLimitError  — rate limit atteint, retourner le fallback immédiatement.
            AIClientError   — toute autre erreur AI.
        """
        resolved = self._model_smart if model == "smart" else self._model_fast
        if self._provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt, resolved,
                                        max_tokens, analyzer, company_id)
        return self._call_openai(system_prompt, user_prompt, resolved,
                                 max_tokens, analyzer, company_id)

    # ── Anthropic ─────────────────────────────────────────────────────────────

    def _call_anthropic(self, system_prompt, user_prompt, model,
                        max_tokens, analyzer, company_id):
        import anthropic as ant
        client = self._get_anthropic()
        try:
            import time as _time
            start = _time.monotonic()
            resp  = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt + "\n\nReturn ONLY valid JSON. No markdown, no preamble.",
                messages=[{"role": "user", "content": user_prompt}],
            )
            ms     = int((_time.monotonic() - start) * 1000)
            tokens = (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
            logger.info("[AIClient] ✓ anthropic analyzer=%s model=%s tokens=%d latency=%dms",
                        analyzer, model, tokens, ms)
            raw = resp.content[0].text if resp.content else ""
            result = self._extract_json(raw)
            self._log_usage(analyzer, model, tokens, company_id)
            return result

        except ant.RateLimitError as exc:
            logger.warning("[AIClient] Anthropic rate limit — returning fallback. analyzer=%s", analyzer)
            raise RateLimitError("Anthropic rate limit reached") from exc
        except ant.AuthenticationError as exc:
            raise AIClientError("Clé ANTHROPIC_API_KEY invalide.") from exc
        except Exception as exc:
            logger.error("[AIClient] Anthropic error analyzer=%s: %s", analyzer, exc)
            raise AIClientError(str(exc)) from exc

    # ── OpenAI ────────────────────────────────────────────────────────────────

    def _call_openai(self, system_prompt, user_prompt, model,
                     max_tokens, analyzer, company_id):
        import openai
        client = self._get_openai()

        use_json_mode = any(m in model for m in self._OAI_JSON_MODE)
        effective_sys = system_prompt
        if not use_json_mode:
            effective_sys += "\n\nReturn ONLY valid JSON. No markdown, no preamble."

        kwargs: dict = dict(
            model=model, max_tokens=max_tokens, temperature=0.2,
            messages=[
                {"role": "system", "content": effective_sys},
                {"role": "user",   "content": user_prompt},
            ],
        )
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            import time as _time
            start = _time.monotonic()
            resp  = client.chat.completions.create(**kwargs)
            ms     = int((_time.monotonic() - start) * 1000)
            usage  = resp.usage
            tokens = usage.total_tokens if usage else 0
            logger.info("[AIClient] ✓ openai analyzer=%s model=%s tokens=%d latency=%dms",
                        analyzer, model, tokens, ms)
            raw    = resp.choices[0].message.content or ""
            result = self._extract_json(raw)
            self._log_usage(analyzer, model, tokens, company_id)
            return result

        except openai.RateLimitError as exc:
            logger.warning("[AIClient] OpenAI rate limit — returning fallback. analyzer=%s", analyzer)
            raise RateLimitError("OpenAI rate limit reached") from exc
        except openai.AuthenticationError as exc:
            raise AIClientError("Clé OPENAI_API_KEY invalide.") from exc
        except openai.BadRequestError as exc:
            # json_object non supporté → retry sans
            if use_json_mode:
                logger.warning("[AIClient] json_object not supported for %s, retrying without.", model)
                kwargs.pop("response_format", None)
                kwargs["messages"][0]["content"] += (
                    "\n\nReturn ONLY valid JSON. No markdown, no preamble."
                )
                try:
                    import time as _time
                    resp   = client.chat.completions.create(**kwargs)
                    raw    = resp.choices[0].message.content or ""
                    return self._extract_json(raw)
                except Exception as exc2:
                    raise AIClientError(str(exc2)) from exc2
            raise AIClientError(str(exc)) from exc
        except Exception as exc:
            logger.error("[AIClient] OpenAI error analyzer=%s: %s", analyzer, exc)
            raise AIClientError(str(exc)) from exc

    # ── Usage logging (pour monitoring des coûts) ─────────────────────────────

    @staticmethod
    def _log_usage(analyzer: str, model: str, tokens: int, company_id: str | None) -> None:
        """
        Persiste la consommation de tokens en base pour le dashboard de coûts.
        N'interrompt JAMAIS le flux principal en cas d'erreur.
        """
        try:
            from apps.ai_insights.models import AIUsageLog
            # Coût approximatif : gpt-4o-mini = $0.00015/1K input, $0.0006/1K output
            # On utilise une estimation conservative à $0.0003/1K tokens
            cost_usd = round((tokens / 1000) * 0.0003, 8)
            AIUsageLog.objects.create(
                analyzer=analyzer,
                model=model,
                tokens_used=tokens,
                cost_usd=cost_usd,
                company_id=company_id,
            )
        except Exception:
            pass  # Ne jamais bloquer sur le logging