# import logging
# from django.conf import settings
# from django.contrib.auth import get_user_model
# from django.core.mail import send_mail

# from apps.token_security.services import TokenService

# logger = logging.getLogger("django")
# User = get_user_model()


# class EmailService:
#     """
#     Service centralisé pour l'envoi de tous les emails du système.
#     """

#     @staticmethod
#     def send_admin_new_manager_request(manager: User) -> None:
#         """
#         Envoie un email à TOUS les admins pour signaler qu'un nouveau manager
#         vient de s'inscrire et attend validation.
#         """
#         admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
#         admin_emails = list(admins.values_list("email", flat=True))

#         if not admin_emails:
#             logger.warning(
#                 f"Aucun admin actif trouvé pour recevoir la notification "
#                 f"de la demande du manager [{manager.email}]."
#             )
#             return

#         company_name = manager.company_name or "Non renseignée"

#         subject = f"[FASI] Nouvelle demande d'accès Manager — {manager.full_name}"
#         message = (
#             f"Bonjour,\n\n"
#             f"Un nouveau manager vient de s'inscrire et attend votre approbation.\n\n"
#             f"Nom      : {manager.full_name}\n"
#             f"Email    : {manager.email}\n"
#             f"Téléphone : {manager.phone_number or 'Non renseigné'}\n"
#             f"Société  : {company_name}\n\n"
#             f"Pour approuver ou rejeter cette demande, connectez-vous à l'interface d'administration.\n\n"
#             f"Cordialement,\nLe système FASI"
#         )

#         send_mail(
#             subject=subject,
#             message=message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=admin_emails,
#             fail_silently=False,
#         )

#         logger.info(
#             f"Email de notification envoyé à {len(admin_emails)} admin(s) "
#             f"pour la demande du manager [{manager.email}]."
#         )

#     @staticmethod
#     def send_manager_approved(manager: User) -> None:
#         """Envoie un email au manager pour confirmer l'approbation de son compte."""
#         subject = "[FASI] Votre compte a été approuvé — Vous pouvez maintenant vous connecter"
#         message = (
#             f"Bonjour {manager.first_name},\n\n"
#             f"Bonne nouvelle ! Votre demande d'accès à la plateforme FASI a été approuvée.\n\n"
#             f"Vous pouvez maintenant vous connecter avec votre adresse email : {manager.email}\n\n"
#             f"Cordialement,\nL'équipe FASI"
#         )
#         send_mail(
#             subject=subject,
#             message=message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[manager.email],
#             fail_silently=False,
#         )

#     @staticmethod
#     def send_manager_rejected(manager: User, reason: str) -> None:
#         """Envoie un email au manager pour l'informer du rejet."""
#         subject = "[FASI] Votre demande d'accès n'a pas été approuvée"
#         message = (
#             f"Bonjour {manager.first_name},\n\n"
#             f"Nous avons examiné votre demande d'accès à la plateforme FASI.\n\n"
#             f"Malheureusement, votre demande n'a pas pu être approuvée pour la raison suivante :\n"
#             f"{reason}\n\n"
#             f"Pour toute question, contactez votre administrateur.\n\n"
#             f"Cordialement,\nL'équipe FASI"
#         )
#         send_mail(
#             subject=subject,
#             message=message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[manager.email],
#             fail_silently=False,
#         )

#     @staticmethod
#     def send_agent_credentials(agent: User, temporary_password: str, created_by: User) -> None:
#         """Envoie les identifiants de connexion à un agent nouvellement créé."""
#         company_name = agent.company_name or "FASI"
#         subject = f"[FASI] Votre compte agent a été créé — {agent.full_name}"
#         message = (
#             f"Bonjour {agent.first_name},\n\n"
#             f"Votre compte agent sur la plateforme FASI a été créé par {created_by.full_name}.\n"
#             f"Société : {company_name}\n\n"
#             f"Vos identifiants de connexion :\n"
#             f"  Email         : {agent.email}\n"
#             f"  Mot de passe  : {temporary_password}\n\n"
#             f"IMPORTANT : Vous devrez changer ce mot de passe temporaire lors de votre première connexion.\n\n"
#             f"Cordialement,\nL'équipe FASI"
#         )
#         send_mail(
#             subject=subject,
#             message=message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[agent.email],
#             fail_silently=False,
#         )

#     @staticmethod
#     def send_password_reset_link(user: User, reset_token: str) -> None:
#         """Envoie un lien de réinitialisation de mot de passe."""
#         frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
#         reset_link = f"{frontend_url}/reset-password?token={reset_token}"

#         subject = "[FASI] Réinitialisation de votre mot de passe"
#         message = (
#             f"Bonjour {user.first_name},\n\n"
#             f"Une demande de réinitialisation de mot de passe a été effectuée pour votre compte.\n\n"
#             f"Cliquez sur le lien ci-dessous pour définir un nouveau mot de passe :\n"
#             f"{reset_link}\n\n"
#             f"Ce lien est valable pendant 1 heure et ne peut être utilisé qu'une seule fois.\n\n"
#             f"Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.\n\n"
#             f"Cordialement,\nL'équipe FASI"
#         )
#         send_mail(
#             subject=subject,
#             message=message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[user.email],
#             fail_silently=False,
#         )

#     @staticmethod
#     def send_password_changed_confirmation(user: User) -> None:
#         """Envoie une confirmation après un changement réussi de mot de passe."""
#         subject = "[FASI] Votre mot de passe a été modifié"
#         message = (
#             f"Bonjour {user.first_name},\n\n"
#             f"Votre mot de passe a été modifié avec succès.\n\n"
#             f"Si vous n'êtes pas à l'origine de cette modification, "
#             f"contactez immédiatement votre administrateur.\n\n"
#             f"Cordialement,\nL'équipe FASI"
#         )
#         send_mail(
#             subject=subject,
#             message=message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             recipient_list=[user.email],
#             fail_silently=False,
#         )


# class UserService:
#     """
#     Service centralisé pour les opérations métier sur les utilisateurs.
#     """

#     @staticmethod
#     def approve_manager(manager: User, admin: User) -> None:
#         """Approuve le compte d'un manager en attente."""
#         manager.approve()
#         EmailService.send_manager_approved(manager)
#         logger.info(f"Manager [{manager.email}] approuvé par l'admin [{admin.email}].")

#     @staticmethod
#     def reject_manager(manager: User, admin: User, reason: str) -> None:
#         """Rejette la demande d'accès d'un manager."""
#         manager.reject(reason=reason)
#         EmailService.send_manager_rejected(manager=manager, reason=reason)
#         logger.info(f"Manager [{manager.email}] rejeté par l'admin [{admin.email}]. Motif : {reason}.")

#     @staticmethod
#     def create_agent(validated_data: dict, manager: User, temporary_password: str) -> User:
#         """
#         Crée un compte agent et envoie ses identifiants par email.
#         La Company de l'agent est automatiquement celle du Manager.
#         """
#         validated_data.pop("temporary_password", None)

#         agent = User(
#             role=User.Role.AGENT,
#             status=User.AccountStatus.ACTIVE,
#             is_verified=True,
#             must_change_password=True,
#             created_by=manager,
#             # Hérite automatiquement de la Company du Manager
#             company=manager.company,
#             **validated_data,
#         )
#         agent.set_password(temporary_password)
#         agent.save()

#         EmailService.send_agent_credentials(
#             agent=agent,
#             temporary_password=temporary_password,
#             created_by=manager,
#         )

#         logger.info(f"Agent [{agent.email}] créé par le manager [{manager.email}].")
#         return agent

#     @staticmethod
#     def change_password(user: User, new_password: str, request) -> None:
#         """Change le mot de passe et invalide tous les tokens existants."""
#         user.set_password(new_password)
#         user.must_change_password = False
#         user.save(update_fields=["password", "must_change_password", "updated_at"])
#         user.increment_token_version()
#         TokenService.revoke_all_user_tokens(user=user, reason="password_changed")
#         EmailService.send_password_changed_confirmation(user=user)
#         logger.info(f"Mot de passe changé pour [{user.email}].")

#     @staticmethod
#     def reset_password(user: User, new_password: str) -> None:
#         """Réinitialise le mot de passe après validation du token temporaire."""
#         user.set_password(new_password)
#         user.save(update_fields=["password", "updated_at"])
#         user.increment_token_version()
#         TokenService.revoke_all_user_tokens(user=user, reason="password_reset")
#         EmailService.send_password_changed_confirmation(user=user)
#         logger.info(f"Mot de passe réinitialisé pour [{user.email}].")

#     @staticmethod
#     def request_password_reset(target_user: User, requesting_user: User) -> None:
#         """Génère un token temporaire et envoie le lien de reset par email."""
#         reset_token = TokenService.issue_temporary_token(
#             user=target_user,
#             action="password_reset",
#         )
#         EmailService.send_password_reset_link(user=target_user, reset_token=reset_token)
#         logger.info(
#             f"Lien de reset envoyé à [{target_user.email}] par [{requesting_user.email}]."
#         )
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger("django")
User = get_user_model()


class EmailService:

    @staticmethod
    def send_admin_new_manager_request(manager: User) -> None:
        """
        Envoie un email HTML aux admins avec un bouton de redirection vers l'app.
        """
        admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
        admin_emails = list(admins.values_list("email", flat=True))

        if not admin_emails:
            logger.warning(f"Aucun admin actif trouvé pour notifier [{manager.email}].")
            return

        company_name = manager.company_name or "Non renseignée"
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        admin_url = f"{frontend_url}/dashboard/admin-verification"

        subject = f"[FASI] Nouvelle demande d'accès Manager — {manager.full_name}"

        # Version texte (fallback)
        text_content = (
            f"Bonjour,\n\n"
            f"Un nouveau manager vient de s'inscrire et attend votre approbation.\n\n"
            f"Nom      : {manager.full_name}\n"
            f"Email    : {manager.email}\n"
            f"Téléphone: {manager.phone_number or 'Non renseigné'}\n"
            f"Société  : {company_name}\n\n"
            f"Pour approuver ou rejeter cette demande, cliquez ici :\n{admin_url}\n\n"
            f"Cordialement,\nLe système FASI"
        )

        # Version HTML avec bouton
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"></head>
        <body style="font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:20px;">
          <div style="max-width:600px; margin:0 auto; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed); padding:30px; text-align:center;">
              <h1 style="color:#fff; margin:0; font-size:28px; font-weight:bold;">FASI</h1>
              <p style="color:#c7d2fe; margin:8px 0 0;">Financial Analytics & System Intelligence</p>
            </div>

            <!-- Body -->
            <div style="padding:30px;">
              <h2 style="color:#1e293b; margin-top:0;">🔔 Nouvelle demande d'accès Manager</h2>
              <p style="color:#475569;">Un nouveau manager vient de créer un compte et attend votre approbation.</p>

              <!-- Info Card -->
              <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:20px; margin:20px 0;">
                <table style="width:100%; border-collapse:collapse;">
                  <tr>
                    <td style="padding:8px 0; color:#64748b; width:120px;">👤 Nom</td>
                    <td style="padding:8px 0; color:#1e293b; font-weight:bold;">{manager.full_name}</td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0; color:#64748b;">📧 Email</td>
                    <td style="padding:8px 0; color:#1e293b;">{manager.email}</td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0; color:#64748b;">📞 Téléphone</td>
                    <td style="padding:8px 0; color:#1e293b;">{manager.phone_number or 'Non renseigné'}</td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0; color:#64748b;">🏢 Société</td>
                    <td style="padding:8px 0; color:#1e293b;">{company_name}</td>
                  </tr>
                </table>
              </div>

              <!-- CTA Button -->
              <div style="text-align:center; margin:30px 0;">
                <a href="{admin_url}"
                   style="display:inline-block; background:linear-gradient(135deg,#4f46e5,#7c3aed); color:#fff;
                          text-decoration:none; padding:14px 32px; border-radius:8px; font-weight:bold;
                          font-size:16px; letter-spacing:0.5px;">
                  ✅ Gérer la demande dans FASI
                </a>
              </div>

              <p style="color:#94a3b8; font-size:13px; text-align:center;">
                Ou copiez ce lien : <a href="{admin_url}" style="color:#4f46e5;">{admin_url}</a>
              </p>
            </div>

            <!-- Footer -->
            <div style="background:#f8fafc; padding:20px; text-align:center; border-top:1px solid #e2e8f0;">
              <p style="color:#94a3b8; font-size:12px; margin:0;">
                Cet email a été envoyé automatiquement par le système FASI.<br>
                Ne pas répondre à cet email.
              </p>
            </div>
          </div>
        </body>
        </html>
        """

        # msg = EmailMultiAlternatives(
        #     subject=subject,
        #     body=text_content,
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     to=admin_emails,
        # )
        from django.core.mail import get_connection
        connection = get_connection(timeout=5)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=admin_emails,
            connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info(f"Email envoyé à {len(admin_emails)} admin(s) pour [{manager.email}].")

    @staticmethod
    def send_manager_approved(manager: User) -> None:
        subject = "[FASI] Votre compte a été approuvé — Vous pouvez vous connecter"
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        login_url = f"{frontend_url}/login"

        text_content = (
            f"Bonjour {manager.first_name},\n\n"
            f"Votre compte Manager FASI a été approuvé.\n"
            f"Connectez-vous ici : {login_url}\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:30px;text-align:center;">
              <h1 style="color:#fff;margin:0;">FASI</h1>
            </div>
            <div style="padding:30px;">
              <h2 style="color:#16a34a;">✅ Compte approuvé !</h2>
              <p style="color:#475569;">Bonjour <strong>{manager.first_name}</strong>,</p>
              <p style="color:#475569;">Bonne nouvelle ! Votre compte Manager sur la plateforme FASI a été <strong>approuvé</strong>.</p>
              <p style="color:#475569;">Vous pouvez maintenant vous connecter et commencer à utiliser la plateforme.</p>
              <div style="text-align:center;margin:30px 0;">
                <a href="{login_url}"
                   style="display:inline-block;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;
                          text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:bold;font-size:16px;">
                  Se connecter à FASI
                </a>
              </div>
            </div>
            <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
              <p style="color:#94a3b8;font-size:12px;margin:0;">Email automatique FASI — Ne pas répondre.</p>
            </div>
          </div>
        </body>
        </html>
        """

        msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [manager.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

    @staticmethod
    def send_manager_rejected(manager: User, reason: str) -> None:
        subject = "[FASI] Votre demande d'accès n'a pas été approuvée"

        text_content = (
            f"Bonjour {manager.first_name},\n\n"
            f"Votre demande d'accès FASI n'a pas été approuvée.\n"
            f"Motif : {reason}\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:30px;text-align:center;">
              <h1 style="color:#fff;margin:0;">FASI</h1>
            </div>
            <div style="padding:30px;">
              <h2 style="color:#dc2626;">❌ Demande non approuvée</h2>
              <p style="color:#475569;">Bonjour <strong>{manager.first_name}</strong>,</p>
              <p style="color:#475569;">Nous avons examiné votre demande d'accès à la plateforme FASI.</p>
              <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin:20px 0;">
                <p style="color:#dc2626;margin:0;"><strong>Motif du refus :</strong></p>
                <p style="color:#7f1d1d;margin:8px 0 0;">{reason}</p>
              </div>
              <p style="color:#475569;">Pour toute question, contactez votre administrateur.</p>
            </div>
            <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
              <p style="color:#94a3b8;font-size:12px;margin:0;">Email automatique FASI — Ne pas répondre.</p>
            </div>
          </div>
        </body>
        </html>
        """

        msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [manager.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

    @staticmethod
    def send_agent_credentials(agent: User, temporary_password: str, created_by: User) -> None:
        company_name = agent.company_name or "FASI"
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        login_url = f"{frontend_url}/login"
        subject = f"[FASI] Votre compte agent a été créé"

        text_content = (
            f"Bonjour {agent.first_name},\n\n"
            f"Votre compte agent FASI a été créé par {created_by.full_name}.\n"
            f"Email : {agent.email}\n"
            f"Mot de passe temporaire : {temporary_password}\n\n"
            f"Connectez-vous ici : {login_url}\n"
            f"IMPORTANT : Changez votre mot de passe à la première connexion.\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:30px;text-align:center;">
              <h1 style="color:#fff;margin:0;">FASI</h1>
            </div>
            <div style="padding:30px;">
              <h2 style="color:#1e293b;">🎉 Bienvenue sur FASI !</h2>
              <p style="color:#475569;">Bonjour <strong>{agent.first_name}</strong>,</p>
              <p style="color:#475569;">Votre compte agent a été créé par <strong>{created_by.full_name}</strong> ({company_name}).</p>

              <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;margin:20px 0;">
                <p style="color:#15803d;font-weight:bold;margin:0 0 12px;">Vos identifiants de connexion :</p>
                <table style="width:100%;">
                  <tr>
                    <td style="color:#64748b;padding:4px 0;">📧 Email :</td>
                    <td style="color:#1e293b;font-weight:bold;">{agent.email}</td>
                  </tr>
                  <tr>
                    <td style="color:#64748b;padding:4px 0;">🔑 Mot de passe :</td>
                    <td style="color:#1e293b;font-weight:bold;font-family:monospace;font-size:16px;">{temporary_password}</td>
                  </tr>
                </table>
              </div>

              <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin:16px 0;">
                <p style="color:#92400e;margin:0;">⚠️ <strong>Important :</strong> Vous devrez changer ce mot de passe temporaire lors de votre première connexion.</p>
              </div>

              <div style="text-align:center;margin:30px 0;">
                <a href="{login_url}"
                   style="display:inline-block;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;
                          text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:bold;font-size:16px;">
                  Se connecter à FASI
                </a>
              </div>
            </div>
            <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
              <p style="color:#94a3b8;font-size:12px;margin:0;">Email automatique FASI — Ne pas répondre.</p>
            </div>
          </div>
        </body>
        </html>
        """

        msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [agent.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

    @staticmethod
    def send_password_reset_link(user: User, reset_token: str) -> None:
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"
        subject = "[FASI] Réinitialisation de votre mot de passe"

        text_content = (
            f"Bonjour {user.first_name},\n\n"
            f"Cliquez ici pour réinitialiser votre mot de passe :\n{reset_link}\n\n"
            f"Ce lien est valable 1 heure.\n\nCordialement,\nL'équipe FASI"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:30px;text-align:center;">
              <h1 style="color:#fff;margin:0;">FASI</h1>
            </div>
            <div style="padding:30px;">
              <h2 style="color:#1e293b;">🔐 Réinitialisation du mot de passe</h2>
              <p style="color:#475569;">Bonjour <strong>{user.first_name}</strong>,</p>
              <p style="color:#475569;">Une demande de réinitialisation de mot de passe a été effectuée pour votre compte.</p>
              <div style="text-align:center;margin:30px 0;">
                <a href="{reset_link}"
                   style="display:inline-block;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;
                          text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:bold;font-size:16px;">
                  Réinitialiser mon mot de passe
                </a>
              </div>
              <p style="color:#94a3b8;font-size:13px;text-align:center;">⏱️ Ce lien expire dans <strong>1 heure</strong>.</p>
              <p style="color:#94a3b8;font-size:13px;text-align:center;">Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>
            </div>
            <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
              <p style="color:#94a3b8;font-size:12px;margin:0;">Email automatique FASI — Ne pas répondre.</p>
            </div>
          </div>
        </body>
        </html>
        """

        msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

    @staticmethod
    def send_password_changed_confirmation(user: User) -> None:
        subject = "[FASI] Votre mot de passe a été modifié"

        text_content = (
            f"Bonjour {user.first_name},\n\n"
            f"Votre mot de passe a été modifié avec succès.\n"
            f"Si ce n'est pas vous, contactez immédiatement votre administrateur.\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
          <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:30px;text-align:center;">
              <h1 style="color:#fff;margin:0;">FASI</h1>
            </div>
            <div style="padding:30px;">
              <h2 style="color:#16a34a;">🔒 Mot de passe modifié</h2>
              <p style="color:#475569;">Bonjour <strong>{user.first_name}</strong>,</p>
              <p style="color:#475569;">Votre mot de passe a été modifié avec succès.</p>
              <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px;margin:16px 0;">
                <p style="color:#dc2626;margin:0;">⚠️ Si vous n'êtes pas à l'origine de cette modification, contactez immédiatement votre administrateur.</p>
              </div>
            </div>
            <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;">
              <p style="color:#94a3b8;font-size:12px;margin:0;">Email automatique FASI — Ne pas répondre.</p>
            </div>
          </div>
        </body>
        </html>
        """

        msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)


class UserService:
    @staticmethod
    def approve_manager(manager: User, admin: User) -> None:
        manager.approve()
        EmailService.send_manager_approved(manager)
        logger.info(f"Manager [{manager.email}] approuvé par [{admin.email}].")

    @staticmethod
    def reject_manager(manager: User, admin: User, reason: str) -> None:
        manager.reject(reason=reason)
        EmailService.send_manager_rejected(manager=manager, reason=reason)
        logger.info(f"Manager [{manager.email}] rejeté par [{admin.email}]. Motif : {reason}.")

    @staticmethod
    def create_agent(validated_data: dict, manager: User, temporary_password: str) -> User:
        validated_data.pop("temporary_password", None)
        agent = User(
            role=User.Role.AGENT,
            status=User.AccountStatus.ACTIVE,
            is_verified=True,
            must_change_password=True,
            created_by=manager,
            company=manager.company,
            **validated_data,
        )
        agent.set_password(temporary_password)
        agent.save()
        EmailService.send_agent_credentials(
            agent=agent,
            temporary_password=temporary_password,
            created_by=manager,
        )
        logger.info(f"Agent [{agent.email}] créé par [{manager.email}].")
        return agent

    @staticmethod
    def change_password(user: User, new_password: str, request) -> None:
        from apps.token_security.services import TokenService
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        user.increment_token_version()
        TokenService.revoke_all_user_tokens(user=user, reason="password_changed")
        EmailService.send_password_changed_confirmation(user=user)
        logger.info(f"Mot de passe changé pour [{user.email}].")

    @staticmethod
    def reset_password(user: User, new_password: str) -> None:
        from apps.token_security.services import TokenService
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        user.increment_token_version()
        TokenService.revoke_all_user_tokens(user=user, reason="password_reset")
        EmailService.send_password_changed_confirmation(user=user)
        logger.info(f"Mot de passe réinitialisé pour [{user.email}].")

    @staticmethod
    def request_password_reset(target_user: User, requesting_user: User) -> None:
        from apps.token_security.services import TokenService
        reset_token = TokenService.issue_temporary_token(user=target_user, action="password_reset")
        EmailService.send_password_reset_link(user=target_user, reset_token=reset_token)
        logger.info(f"Lien de reset envoyé à [{target_user.email}] par [{requesting_user.email}].")