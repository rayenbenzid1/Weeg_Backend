import uuid
from django.db import models


class MaterialMovement(models.Model):
    """
    Represents a single material movement transaction imported from
    the Excel movements file (حركة_المادة_2025).

    Movement types (original Arabic → English mapping):
        ف بيع           → sale
        ف شراء          → purchase
        ف.أول المدة     → opening_balance
        مردودات بيع     → sales_return
        مردود شراء      → purchase_return
        ادخال رئيسي     → main_entry
        اخراج رئيسي     → main_exit
    """

    class MovementType(models.TextChoices):
        SALE = "sale", "Sale"
        PURCHASE = "purchase", "Purchase"
        OPENING_BALANCE = "opening_balance", "Opening Balance"
        SALES_RETURN = "sales_return", "Sales Return"
        PURCHASE_RETURN = "purchase_return", "Purchase Return"
        MAIN_ENTRY = "main_entry", "Main Entry"
        MAIN_EXIT = "main_exit", "Main Exit"
        OTHER = "other", "Other"

    # Arabic → English movement type mapping
    MOVEMENT_TYPE_MAP = {
        "ف بيع": MovementType.SALE,
        "ف شراء": MovementType.PURCHASE,
        "ف.أول المدة": MovementType.OPENING_BALANCE,
        "مردودات بيع": MovementType.SALES_RETURN,
        "مردود شراء": MovementType.PURCHASE_RETURN,
        "ادخال رئيسي": MovementType.MAIN_ENTRY,
        "اخراج رئيسي": MovementType.MAIN_EXIT,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="material_movements",
        verbose_name="Company",
    )

    # ── Product reference (FK if product exists, raw fields as fallback) ──────

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
        verbose_name="Product",
        help_text="Linked product (resolved from product_code during import).",
    )

    # Raw fields preserved for traceability even if FK resolution fails
    category = models.CharField(max_length=255, blank=True, null=True, verbose_name="Category")
    material_code = models.CharField(max_length=100, verbose_name="Material Code")
    lab_code = models.CharField(max_length=100, blank=True, null=True, verbose_name="Lab Code")
    material_name = models.CharField(max_length=500, verbose_name="Material Name")

    # ── Date & movement type ──────────────────────────────────────────────────

    movement_date = models.DateField(
        verbose_name="Movement Date",
        db_index=True,
    )

    movement_type = models.CharField(
        max_length=30,
        choices=MovementType.choices,
        default=MovementType.OTHER,
        verbose_name="Movement Type",
        db_index=True,
    )

    movement_type_raw = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Movement Type (Original Arabic)",
        help_text="Original Arabic value from Excel for reference.",
    )

    # ── Quantities & amounts ──────────────────────────────────────────────────

    qty_in = models.DecimalField(
        max_digits=14, decimal_places=4,
        null=True, blank=True,
        verbose_name="Quantity In",
    )
    price_in = models.DecimalField(
        max_digits=14, decimal_places=4,
        null=True, blank=True,
        verbose_name="Unit Price In (LYD)",
    )
    total_in = models.DecimalField(
        max_digits=18, decimal_places=4,
        null=True, blank=True,
        verbose_name="Total In (LYD)",
    )

    qty_out = models.DecimalField(
        max_digits=14, decimal_places=4,
        null=True, blank=True,
        verbose_name="Quantity Out",
    )
    price_out = models.DecimalField(
        max_digits=14, decimal_places=4,
        null=True, blank=True,
        verbose_name="Unit Price Out (LYD)",
    )
    total_out = models.DecimalField(
        max_digits=18, decimal_places=4,
        null=True, blank=True,
        verbose_name="Total Out (LYD)",
    )

    balance_price = models.DecimalField(
        max_digits=14, decimal_places=4,
        null=True, blank=True,
        verbose_name="Balance Price (LYD)",
    )

    # ── Branch & customer ─────────────────────────────────────────────────────

    branch_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Branch Name",
        help_text="Raw branch name from Excel (resolved to Branch FK when possible).",
    )

    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
        verbose_name="Branch",
    )

    customer_name = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Customer Name",
        help_text="Raw customer name from Excel.",
    )

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
        verbose_name="Customer",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions_movement"
        verbose_name = "Material Movement"
        verbose_name_plural = "Material Movements"
        ordering = ["-movement_date", "material_code"]
        indexes = [
            models.Index(fields=["company", "movement_date"]),
            models.Index(fields=["company", "movement_type"]),
            models.Index(fields=["company", "material_code"]),
        ]

    def __str__(self):
        return (
            f"[{self.movement_type}] {self.material_name} "
            f"({self.movement_date}) — {self.branch_name}"
        )
