from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """
    Autorise uniquement les utilisateurs avec le rôle 'admin'.
    Le rôle est lu directement depuis le payload JWT sans requête DB.

    Utilisé pour :
        - Approuver / rejeter les comptes managers
        - Accéder aux logs de sécurité
        - Gérer la configuration système
    """
    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsManager(BasePermission):
    """
    Autorise uniquement les utilisateurs avec le rôle 'manager'.
    Le rôle est lu directement depuis le payload JWT sans requête DB.

    Utilisé pour :
        - Créer et gérer les comptes agents
        - Accéder aux rapports détaillés
        - Configurer les seuils d'alertes
        - Réinitialiser le mot de passe des agents
    """
    message = "Accès réservé aux managers."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "manager"
        )


class IsAgent(BasePermission):
    """
    Autorise uniquement les utilisateurs avec le rôle 'agent'.
    Le rôle est lu directement depuis le payload JWT sans requête DB.

    Utilisé pour :
        - Consulter les données de sa succursale
        - Importer des fichiers Excel
        - Recevoir et gérer les alertes
    """
    message = "Accès réservé aux agents."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "agent"
        )


class IsAdminOrManager(BasePermission):
    """
    Autorise les utilisateurs avec le rôle 'admin' ou 'manager'.

    Utilisé pour :
        - Générer des rapports
        - Planifier des rapports automatiques
        - Configurer les alertes
        - Réinitialiser les mots de passe
    """
    message = "Accès réservé aux administrateurs et managers."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ("admin", "manager")
        )


class IsManagerOrAgent(BasePermission):
    """
    Autorise les utilisateurs avec le rôle 'manager' ou 'agent'.

    Utilisé pour les ressources accessibles à tous les utilisateurs internes
    sauf les opérations réservées à l'administrateur système.
    """
    message = "Accès réservé aux managers et agents."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ("manager", "agent")
        )


class HasPermission(BasePermission):
    """
    Permission granulaire basée sur la liste de permissions de l'utilisateur.
    La liste est lue depuis le payload JWT (champ 'permissions').

    Usage dans une vue :
        permission_classes = [IsAuthenticated, HasPermission]
        required_permission = "view-dashboard"

    Les permissions disponibles sont définies dans le modèle User.
    """
    message = "Vous n'avez pas la permission spécifique requise pour cette action."
    required_permission = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        required = getattr(view, "required_permission", self.required_permission)
        if not required:
            return True

        return required in (request.user.permissions_list or [])
