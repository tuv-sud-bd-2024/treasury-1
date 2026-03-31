"""
Money Market Module – API Views
"""

from decimal import Decimal
from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Counterparty,
    MoneyMarketDeal,
    CashFlow,
    DealStatus,
)
from .serializers import (
    CounterpartySerializer,
    MoneyMarketDealSerializer,
    CashFlowSerializer,
    DealRollOverSerializer,
    PortfolioPositionSerializer,
)


class CounterpartyViewSet(viewsets.ModelViewSet):
    """CRUD operations for counterparties."""

    queryset = Counterparty.objects.all()
    serializer_class = CounterpartySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get("is_active")
        cp_type = self.request.query_params.get("counterparty_type")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        if cp_type:
            qs = qs.filter(counterparty_type=cp_type)
        return qs


class MoneyMarketDealViewSet(viewsets.ModelViewSet):
    """CRUD and lifecycle operations for money market deals."""

    queryset = MoneyMarketDeal.objects.select_related("counterparty").all()
    serializer_class = MoneyMarketDealSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter.upper())
        if deal_type := params.get("deal_type"):
            qs = qs.filter(deal_type=deal_type.upper())
        if direction := params.get("direction"):
            qs = qs.filter(direction=direction.upper())
        if currency := params.get("currency"):
            qs = qs.filter(currency=currency.upper())
        if counterparty_id := params.get("counterparty"):
            qs = qs.filter(counterparty_id=counterparty_id)
        if trade_date_from := params.get("trade_date_from"):
            qs = qs.filter(trade_date__gte=trade_date_from)
        if trade_date_to := params.get("trade_date_to"):
            qs = qs.filter(trade_date__lte=trade_date_to)
        if maturity_from := params.get("maturity_date_from"):
            qs = qs.filter(maturity_date__gte=maturity_from)
        if maturity_to := params.get("maturity_date_to"):
            qs = qs.filter(maturity_date__lte=maturity_to)
        return qs

    def perform_create(self, serializer):
        deal = serializer.save()
        deal.generate_cash_flows()

    def perform_update(self, serializer):
        deal = serializer.save()
        if deal.status == DealStatus.ACTIVE:
            deal.generate_cash_flows()

    @action(detail=True, methods=["post"], url_path="mature")
    def mature(self, request, pk=None):
        """Mark a deal as matured and settle its cash flows."""
        deal = self.get_object()
        if deal.status != DealStatus.ACTIVE:
            return Response(
                {"detail": f"Cannot mature a deal with status '{deal.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deal.status = DealStatus.MATURED
        deal.save(update_fields=["status", "updated_at"])
        deal.cash_flows.filter(is_settled=False).update(is_settled=True)
        return Response(
            MoneyMarketDealSerializer(deal, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel an active deal."""
        deal = self.get_object()
        if deal.status != DealStatus.ACTIVE:
            return Response(
                {"detail": f"Cannot cancel a deal with status '{deal.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deal.status = DealStatus.CANCELLED
        deal.save(update_fields=["status", "updated_at"])
        deal.cash_flows.all().delete()
        return Response(
            MoneyMarketDealSerializer(deal, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="roll-over")
    def roll_over(self, request, pk=None):
        """Roll an active deal over into a new deal."""
        deal = self.get_object()
        if deal.status != DealStatus.ACTIVE:
            return Response(
                {"detail": f"Cannot roll over a deal with status '{deal.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = DealRollOverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Mark the existing deal as rolled over
        deal.status = DealStatus.ROLLED_OVER
        deal.save(update_fields=["status", "updated_at"])

        # Create a new deal starting from the old maturity date
        new_deal = MoneyMarketDeal(
            deal_type=deal.deal_type,
            direction=deal.direction,
            counterparty=deal.counterparty,
            currency=deal.currency,
            principal_amount=deal.maturity_amount,
            interest_rate=data["new_interest_rate"],
            day_count_convention=deal.day_count_convention,
            trade_date=deal.maturity_date,
            settlement_date=deal.maturity_date,
            maturity_date=data["new_maturity_date"],
            rolled_from=deal,
            notes=data.get("notes", ""),
        )
        new_deal.save()
        new_deal.generate_cash_flows()

        return Response(
            MoneyMarketDealSerializer(new_deal, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="cash-flows")
    def cash_flows(self, request, pk=None):
        """List projected cash flows for a deal."""
        deal = self.get_object()
        flows = deal.cash_flows.all()
        serializer = CashFlowSerializer(flows, many=True)
        return Response(serializer.data)


class CashFlowViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve cash flows (read-only; managed via deals)."""

    queryset = CashFlow.objects.select_related("deal__counterparty").all()
    serializer_class = CashFlowSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        if flow_date_from := params.get("flow_date_from"):
            qs = qs.filter(flow_date__gte=flow_date_from)
        if flow_date_to := params.get("flow_date_to"):
            qs = qs.filter(flow_date__lte=flow_date_to)
        if currency := params.get("currency"):
            qs = qs.filter(currency=currency.upper())
        if is_settled := params.get("is_settled"):
            qs = qs.filter(is_settled=is_settled.lower() == "true")
        return qs


class PortfolioPositionView(viewsets.ViewSet):
    """Aggregated portfolio positions for active deals."""

    def list(self, request):
        active_deals = MoneyMarketDeal.objects.filter(status=DealStatus.ACTIVE).select_related(
            "counterparty"
        )

        # Build position rows grouped by currency, deal_type, direction
        from collections import defaultdict
        groups: dict = defaultdict(lambda: {"total_principal": Decimal("0"), "total_accrued": Decimal("0"), "count": 0})

        for deal in active_deals:
            key = (deal.currency, deal.deal_type, deal.direction)
            groups[key]["total_principal"] += deal.principal_amount
            groups[key]["total_accrued"] += deal.accrued_interest
            groups[key]["count"] += 1

        positions = [
            {
                "currency": k[0],
                "deal_type": k[1],
                "direction": k[2],
                "total_principal": v["total_principal"],
                "total_accrued_interest": v["total_accrued"],
                "deal_count": v["count"],
            }
            for k, v in sorted(groups.items())
        ]

        serializer = PortfolioPositionSerializer(positions, many=True)
        return Response(serializer.data)

