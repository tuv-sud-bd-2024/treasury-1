"""
Money Market Module – Serializers
"""

from decimal import Decimal
from rest_framework import serializers

from .models import (
    Counterparty,
    MoneyMarketDeal,
    CashFlow,
    DealStatus,
)


class CounterpartySerializer(serializers.ModelSerializer):
    current_exposure = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True
    )

    class Meta:
        model = Counterparty
        fields = [
            "id",
            "name",
            "short_name",
            "counterparty_type",
            "credit_rating",
            "credit_limit",
            "is_active",
            "current_exposure",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "current_exposure"]


class CashFlowSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlow
        fields = [
            "id",
            "deal",
            "flow_date",
            "flow_type",
            "amount",
            "currency",
            "is_settled",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class MoneyMarketDealSerializer(serializers.ModelSerializer):
    counterparty_name = serializers.CharField(
        source="counterparty.short_name", read_only=True
    )
    tenor_days = serializers.IntegerField(read_only=True)
    interest_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True
    )
    maturity_amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True
    )
    accrued_interest = serializers.DecimalField(
        max_digits=20, decimal_places=2, read_only=True
    )

    class Meta:
        model = MoneyMarketDeal
        fields = [
            "id",
            "deal_reference",
            "deal_type",
            "direction",
            "counterparty",
            "counterparty_name",
            "currency",
            "principal_amount",
            "interest_rate",
            "day_count_convention",
            "trade_date",
            "settlement_date",
            "maturity_date",
            "status",
            "rolled_from",
            "notes",
            "tenor_days",
            "interest_amount",
            "maturity_amount",
            "accrued_interest",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "deal_reference",
            "counterparty_name",
            "tenor_days",
            "interest_amount",
            "maturity_amount",
            "accrued_interest",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        settlement_date = data.get("settlement_date")
        maturity_date = data.get("maturity_date")
        trade_date = data.get("trade_date")
        principal_amount = data.get("principal_amount")
        interest_rate = data.get("interest_rate")

        if settlement_date and trade_date and settlement_date < trade_date:
            raise serializers.ValidationError(
                {"settlement_date": "Settlement date cannot be before trade date."}
            )
        if maturity_date and settlement_date and maturity_date <= settlement_date:
            raise serializers.ValidationError(
                {"maturity_date": "Maturity date must be after settlement date."}
            )
        if principal_amount is not None and principal_amount <= Decimal("0"):
            raise serializers.ValidationError(
                {"principal_amount": "Principal amount must be positive."}
            )
        if interest_rate is not None and interest_rate < Decimal("0"):
            raise serializers.ValidationError(
                {"interest_rate": "Interest rate cannot be negative."}
            )
        return data


class DealMatureSerializer(serializers.Serializer):
    """Used to mark a deal as matured."""
    pass


class DealRollOverSerializer(serializers.Serializer):
    """Used to roll over a deal into a new one."""
    new_maturity_date = serializers.DateField()
    new_interest_rate = serializers.DecimalField(max_digits=8, decimal_places=6)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class PortfolioPositionSerializer(serializers.Serializer):
    """Aggregated position summary."""
    currency = serializers.CharField()
    deal_type = serializers.CharField()
    direction = serializers.CharField()
    total_principal = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_accrued_interest = serializers.DecimalField(max_digits=20, decimal_places=2)
    deal_count = serializers.IntegerField()
