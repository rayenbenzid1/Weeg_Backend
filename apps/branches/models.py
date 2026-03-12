import uuid
from django.db import models


class Branch(models.Model):
    """
    Represents a branch (agency/office) of the company.
    Each agent and manager is assigned to one branch.
    Data (stock, sales, KPIs) is filtered by branch.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Branch name",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Address",
    )

    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="City",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Phone",
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Branch email",
    )
    country = models.CharField(max_length=100, blank=True, null=True, verbose_name="Country")
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="City")
    current_erp = models.CharField(max_length=100, blank=True, null=True, verbose_name="Current ERP", help_text="ERP or business software currently used.")
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Disabling a branch hides it without deleting its data.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last updated")

    class Meta:
        db_table = "branches_branch"
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city or 'City not specified'})"
class BranchAlias(models.Model):
    """
    Maps any raw name found in an Excel file → canonical Branch object.
    Scoped per company: each company has its own alias table.

    Lifecycle:
      - Created automatically during import when an unknown branch name is found.
      - If fuzzy match succeeds  → branch is set, auto_matched=True.
      - If no match              → branch=None (unresolved), admin must resolve via API.
      - Once resolved (manually or auto), the next import reuses the cached alias
        with a single DB lookup — no fuzzy computation needed again.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company      = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="branch_aliases",
        verbose_name="Company",
    )
    alias        = models.CharField(
        max_length=255,
        verbose_name="Raw name from Excel",
        help_text="Exact string as it appears in the imported file.",
    )
    branch       = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aliases",
        verbose_name="Canonical branch",
        help_text="Null = unresolved. Admin must link it via the API.",
    )
    auto_matched = models.BooleanField(
        default=False,
        verbose_name="Auto-matched",
        help_text="True = resolved automatically via fuzzy matching.",
    )
    created_at   = models.DateTimeField(auto_now_add=True, verbose_name="Created at")

    class Meta:
        db_table = "branches_alias"
        unique_together = ("company", "alias")
        verbose_name = "Branch Alias"
        verbose_name_plural = "Branch Aliases"
        ordering = ["alias"]

    def __str__(self):
        target = self.branch.name if self.branch_id else "⚠ unresolved"
        return f"{self.alias!r} → {target}"
