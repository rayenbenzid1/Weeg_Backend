from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Interface d'administration personnalisée pour le modèle User custom.
    Étend UserAdmin pour prendre en compte les champs spécifiques au projet FASI.
    """

    # Colonnes affichées dans la liste
    list_display = [
        "email",
        "full_name",
        "role_display",
        "status_display",
        "branch",
        "is_verified",
        "created_at",
    ]

    # Filtres latéraux
    list_filter = [
        "role",
        "status",
        "is_verified",
        "must_change_password",
        "branch",
        "created_at",
    ]

    # Champs de recherche
    search_fields = ["email", "first_name", "last_name", "phone_number"]

    # Tri par défaut
    ordering = ["-created_at"]

    # Champs en lecture seule
    readonly_fields = ["id", "created_at", "updated_at", "token_version", "created_by"]

    # Organisation des champs dans le formulaire de détail
    fieldsets = (
        (
            "Identité",
            {
                "fields": ("id", "email", "first_name", "last_name", "phone_number")
            },
        ),
        (
            "Rôle et accès",
            {
                "fields": ("role", "status", "branch", "is_verified", "rejection_reason")
            },
        ),
        (
            "Permissions granulaires",
            {
                "fields": ("permissions_list",),
                "classes": ("collapse",),
            },
        ),
        (
            "Sécurité",
            {
                "fields": ("password", "token_version", "must_change_password"),
                "classes": ("collapse",),
            },
        ),
        (
            "Permissions Django (système)",
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
                "classes": ("collapse",),
            },
        ),
        (
            "Métadonnées",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # Champs affichés lors de la création d'un utilisateur dans l'admin
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "status",
                    "branch",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    # Champ utilisé à la place du username
    USERNAME_FIELD = "email"

    # Colonnes calculées avec mise en forme
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = "Nom complet"

    def role_display(self, obj):
        colors = {
            "admin": "#c0392b",
            "manager": "#2980b9",
            "agent": "#27ae60",
        }
        color = colors.get(obj.role, "#7f8c8d")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_role_display(),
        )
    role_display.short_description = "Rôle"

    def status_display(self, obj):
        colors = {
            "pending": "#f39c12",
            "approved": "#27ae60",
            "rejected": "#c0392b",
            "active": "#2ecc71",
            "suspended": "#7f8c8d",
        }
        color = colors.get(obj.status, "#7f8c8d")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_display.short_description = "Statut"
