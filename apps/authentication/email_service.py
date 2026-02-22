"""
apps/authentication/email_service.py

Service d'envoi d'emails pour le flux de validation des managers.
Utilisé lors :
    - De l'inscription d'un Manager (notification à l'Admin)
    - De l'approbation d'un Manager (notification au Manager)
    - Du rejet d'un Manager (notification au Manager)
"""

import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_admin_email() -> str:
    """
    Retourne l'email de l'admin principal.
    On utilise DEFAULT_FROM_EMAIL comme destinataire admin,
    ou une valeur dédiée ADMIN_NOTIFICATION_EMAIL si définie dans settings.
    """
    return getattr(settings, "ADMIN_NOTIFICATION_EMAIL", settings.DEFAULT_FROM_EMAIL)


def _send(subject: str, html_body: str, recipient: str) -> bool:
    """
    Wrapper générique autour de send_mail.
    Retourne True si l'envoi a réussi, False sinon (sans lever d'exception).
    """
    plain_text = strip_tags(html_body)
    try:
        send_mail(
            subject=subject,
            message=plain_text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html_body,
            fail_silently=False,
        )
        logger.info(f"Email envoyé avec succès → {recipient} | Sujet : {subject}")
        return True
    except Exception as exc:
        logger.error(f"Échec d'envoi d'email → {recipient} | Sujet : {subject} | Erreur : {exc}")
        return False


# ---------------------------------------------------------------------------
# 1. Notification Admin — nouveau Manager inscrit
# ---------------------------------------------------------------------------

def notify_admin_new_manager(manager) -> bool:
    """
    Envoie un email à l'admin lorsqu'un nouveau manager s'inscrit.

    Args:
        manager : instance User (role=manager, status=pending)

    Returns:
        True si l'email a été envoyé avec succès.
    """
    admin_email = _get_admin_email()
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    verification_url = f"{frontend_url}/admin/verification"

    subject = f"[FASI] Nouvelle demande de compte Manager — {manager.full_name}"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Nouvelle demande Manager</title>
    </head>
    <body style="margin:0; padding:0; background-color:#f8fafc; font-family: 'Segoe UI', Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08);">

                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #4f46e5, #7c3aed); padding: 32px 40px; text-align:center;">
                                <div style="display:inline-block; background:rgba(255,255,255,0.15); border-radius:12px; padding:12px 20px; margin-bottom:16px;">
                                    <span style="color:#ffffff; font-size:28px; font-weight:900; letter-spacing:2px;">FASI</span>
                                </div>
                                <h1 style="color:#ffffff; margin:0; font-size:22px; font-weight:600;">
                                    Nouvelle demande de compte Manager
                                </h1>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <p style="color:#374151; font-size:16px; margin:0 0 24px;">
                                    Bonjour Administrateur,
                                </p>
                                <p style="color:#6b7280; font-size:15px; margin:0 0 28px; line-height:1.6;">
                                    Un nouveau Manager vient de créer un compte sur la plateforme FASI.
                                    Son compte est actuellement <strong style="color:#f59e0b;">en attente de validation</strong>.
                                </p>

                                <!-- Manager Info Card -->
                                <table width="100%" cellpadding="0" cellspacing="0"
                                    style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:10px; margin-bottom:32px;">
                                    <tr>
                                        <td style="padding:24px;">
                                            <p style="margin:0 0 4px; color:#9ca3af; font-size:12px; text-transform:uppercase; letter-spacing:1px;">Informations du candidat</p>
                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;">
                                                <tr>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6;">
                                                        <span style="color:#6b7280; font-size:14px;">Nom complet</span>
                                                    </td>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6; text-align:right;">
                                                        <strong style="color:#111827; font-size:14px;">{manager.full_name}</strong>
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6;">
                                                        <span style="color:#6b7280; font-size:14px;">Email</span>
                                                    </td>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6; text-align:right;">
                                                        <strong style="color:#111827; font-size:14px;">{manager.email}</strong>
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6;">
                                                        <span style="color:#6b7280; font-size:14px;">Société</span>
                                                    </td>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6; text-align:right;">
                                                        <strong style="color:#111827; font-size:14px;">{manager.company_name or "—"}</strong>
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:8px 0;">
                                                        <span style="color:#6b7280; font-size:14px;">Téléphone</span>
                                                    </td>
                                                    <td style="padding:8px 0; text-align:right;">
                                                        <strong style="color:#111827; font-size:14px;">{manager.phone_number or "—"}</strong>
                                                    </td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                </table>

                                <!-- CTA -->
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td align="center">
                                            <a href="{verification_url}"
                                               style="display:inline-block; background:linear-gradient(135deg, #4f46e5, #7c3aed);
                                                      color:#ffffff; font-size:15px; font-weight:600;
                                                      padding:14px 36px; border-radius:8px; text-decoration:none;
                                                      letter-spacing:0.3px;">
                                                Examiner la demande →
                                            </a>
                                        </td>
                                    </tr>
                                </table>

                                <p style="color:#9ca3af; font-size:13px; margin:28px 0 0; text-align:center; line-height:1.5;">
                                    Ce lien vous redirige vers la page de vérification Admin de FASI.<br>
                                    Vous pouvez approuver ou rejeter ce compte depuis l'interface.
                                </p>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background:#f9fafb; border-top:1px solid #e5e7eb; padding:20px 40px; text-align:center;">
                                <p style="color:#9ca3af; font-size:12px; margin:0;">
                                    FASI — Financial Analytics & System Intelligence<br>
                                    Cet email est automatique, merci de ne pas y répondre.
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    return _send(subject, html_body, admin_email)


# ---------------------------------------------------------------------------
# 2. Notification Manager — compte approuvé
# ---------------------------------------------------------------------------

def notify_manager_approved(manager) -> bool:
    """
    Envoie un email au manager pour l'informer que son compte a été approuvé.

    Args:
        manager : instance User (role=manager)

    Returns:
        True si l'email a été envoyé avec succès.
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    login_url = f"{frontend_url}/login"

    subject = "[FASI] Votre compte Manager a été approuvé ✓"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Compte approuvé</title>
    </head>
    <body style="margin:0; padding:0; background-color:#f8fafc; font-family: 'Segoe UI', Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08);">

                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #059669, #10b981); padding: 32px 40px; text-align:center;">
                                <div style="display:inline-block; background:rgba(255,255,255,0.15); border-radius:12px; padding:12px 20px; margin-bottom:16px;">
                                    <span style="color:#ffffff; font-size:28px; font-weight:900; letter-spacing:2px;">FASI</span>
                                </div>
                                <div style="width:56px; height:56px; background:rgba(255,255,255,0.2); border-radius:50%; margin:0 auto 12px; display:flex; align-items:center; justify-content:center;">
                                    <span style="font-size:28px;">✓</span>
                                </div>
                                <h1 style="color:#ffffff; margin:0; font-size:22px; font-weight:600;">
                                    Compte approuvé !
                                </h1>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <p style="color:#374151; font-size:16px; margin:0 0 16px;">
                                    Bonjour <strong>{manager.full_name}</strong>,
                                </p>
                                <p style="color:#6b7280; font-size:15px; margin:0 0 24px; line-height:1.6;">
                                    Bonne nouvelle ! Votre demande de compte Manager sur la plateforme FASI a été
                                    <strong style="color:#059669;">approuvée par l'administrateur</strong>.
                                    Vous pouvez maintenant vous connecter et commencer à utiliser l'application.
                                </p>

                                <!-- What you can do -->
                                <table width="100%" cellpadding="0" cellspacing="0"
                                    style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; margin-bottom:32px;">
                                    <tr>
                                        <td style="padding:24px;">
                                            <p style="margin:0 0 16px; color:#166534; font-size:14px; font-weight:600;">
                                                Ce que vous pouvez faire dès maintenant :
                                            </p>
                                            <table width="100%" cellpadding="0" cellspacing="0">
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; Accéder au tableau de bord FASI
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; Créer des comptes agents pour votre équipe
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; Consulter les rapports et analyses financières
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; Configurer les alertes pour votre société
                                                    </td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                </table>

                                <!-- CTA -->
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td align="center">
                                            <a href="{login_url}"
                                               style="display:inline-block; background:linear-gradient(135deg, #059669, #10b981);
                                                      color:#ffffff; font-size:15px; font-weight:600;
                                                      padding:14px 36px; border-radius:8px; text-decoration:none;
                                                      letter-spacing:0.3px;">
                                                Se connecter à FASI →
                                            </a>
                                        </td>
                                    </tr>
                                </table>

                                <p style="color:#9ca3af; font-size:13px; margin:28px 0 0; text-align:center;">
                                    Utilisez votre email <strong>{manager.email}</strong> et le mot de passe choisi lors de l'inscription.
                                </p>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background:#f9fafb; border-top:1px solid #e5e7eb; padding:20px 40px; text-align:center;">
                                <p style="color:#9ca3af; font-size:12px; margin:0;">
                                    FASI — Financial Analytics & System Intelligence<br>
                                    Cet email est automatique, merci de ne pas y répondre.
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    return _send(subject, html_body, manager.email)


# ---------------------------------------------------------------------------
# 3. Notification Manager — compte rejeté
# ---------------------------------------------------------------------------

def notify_manager_rejected(manager, reason: str = "") -> bool:
    """
    Envoie un email au manager pour l'informer que son compte a été rejeté.

    Args:
        manager : instance User (role=manager)
        reason  : motif de rejet renseigné par l'admin

    Returns:
        True si l'email a été envoyé avec succès.
    """
    subject = "[FASI] Votre demande de compte Manager n'a pas été acceptée"

    reason_block = ""
    if reason.strip():
        reason_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0"
            style="background:#fff7ed; border:1px solid #fed7aa; border-radius:10px; margin-bottom:28px;">
            <tr>
                <td style="padding:20px 24px;">
                    <p style="margin:0 0 8px; color:#9a3412; font-size:14px; font-weight:600;">
                        Motif communiqué par l'administrateur :
                    </p>
                    <p style="margin:0; color:#c2410c; font-size:14px; line-height:1.6; font-style:italic;">
                        "{reason}"
                    </p>
                </td>
            </tr>
        </table>
        """

    html_body = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Demande refusée</title>
    </head>
    <body style="margin:0; padding:0; background-color:#f8fafc; font-family: 'Segoe UI', Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08);">

                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #dc2626, #ef4444); padding: 32px 40px; text-align:center;">
                                <div style="display:inline-block; background:rgba(255,255,255,0.15); border-radius:12px; padding:12px 20px; margin-bottom:16px;">
                                    <span style="color:#ffffff; font-size:28px; font-weight:900; letter-spacing:2px;">FASI</span>
                                </div>
                                <h1 style="color:#ffffff; margin:0; font-size:22px; font-weight:600;">
                                    Demande non acceptée
                                </h1>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <p style="color:#374151; font-size:16px; margin:0 0 16px;">
                                    Bonjour <strong>{manager.full_name}</strong>,
                                </p>
                                <p style="color:#6b7280; font-size:15px; margin:0 0 24px; line-height:1.6;">
                                    Après examen de votre dossier, nous sommes dans l'impossibilité
                                    d'approuver votre demande de compte Manager sur la plateforme FASI.
                                </p>

                                {reason_block}

                                <p style="color:#6b7280; font-size:14px; margin:0 0 0; line-height:1.6;">
                                    Si vous pensez qu'il s'agit d'une erreur ou si vous souhaitez obtenir
                                    plus d'informations, veuillez contacter directement l'administrateur FASI.
                                </p>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background:#f9fafb; border-top:1px solid #e5e7eb; padding:20px 40px; text-align:center;">
                                <p style="color:#9ca3af; font-size:12px; margin:0;">
                                    FASI — Financial Analytics & System Intelligence<br>
                                    Cet email est automatique, merci de ne pas y répondre.
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    return _send(subject, html_body, manager.email)