import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.token_security.services import TokenService

logger = logging.getLogger("django")
User = get_user_model()


class EmailService:
    """
    Service centralisé pour l'envoi de tous les emails du système.
    Chaque méthode correspond à un événement métier précis.
    """

    @staticmethod
    def send_admin_new_manager_request(manager: User) -> None:
        """
        Envoie un email à TOUS les admins pour signaler qu'un nouveau manager
        vient de s'inscrire et attend validation.

        Déclenché par : ManagerSignupView après création du compte.

        Contenu de l'email :
            - Nom et email du manager
            - Lien vers l'interface d'approbation/rejet
        """
        admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
        admin_emails = list(admins.values_list("email", flat=True))

        if not admin_emails:
            logger.warning(
                "Aucun admin actif trouvé pour recevoir la notification "
                f"de la demande du manager [{manager.email}]."
            )
            return

        subject = f"[FASI] Nouvelle demande d'accès Manager — {manager.full_name}"
        message = (
            f"Bonjour,\n\n"
            f"Un nouveau manager vient de s'inscrire et attend votre approbation.\n\n"
            f"Nom      : {manager.full_name}\n"
            f"Email    : {manager.email}\n"
            f"Téléphone : {manager.phone_number or 'Non renseigné'}\n\n"
            f"Pour approuver ou rejeter cette demande, connectez-vous à l'interface d'administration.\n\n"
            f"Cordialement,\nLe système FASI"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=False,
        )

        logger.info(
            f"Email de notification envoyé à {len(admin_emails)} admin(s) "
            f"pour la demande du manager [{manager.email}]."
        )

    @staticmethod
    def send_manager_approved(manager: User) -> None:
        """
        Envoie un email au manager pour lui confirmer que son compte a été approuvé.
        Il peut maintenant se connecter.

        Déclenché par : ApproveRejectManagerView (action = 'approve').
        """
        subject = "[FASI] Votre compte a été approuvé — Vous pouvez maintenant vous connecter"
        message = (
            f"Bonjour {manager.first_name},\n\n"
            f"Bonne nouvelle ! Votre demande d'accès à la plateforme FASI a été approuvée.\n\n"
            f"Vous pouvez maintenant vous connecter avec votre adresse email : {manager.email}\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[manager.email],
            fail_silently=False,
        )

    @staticmethod
    def send_manager_rejected(manager: User, reason: str) -> None:
        """
        Envoie un email au manager pour lui informer que sa demande a été rejetée.

        Déclenché par : ApproveRejectManagerView (action = 'reject').
        """
        subject = "[FASI] Votre demande d'accès n'a pas été approuvée"
        message = (
            f"Bonjour {manager.first_name},\n\n"
            f"Nous avons examiné votre demande d'accès à la plateforme FASI.\n\n"
            f"Malheureusement, votre demande n'a pas pu être approuvée pour la raison suivante :\n"
            f"{reason}\n\n"
            f"Pour toute question, contactez votre administrateur.\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[manager.email],
            fail_silently=False,
        )

    @staticmethod
    def send_agent_credentials(agent: User, temporary_password: str, created_by: User) -> None:
        """
        Envoie les identifiants de connexion à un agent nouvellement créé.
        L'agent devra changer son mot de passe temporaire au premier login.

        Déclenché par : CreateAgentView après création du compte agent.
        """
        subject = f"[FASI] Votre compte agent a été créé — {agent.full_name}"
        message = (
            f"Bonjour {agent.first_name},\n\n"
            f"Votre compte agent sur la plateforme FASI a été créé par {created_by.full_name}.\n\n"
            f"Vos identifiants de connexion :\n"
            f"  Email         : {agent.email}\n"
            f"  Mot de passe  : {temporary_password}\n\n"
            f"IMPORTANT : Vous devrez changer ce mot de passe temporaire lors de votre première connexion.\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[agent.email],
            fail_silently=False,
        )

    @staticmethod
    def send_password_reset_link(user: User, reset_token: str) -> None:
        """
        Envoie un lien de réinitialisation de mot de passe à l'utilisateur concerné.
        Le lien contient le token temporaire JWT à usage unique (durée : 1 heure).

        Déclenché par : RequestPasswordResetView.
        """
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"

        subject = "[FASI] Réinitialisation de votre mot de passe"
        message = (
            f"Bonjour {user.first_name},\n\n"
            f"Une demande de réinitialisation de mot de passe a été effectuée pour votre compte.\n\n"
            f"Cliquez sur le lien ci-dessous pour définir un nouveau mot de passe :\n"
            f"{reset_link}\n\n"
            f"Ce lien est valable pendant 1 heure et ne peut être utilisé qu'une seule fois.\n\n"
            f"Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

    @staticmethod
    def send_password_changed_confirmation(user: User) -> None:
        """
        Envoie une confirmation à l'utilisateur après un changement réussi de mot de passe.
        Permet à l'utilisateur de détecter un changement non autorisé.

        Déclenché par : ChangePasswordView et ConfirmPasswordResetView.
        """
        subject = "[FASI] Votre mot de passe a été modifié"
        message = (
            f"Bonjour {user.first_name},\n\n"
            f"Votre mot de passe a été modifié avec succès.\n\n"
            f"Si vous n'êtes pas à l'origine de cette modification, "
            f"contactez immédiatement votre administrateur.\n\n"
            f"Cordialement,\nL'équipe FASI"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


class UserService:
    """
    Service centralisé pour les opérations métier sur les utilisateurs.
    Regroupe la logique qui implique plusieurs modèles ou actions.
    """

    @staticmethod
    def approve_manager(manager: User, admin: User) -> None:
        """
        Approuve le compte d'un manager en attente.
        Envoie un email de confirmation au manager.

        Args:
            manager : instance User avec role=manager et status=pending
            admin   : instance User admin qui effectue l'approbation
        """
        manager.approve()
        EmailService.send_manager_approved(manager)

        logger.info(
            f"Manager [{manager.email}] approuvé par l'admin [{admin.email}]."
        )

    @staticmethod
    def reject_manager(manager: User, admin: User, reason: str) -> None:
        """
        Rejette la demande d'accès d'un manager.
        Envoie un email d'information au manager avec le motif.

        Args:
            manager : instance User avec role=manager et status=pending
            admin   : instance User admin qui effectue le rejet
            reason  : motif du rejet (obligatoire)
        """
        manager.reject(reason=reason)
        EmailService.send_manager_rejected(manager=manager, reason=reason)

        logger.info(
            f"Manager [{manager.email}] rejeté par l'admin [{admin.email}]. Motif : {reason}."
        )

    @staticmethod
    def create_agent(validated_data: dict, manager: User, temporary_password: str) -> User:
        """
        Crée un compte agent et envoie ses identifiants par email.

        Args:
            validated_data     : données validées par CreateAgentSerializer
            manager            : manager qui crée l'agent
            temporary_password : mot de passe temporaire en clair (pour l'email)

        Returns:
            Instance User du nouvel agent créé.
        """
        validated_data.pop("temporary_password", None)

        agent = User(
            role=User.Role.AGENT,
            status=User.AccountStatus.ACTIVE,
            is_verified=True,
            must_change_password=True,
            created_by=manager,
            **validated_data,
        )
        agent.set_password(temporary_password)
        agent.save()

        EmailService.send_agent_credentials(
            agent=agent,
            temporary_password=temporary_password,
            created_by=manager,
        )

        logger.info(
            f"Agent [{agent.email}] créé par le manager [{manager.email}]."
        )

        return agent

    @staticmethod
    def change_password(user: User, new_password: str, request) -> None:
        """
        Change le mot de passe de l'utilisateur et invalide tous ses tokens existants.

        Args:
            user         : utilisateur qui change son mot de passe
            new_password : nouveau mot de passe en clair
            request      : requête HTTP (pour révoquer la session courante)
        """
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])

        # Invalide tous les tokens existants en incrémentant la version
        user.increment_token_version()

        # Révoque toutes les sessions actives
        TokenService.revoke_all_user_tokens(user=user, reason="password_changed")

        # Envoie une confirmation par email
        EmailService.send_password_changed_confirmation(user=user)

        logger.info(f"Mot de passe changé pour [{user.email}].")

    @staticmethod
    def reset_password(user: User, new_password: str) -> None:
        """
        Réinitialise le mot de passe après validation du token temporaire.
        Révoque tous les tokens existants de l'utilisateur.

        Args:
            user         : utilisateur dont le mot de passe est réinitialisé
            new_password : nouveau mot de passe en clair
        """
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])

        # Invalide tous les tokens existants
        user.increment_token_version()

        # Révoque toutes les sessions actives
        TokenService.revoke_all_user_tokens(user=user, reason="password_reset")

        # Envoie une confirmation par email
        EmailService.send_password_changed_confirmation(user=user)

        logger.info(f"Mot de passe réinitialisé pour [{user.email}].")

    @staticmethod
    def request_password_reset(target_user: User, requesting_user: User) -> None:
        """
        Génère un token temporaire et envoie le lien de reset par email.
        Accessible uniquement aux admins et managers selon les règles :
            - Admin  : peut resetter n'importe qui
            - Manager: peut resetter uniquement ses agents

        Args:
            target_user     : utilisateur dont le mot de passe sera resetté
            requesting_user : admin ou manager qui fait la demande
        """
        reset_token = TokenService.issue_temporary_token(
            user=target_user,
            action="password_reset",
        )
        EmailService.send_password_reset_link(
            user=target_user,
            reset_token=reset_token,
        )

        logger.info(
            f"Lien de reset envoyé à [{target_user.email}] "
            f"par [{requesting_user.email}]."
        )
