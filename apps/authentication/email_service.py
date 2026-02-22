"""
apps/authentication/email_service.py

Email sending service for the manager validation flow.
Used when:
    - A Manager registers (notification to Admin)
    - A Manager is approved (notification to Manager)
    - A Manager is rejected (notification to Manager)
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
    Returns the main admin email.
    Uses DEFAULT_FROM_EMAIL as fallback, or ADMIN_NOTIFICATION_EMAIL if defined in settings.
    """
    return getattr(settings, "ADMIN_NOTIFICATION_EMAIL", settings.DEFAULT_FROM_EMAIL)


def _send(subject: str, html_body: str, recipient: str) -> bool:
    """
    Generic wrapper around send_mail.
    Returns True if sending succeeded, False otherwise (no exception raised).
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
        logger.info(f"Email sent successfully → {recipient} | Subject: {subject}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send email → {recipient} | Subject: {subject} | Error: {exc}")
        return False


# ---------------------------------------------------------------------------
# 1. Notify Admin — new Manager registered
# ---------------------------------------------------------------------------

def notify_admin_new_manager(manager) -> bool:
    """
    Sends an email to the admin when a new manager registers.

    Args:
        manager: User instance (role=manager, status=pending)

    Returns:
        True if the email was sent successfully.
    """
    admin_email = _get_admin_email()
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    verification_url = f"{frontend_url}/admin/verification"

    subject = f"[WEEG] New Manager Account Request — {manager.full_name}"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>New Manager Request</title>
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
                                    <span style="color:#ffffff; font-size:28px; font-weight:900; letter-spacing:2px;">WEEG</span>
                                </div>
                                <h1 style="color:#ffffff; margin:0; font-size:22px; font-weight:600;">
                                    New Manager Account Request
                                </h1>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <p style="color:#374151; font-size:16px; margin:0 0 24px;">
                                    Hello Administrator,
                                </p>
                                <p style="color:#6b7280; font-size:15px; margin:0 0 28px; line-height:1.6;">
                                    A new Manager has just created an account on the WEEG platform.
                                    Their account is currently <strong style="color:#f59e0b;">pending approval</strong>.
                                </p>

                                <!-- Manager Info Card -->
                                <table width="100%" cellpadding="0" cellspacing="0"
                                    style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:10px; margin-bottom:32px;">
                                    <tr>
                                        <td style="padding:24px;">
                                            <p style="margin:0 0 4px; color:#9ca3af; font-size:12px; text-transform:uppercase; letter-spacing:1px;">Candidate Information</p>
                                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;">
                                                <tr>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6;">
                                                        <span style="color:#6b7280; font-size:14px;">Full name</span>
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
                                                        <span style="color:#6b7280; font-size:14px;">Company</span>
                                                    </td>
                                                    <td style="padding:8px 0; border-bottom:1px solid #f3f4f6; text-align:right;">
                                                        <strong style="color:#111827; font-size:14px;">{manager.company_name or "—"}</strong>
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:8px 0;">
                                                        <span style="color:#6b7280; font-size:14px;">Phone</span>
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
                                                Review Request →
                                            </a>
                                        </td>
                                    </tr>
                                </table>

                                <p style="color:#9ca3af; font-size:13px; margin:28px 0 0; text-align:center; line-height:1.5;">
                                    This link redirects you to the WEEG Admin verification page.<br>
                                    You can approve or reject this account from the interface.
                                </p>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background:#f9fafb; border-top:1px solid #e5e7eb; padding:20px 40px; text-align:center;">
                                <p style="color:#9ca3af; font-size:12px; margin:0;">
                                    WEEG — Financial Analytics & System Intelligence<br>
                                    This is an automated email, please do not reply.
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
# 2. Notify Manager — account approved
# ---------------------------------------------------------------------------

def notify_manager_approved(manager) -> bool:
    """
    Sends an email to the manager informing them that their account has been approved.

    Args:
        manager: User instance (role=manager)

    Returns:
        True if the email was sent successfully.
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    login_url = f"{frontend_url}/login"

    subject = "[WEEG] Your Manager Account Has Been Approved ✓"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Account Approved</title>
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
                                    <span style="color:#ffffff; font-size:28px; font-weight:900; letter-spacing:2px;">WEEG</span>
                                </div>
                                <div style="width:56px; height:56px; background:rgba(255,255,255,0.2); border-radius:50%; margin:0 auto 12px; display:flex; align-items:center; justify-content:center;">
                                    <span style="font-size:28px;">✓</span>
                                </div>
                                <h1 style="color:#ffffff; margin:0; font-size:22px; font-weight:600;">
                                    Account Approved!
                                </h1>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <p style="color:#374151; font-size:16px; margin:0 0 16px;">
                                    Hello <strong>{manager.full_name}</strong>,
                                </p>
                                <p style="color:#6b7280; font-size:15px; margin:0 0 24px; line-height:1.6;">
                                    Great news! Your Manager account request on the WEEG platform has been
                                    <strong style="color:#059669;">approved by the administrator</strong>.
                                    You can now log in and start using the application.
                                </p>

                                <!-- What you can do -->
                                <table width="100%" cellpadding="0" cellspacing="0"
                                    style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; margin-bottom:32px;">
                                    <tr>
                                        <td style="padding:24px;">
                                            <p style="margin:0 0 16px; color:#166534; font-size:14px; font-weight:600;">
                                                What you can do right now:
                                            </p>
                                            <table width="100%" cellpadding="0" cellspacing="0">
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; Access the WEEG dashboard
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; Create agent accounts for your team
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; View financial reports and analytics
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding:6px 0; color:#166534; font-size:14px;">
                                                        ✓ &nbsp; Set up alerts for your company
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
                                                Log in to WEEG →
                                            </a>
                                        </td>
                                    </tr>
                                </table>

                                <p style="color:#9ca3af; font-size:13px; margin:28px 0 0; text-align:center;">
                                    Use your email <strong>{manager.email}</strong> and the password you chose during registration.
                                </p>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background:#f9fafb; border-top:1px solid #e5e7eb; padding:20px 40px; text-align:center;">
                                <p style="color:#9ca3af; font-size:12px; margin:0;">
                                    WEEG — Financial Analytics & System Intelligence<br>
                                    This is an automated email, please do not reply.
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
# 3. Notify Manager — account rejected
# ---------------------------------------------------------------------------

def notify_manager_rejected(manager, reason: str = "") -> bool:
    """
    Sends an email to the manager informing them that their account request was rejected.

    Args:
        manager: User instance (role=manager)
        reason: rejection reason provided by the admin

    Returns:
        True if the email was sent successfully.
    """
    subject = "[WEEG] Your Manager Account Request Was Not Accepted"

    reason_block = ""
    if reason.strip():
        reason_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0"
            style="background:#fff7ed; border:1px solid #fed7aa; border-radius:10px; margin-bottom:28px;">
            <tr>
                <td style="padding:20px 24px;">
                    <p style="margin:0 0 8px; color:#9a3412; font-size:14px; font-weight:600;">
                        Reason provided by the administrator:
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
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Request Denied</title>
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
                                    <span style="color:#ffffff; font-size:28px; font-weight:900; letter-spacing:2px;">WEEG</span>
                                </div>
                                <h1 style="color:#ffffff; margin:0; font-size:22px; font-weight:600;">
                                    Request Not Accepted
                                </h1>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding: 40px;">
                                <p style="color:#374151; font-size:16px; margin:0 0 16px;">
                                    Hello <strong>{manager.full_name}</strong>,
                                </p>
                                <p style="color:#6b7280; font-size:15px; margin:0 0 24px; line-height:1.6;">
                                    After reviewing your application, we are unable to approve
                                    your Manager account request on the WEEG platform.
                                </p>

                                {reason_block}

                                <p style="color:#6b7280; font-size:14px; margin:0 0 0; line-height:1.6;">
                                    If you believe this is an error or would like more information,
                                    please contact the WEEG administrator directly.
                                </p>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background:#f9fafb; border-top:1px solid #e5e7eb; padding:20px 40px; text-align:center;">
                                <p style="color:#9ca3af; font-size:12px; margin:0;">
                                    WEEG — Financial Analytics & System Intelligence<br>
                                    This is an automated email, please do not reply.
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