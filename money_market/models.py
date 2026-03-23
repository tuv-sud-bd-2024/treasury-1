"""
Money Market Module – Models

Covers the core entities for managing money market instruments in a
treasury system: counterparties, deals, and projected cash flows.
"""

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .utils import calculate_interest, calculate_days


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class DealType(models.TextChoices):
    FIXED_DEPOSIT = "FD", "Fixed Deposit"
    CALL_DEPOSIT = "CD", "Call Deposit"
    TREASURY_BILL = "TB", "Treasury Bill"
    COMMERCIAL_PAPER = "CP", "Commercial Paper"
    REPO = "REPO", "Repurchase Agreement"
    REVERSE_REPO = "RREPO", "Reverse Repurchase Agreement"
    CERTIFICATE_OF_DEPOSIT = "COD", "Certificate of Deposit"


class DealDirection(models.TextChoices):
    PLACEMENT = "P", "Placement"
    BORROWING = "B", "Borrowing"


class DayCountConvention(models.TextChoices):
    ACT_365 = "ACT/365", "Actual/365"
    ACT_360 = "ACT/360", "Actual/360"
    THIRTY_360 = "30/360", "30/360"


class DealStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    MATURED = "MATURED", "Matured"
    CANCELLED = "CANCELLED", "Cancelled"
    ROLLED_OVER = "ROLLED", "Rolled Over"


class CounterpartyType(models.TextChoices):
    BANK = "BANK", "Bank"
    CORPORATE = "CORP", "Corporate"
    GOVERNMENT = "GOVT", "Government"
    CENTRAL_BANK = "CB", "Central Bank"
    OTHER = "OTHER", "Other"


class CashFlowType(models.TextChoices):
    PRINCIPAL_IN = "PRINC_IN", "Principal Inflow"
    PRINCIPAL_OUT = "PRINC_OUT", "Principal Outflow"
    INTEREST_IN = "INT_IN", "Interest Inflow"
    INTEREST_OUT = "INT_OUT", "Interest Outflow"


# ---------------------------------------------------------------------------
# Counterparty
# ---------------------------------------------------------------------------

class Counterparty(models.Model):
    """A counterparty (bank, corporate, etc.) that participates in deals."""

    name = models.CharField(max_length=255, unique=True)
    short_name = models.CharField(max_length=50, unique=True)
    counterparty_type = models.CharField(
        max_length=10,
        choices=CounterpartyType.choices,
        default=CounterpartyType.BANK,
    )
    credit_rating = models.CharField(max_length=10, blank=True, default="")
    credit_limit = models.DecimalField(
        max_digits=20, decimal_places=2, default=Decimal("0.00"),
        help_text="Maximum exposure limit in base currency",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Counterparty"
        verbose_name_plural = "Counterparties"
        ordering = ["name"]

    def __str__(self):
        return f"{self.short_name} – {self.name}"

    @property
    def current_exposure(self):
        """Total principal of active placements with this counterparty."""
        return (
            self.deals.filter(
                status=DealStatus.ACTIVE,
                direction=DealDirection.PLACEMENT,
            ).aggregate(total=models.Sum("principal_amount"))["total"]
            or Decimal("0.00")
        )

    def clean(self):
        if self.credit_limit is not None and self.credit_limit < Decimal("0.00"):
            raise ValidationError({"credit_limit": "Credit limit cannot be negative."})


# ---------------------------------------------------------------------------
# Money Market Deal
# ---------------------------------------------------------------------------

class MoneyMarketDeal(models.Model):
    """A single money market transaction."""

    deal_reference = models.CharField(max_length=30, unique=True, editable=False)
    deal_type = models.CharField(max_length=10, choices=DealType.choices)
    direction = models.CharField(max_length=1, choices=DealDirection.choices)
    counterparty = models.ForeignKey(
        Counterparty, on_delete=models.PROTECT, related_name="deals"
    )

    # Financials
    currency = models.CharField(max_length=3, default="USD")
    principal_amount = models.DecimalField(max_digits=20, decimal_places=2)
    interest_rate = models.DecimalField(
        max_digits=8, decimal_places=6,
        help_text="Annual interest rate as a decimal (e.g. 0.05 for 5%)",
    )
    day_count_convention = models.CharField(
        max_length=10,
        choices=DayCountConvention.choices,
        default=DayCountConvention.ACT_365,
    )

    # Dates
    trade_date = models.DateField()
    settlement_date = models.DateField()
    maturity_date = models.DateField()

    # Status
    status = models.CharField(
        max_length=10, choices=DealStatus.choices, default=DealStatus.ACTIVE
    )

    # Optional roll-over link
    rolled_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="rolled_to_deals",
    )

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Money Market Deal"
        verbose_name_plural = "Money Market Deals"
        ordering = ["-trade_date", "-created_at"]

    def __str__(self):
        return (
            f"{self.deal_reference} | {self.get_deal_type_display()} | "
            f"{self.currency} {self.principal_amount:,.2f} | {self.counterparty.short_name}"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if not self.deal_reference:
            self.deal_reference = self._generate_reference()
        self.full_clean()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        from django.utils.timezone import now
        prefix = f"MM{now().strftime('%Y%m%d')}"
        last = (
            MoneyMarketDeal.objects.filter(deal_reference__startswith=prefix)
            .order_by("deal_reference")
            .last()
        )
        if last:
            seq = int(last.deal_reference[-4:]) + 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        errors = {}
        if self.principal_amount is not None and self.principal_amount <= Decimal("0"):
            errors["principal_amount"] = "Principal amount must be positive."
        if self.interest_rate is not None and self.interest_rate < Decimal("0"):
            errors["interest_rate"] = "Interest rate cannot be negative."
        if self.settlement_date and self.trade_date and self.settlement_date < self.trade_date:
            errors["settlement_date"] = "Settlement date cannot be before trade date."
        if self.maturity_date and self.settlement_date and self.maturity_date <= self.settlement_date:
            errors["maturity_date"] = "Maturity date must be after settlement date."
        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def tenor_days(self):
        """Number of calendar days from settlement to maturity."""
        if self.settlement_date and self.maturity_date:
            return calculate_days(
                self.settlement_date, self.maturity_date, self.day_count_convention
            )
        return 0

    @property
    def interest_amount(self):
        """Total interest for the full tenor."""
        return calculate_interest(
            principal=self.principal_amount,
            rate=self.interest_rate,
            days=self.tenor_days,
            convention=self.day_count_convention,
        )

    @property
    def maturity_amount(self):
        """Principal + interest at maturity."""
        return self.principal_amount + self.interest_amount

    @property
    def accrued_interest(self):
        """Interest accrued from settlement date to today (or maturity if past)."""
        today = timezone.now().date()
        if self.settlement_date >= today:
            return Decimal("0.00")
        accrual_end = min(today, self.maturity_date) if self.maturity_date else today
        days_accrued = calculate_days(
            self.settlement_date, accrual_end, self.day_count_convention
        )
        return calculate_interest(
            principal=self.principal_amount,
            rate=self.interest_rate,
            days=days_accrued,
            convention=self.day_count_convention,
        )

    def generate_cash_flows(self):
        """Create or refresh the projected CashFlow records for this deal."""
        self.cash_flows.all().delete()
        flows = []

        if self.direction == DealDirection.PLACEMENT:
            flows.append(CashFlow(
                deal=self,
                flow_date=self.settlement_date,
                flow_type=CashFlowType.PRINCIPAL_OUT,
                amount=self.principal_amount,
                currency=self.currency,
            ))
            flows.append(CashFlow(
                deal=self,
                flow_date=self.maturity_date,
                flow_type=CashFlowType.PRINCIPAL_IN,
                amount=self.principal_amount,
                currency=self.currency,
            ))
            flows.append(CashFlow(
                deal=self,
                flow_date=self.maturity_date,
                flow_type=CashFlowType.INTEREST_IN,
                amount=self.interest_amount,
                currency=self.currency,
            ))
        else:  # BORROWING
            flows.append(CashFlow(
                deal=self,
                flow_date=self.settlement_date,
                flow_type=CashFlowType.PRINCIPAL_IN,
                amount=self.principal_amount,
                currency=self.currency,
            ))
            flows.append(CashFlow(
                deal=self,
                flow_date=self.maturity_date,
                flow_type=CashFlowType.PRINCIPAL_OUT,
                amount=self.principal_amount,
                currency=self.currency,
            ))
            flows.append(CashFlow(
                deal=self,
                flow_date=self.maturity_date,
                flow_type=CashFlowType.INTEREST_OUT,
                amount=self.interest_amount,
                currency=self.currency,
            ))

        CashFlow.objects.bulk_create(flows)


# ---------------------------------------------------------------------------
# Cash Flow
# ---------------------------------------------------------------------------

class CashFlow(models.Model):
    """A projected or actual cash movement associated with a deal."""

    deal = models.ForeignKey(
        MoneyMarketDeal, on_delete=models.CASCADE, related_name="cash_flows"
    )
    flow_date = models.DateField()
    flow_type = models.CharField(max_length=10, choices=CashFlowType.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    is_settled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cash Flow"
        verbose_name_plural = "Cash Flows"
        ordering = ["flow_date", "deal"]

    def __str__(self):
        return (
            f"{self.deal.deal_reference} | {self.get_flow_type_display()} | "
            f"{self.currency} {self.amount:,.2f} on {self.flow_date}"
        )

