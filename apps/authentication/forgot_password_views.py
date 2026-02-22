"""
apps/authentication/forgot_password_views.py

Password reset via verification code (for managers and agents).
Flow:
    1. POST /api/users/forgot-password/request/
       → Check email, generate 6-digit code, send via email
    2. POST /api/users/forgot-password/verify/
       → Verify code, return temporary token if valid
    3. POST /api/users/forgot-password/reset/
       → Receive token + new password, update in DB
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
    """Generate a random numeric code."""
    return ''.join(random.choices(string.digits, k=length))


def _generate_token(length=32) -> str:
    """Generate a secure alphanumeric token."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _send_reset_code_email(user, code: str) -> bool:
    """Send the email containing the verification code."""
    subject = "[WEEG] Password Reset Verification Code"

    text_content = (
        f"Hello {user.first_name},\n\n"
        f"Your verification code is: {code}\n\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not request this reset, please ignore this email.\n\n"
        f"Best regards,\nThe WEEG team"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
      <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
        <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:30px;text-align:center;">
          <h1 style="color:#fff;margin:0;font-size:28px;font-weight:bold;">WEEG</h1>
        </div>
        <div style="padding:30px;">
          <h2 style="color:#1e293b;">🔐 Password Reset</h2>
          <p style="color:#475569;">Hello <strong>{user.first_name}</strong>,</p>
          <p style="color:#475569;">
            You requested a password reset.
            Here is your verification code:
          </p>

          <!-- Code Block -->
          <div style="text-align:center;margin:32px 0;">
            <div style="display:inline-block;background:#f0f4ff;border:2px dashed #4f46e5;border-radius:12px;padding:20px 40px;">
              <p style="margin:0 0 8px;color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:1px;">Verification Code</p>
              <span style="font-family:monospace;font-size:40px;font-weight:900;color:#4f46e5;letter-spacing:8px;">
                {code}
              </span>
            </div>
          </div>

          <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin:16px 0;text-align:center;">
            <p style="color:#92400e;margin:0;">⏱️ This code expires in <strong>10 minutes</strong></p>
          </div>

          <p style="color:#94a3b8;font-size:13px;text-align:center;">
            If you did not request this reset, please ignore this email.<br>
            Your password will remain unchanged.
          </p>
        </div>
        <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
          <p style="color:#94a3b8;font-size:12px;margin:0;">Automatic WEEG email — Do not reply.</p>
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
        logger.error(f"Failed to send reset code email to {user.email}: {e}")
        return False


# =============================================================================
# STEP 1 — Request code
# =============================================================================

class ForgotPasswordRequestView(APIView):
    """
    POST /api/users/forgot-password/request/

    Body: { "email": "user@example.com" }

    - Checks if the email exists
    - Generates a 6-digit code
    - Stores the code in cache (10 min)
    - Sends the code by email

    Response: always 200 (to avoid leaking whether the email exists)
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response(
                {"error": "Email address is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Silent lookup — do not reveal if email exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Generic response for security
            return Response(
                {"message": "If this email is registered, you will receive a verification code."},
                status=status.HTTP_200_OK,
            )

        # Check if account can reset (not rejected)
        if user.status == User.AccountStatus.REJECTED:
            return Response(
                {"error": "This account has been rejected. Contact an administrator."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Generate and store code
        code = _generate_code()
        cache_key = f"{RESET_CODE_PREFIX}:{email}"
        cache.set(cache_key, {
            "code": code,
            "user_id": str(user.id),
            "attempts": 0,
        }, timeout=CODE_EXPIRY)

        # Send email
        _send_reset_code_email(user, code)

        logger.info(f"[FORGOT PASSWORD] Code sent to {email}")

        return Response(
            {"message": "If this email is registered, you will receive a verification code."},
            status=status.HTTP_200_OK,
        )


# =============================================================================
# STEP 2 — Verify code
# =============================================================================

class ForgotPasswordVerifyView(APIView):
    """
    POST /api/users/forgot-password/verify/

    Body: { "email": "user@example.com", "code": "483921" }

    - Verifies the code
    - If valid → generates a temporary token (15 min) and returns it
    - If invalid → increments attempt counter (max 5 attempts)
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    MAX_ATTEMPTS = 5

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        code  = request.data.get("code", "").strip()

        if not email or not code:
            return Response(
                {"error": "Email and code are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"{RESET_CODE_PREFIX}:{email}"
        data = cache.get(cache_key)

        if not data:
            return Response(
                {"error": "Code has expired or is invalid. Request a new code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check attempt limit
        if data["attempts"] >= self.MAX_ATTEMPTS:
            cache.delete(cache_key)
            return Response(
                {"error": "Too many attempts. Please request a new code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Compare code
        if data["code"] != code:
            data["attempts"] += 1
            cache.set(cache_key, data, timeout=CODE_EXPIRY)
            remaining = self.MAX_ATTEMPTS - data["attempts"]
            return Response(
                {
                    "error": f"Incorrect code. {remaining} attempt(s) remaining.",
                    "attempts_remaining": remaining,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Valid code — generate temporary token
        reset_token = _generate_token()
        token_key = f"{RESET_TOKEN_PREFIX}:{reset_token}"
        cache.set(token_key, {
            "user_id": data["user_id"],
            "email": email,
        }, timeout=TOKEN_EXPIRY)

        # Remove used code
        cache.delete(cache_key)

        logger.info(f"[FORGOT PASSWORD] Code successfully verified for {email}")

        return Response(
            {
                "message": "Code verified. You can now reset your password.",
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

    Body: {
        "reset_token": "...",
        "new_password": "...",
        "new_password_confirm": "..."
    }

    - Validates the temporary token
    - Checks passwords match
    - Updates password in DB
    - Invalidates all existing JWT tokens
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
                {"error": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate token
        token_key = f"{RESET_TOKEN_PREFIX}:{reset_token}"
        token_data = cache.get(token_key)

        if not token_data:
            return Response(
                {"error": "Invalid or expired token. Please start over."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check password match
        if new_password != new_password_confirm:
            return Response(
                {"error": "The two passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Retrieve user
        try:
            user = User.objects.get(id=token_data["user_id"])
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate new password
        try:
            validate_password(new_password, user)
        except DjangoValidationError as e:
            return Response(
                {"error": list(e.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update password
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])

        # Invalidate all existing JWT tokens
        user.increment_token_version()
        try:
            from apps.token_security.services import TokenService
            TokenService.revoke_all_user_tokens(user=user, reason="password_reset")
        except Exception as e:
            logger.warning(f"Failed to revoke tokens for {user.email}: {e}")

        # Remove temporary token
        cache.delete(token_key)

        # Send confirmation email
        try:
            from apps.authentication.services import EmailService
            EmailService.send_password_changed_confirmation(user)
        except Exception as e:
            logger.warning(f"Confirmation email not sent for {user.email}: {e}")

        logger.info(f"[FORGOT PASSWORD] Password reset successful for {user.email}")

        return Response(
            {"message": "Password reset successfully. You can now log in."},
            status=status.HTTP_200_OK,
        )