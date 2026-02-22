"""
apps/authentication/forgot_password_views.py

Reset de mot de passe par code de vérification (pour managers et agents).
Flow :
    1. POST /api/users/forgot-password/request/
       → Vérifie l'email, génère un code 6 chiffres, l'envoie par email
    2. POST /api/users/forgot-password/verify/
       → Vérifie le code, retourne un token temporaire si valide
    3. POST /api/users/forgot-password/reset/
       → Reçoit le token + nouveau mot de passe, met à jour en DB
"""

import random
import string
import logging

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger("django")
User = get_user_model()

# Cache key prefix
RESET_CODE_PREFIX = "pwd_reset_code"
RESET_TOKEN_PREFIX = "pwd_reset_token"
CODE_EXPIRY = 10 * 60       # 10 minutes
TOKEN_EXPIRY = 15 * 60      # 15 minutes after code verified


def _generate_code(length=6) -> str:
    """Génère un code numérique aléatoire."""
    return ''.join(random.choices(string.digits, k=length))


def _generate_token(length=32) -> str:
    """Génère un token alphanumérique sécurisé."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _send_reset_code_email(user, code: str) -> bool:
    """Envoie l'email contenant le code de vérification."""
    subject = "[FASI] Code de réinitialisation de mot de passe"

    text_content = (
        f"Bonjour {user.first_name},\n\n"
        f"Votre code de vérification est : {code}\n\n"
        f"Ce code expire dans 10 minutes.\n\n"
        f"Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.\n\n"
        f"Cordialement,\nL'équipe FASI"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
      <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
        <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:30px;text-align:center;">
          <h1 style="color:#fff;margin:0;font-size:28px;font-weight:bold;">FASI</h1>
        </div>
        <div style="padding:30px;">
          <h2 style="color:#1e293b;">🔐 Réinitialisation du mot de passe</h2>
          <p style="color:#475569;">Bonjour <strong>{user.first_name}</strong>,</p>
          <p style="color:#475569;">
            Vous avez demandé la réinitialisation de votre mot de passe.
            Voici votre code de vérification :
          </p>

          <!-- Code Block -->
          <div style="text-align:center;margin:32px 0;">
            <div style="display:inline-block;background:#f0f4ff;border:2px dashed #4f46e5;border-radius:12px;padding:20px 40px;">
              <p style="margin:0 0 8px;color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:1px;">Code de vérification</p>
              <span style="font-family:monospace;font-size:40px;font-weight:900;color:#4f46e5;letter-spacing:8px;">
                {code}
              </span>
            </div>
          </div>

          <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin:16px 0;text-align:center;">
            <p style="color:#92400e;margin:0;">⏱️ Ce code expire dans <strong>10 minutes</strong></p>
          </div>

          <p style="color:#94a3b8;font-size:13px;text-align:center;">
            Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.<br>
            Votre mot de passe ne sera pas modifié.
          </p>
        </div>
        <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
          <p style="color:#94a3b8;font-size:12px;margin:0;">Email automatique FASI — Ne pas répondre.</p>
        </div>
      </div>
    </body>
    </html>
    """

    try:
        msg = EmailMultiAlternatives(
            subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Erreur envoi email reset code à {user.email}: {e}")
        return False


# =============================================================================
# STEP 1 — Request code
# =============================================================================

class ForgotPasswordRequestView(APIView):
    """
    POST /api/users/forgot-password/request/

    Body : { "email": "user@example.com" }

    - Vérifie que l'email existe
    - Génère un code 6 chiffres
    - Stocke le code en cache (10 min)
    - Envoie le code par email

    Réponse : toujours 200 (pour ne pas révéler si l'email existe)
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response(
                {"error": "L'adresse email est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lookup silencieux — on ne révèle pas si l'email existe
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Réponse générique pour la sécurité
            return Response(
                {"message": "Si cet email est enregistré, vous recevrez un code de vérification."},
                status=status.HTTP_200_OK,
            )

        # Vérifier que le compte peut réinitialiser (pas rejeté)
        if user.status == User.AccountStatus.REJECTED:
            return Response(
                {"error": "Ce compte a été rejeté. Contactez un administrateur."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Générer et stocker le code
        code = _generate_code()
        cache_key = f"{RESET_CODE_PREFIX}:{email}"
        cache.set(cache_key, {
            "code": code,
            "user_id": str(user.id),
            "attempts": 0,
        }, timeout=CODE_EXPIRY)

        # Envoyer l'email
        _send_reset_code_email(user, code)

        logger.info(f"[FORGOT PASSWORD] Code envoyé à {email}")

        return Response(
            {"message": "Si cet email est enregistré, vous recevrez un code de vérification."},
            status=status.HTTP_200_OK,
        )


# =============================================================================
# STEP 2 — Verify code
# =============================================================================

class ForgotPasswordVerifyView(APIView):
    """
    POST /api/users/forgot-password/verify/

    Body : { "email": "user@example.com", "code": "483921" }

    - Vérifie le code
    - Si valide → génère un token temporaire (15 min) et le retourne
    - Si invalide → incrémente le compteur d'erreurs (max 5 tentatives)
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    MAX_ATTEMPTS = 5

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        code  = request.data.get("code", "").strip()

        if not email or not code:
            return Response(
                {"error": "Email et code sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"{RESET_CODE_PREFIX}:{email}"
        data = cache.get(cache_key)

        if not data:
            return Response(
                {"error": "Le code a expiré ou est invalide. Demandez un nouveau code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérifier le nombre de tentatives
        if data["attempts"] >= self.MAX_ATTEMPTS:
            cache.delete(cache_key)
            return Response(
                {"error": "Trop de tentatives. Demandez un nouveau code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Comparer le code
        if data["code"] != code:
            data["attempts"] += 1
            cache.set(cache_key, data, timeout=CODE_EXPIRY)
            remaining = self.MAX_ATTEMPTS - data["attempts"]
            return Response(
                {
                    "error": f"Code incorrect. {remaining} tentative(s) restante(s).",
                    "attempts_remaining": remaining,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Code valide — générer un token temporaire
        reset_token = _generate_token()
        token_key = f"{RESET_TOKEN_PREFIX}:{reset_token}"
        cache.set(token_key, {
            "user_id": data["user_id"],
            "email": email,
        }, timeout=TOKEN_EXPIRY)

        # Supprimer le code usagé
        cache.delete(cache_key)

        logger.info(f"[FORGOT PASSWORD] Code vérifié avec succès pour {email}")

        return Response(
            {
                "message": "Code vérifié. Vous pouvez maintenant réinitialiser votre mot de passe.",
                "reset_token": reset_token,
            },
            status=status.HTTP_200_OK,
        )


# =============================================================================
# STEP 3 — Reset password
# =============================================================================

class ForgotPasswordResetView(APIView):
    """
    POST /api/users/forgot-password/reset/

    Body : {
        "reset_token": "...",
        "new_password": "...",
        "new_password_confirm": "..."
    }

    - Valide le token temporaire
    - Vérifie les mots de passe
    - Met à jour le mot de passe en DB
    - Invalide tous les tokens JWT existants
    """
    permission_classes = [AllowAny]
    authentication_classes = [] 
    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        reset_token        = request.data.get("reset_token", "").strip()
        new_password       = request.data.get("new_password", "")
        new_password_confirm = request.data.get("new_password_confirm", "")

        if not reset_token or not new_password or not new_password_confirm:
            return Response(
                {"error": "Tous les champs sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Valider le token
        token_key = f"{RESET_TOKEN_PREFIX}:{reset_token}"
        token_data = cache.get(token_key)

        if not token_data:
            return Response(
                {"error": "Token invalide ou expiré. Recommencez la procédure."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérifier la correspondance des mots de passe
        if new_password != new_password_confirm:
            return Response(
                {"error": "Les deux mots de passe ne correspondent pas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Récupérer l'utilisateur
        try:
            user = User.objects.get(id=token_data["user_id"])
        except User.DoesNotExist:
            return Response(
                {"error": "Utilisateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Valider le nouveau mot de passe
        try:
            validate_password(new_password, user)
        except DjangoValidationError as e:
            return Response(
                {"error": list(e.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mettre à jour le mot de passe
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])

        # Invalider tous les tokens JWT existants
        user.increment_token_version()
        try:
            from apps.token_security.services import TokenService
            TokenService.revoke_all_user_tokens(user=user, reason="password_reset")
        except Exception as e:
            logger.warning(f"Impossible de révoquer les tokens pour {user.email}: {e}")

        # Supprimer le token temporaire
        cache.delete(token_key)

        # Envoyer un email de confirmation
        try:
            from apps.authentication.services import EmailService
            EmailService.send_password_changed_confirmation(user)
        except Exception as e:
            logger.warning(f"Email de confirmation non envoyé pour {user.email}: {e}")

        logger.info(f"[FORGOT PASSWORD] Mot de passe réinitialisé pour {user.email}")

        return Response(
            {"message": "Mot de passe réinitialisé avec succès. Vous pouvez vous connecter."},
            status=status.HTTP_200_OK,
        )