"""
Money Market Module – Tests

Covers:
  • Day-count convention utilities
  • Model validation (Counterparty, MoneyMarketDeal)
  • Deal lifecycle (mature, cancel, roll-over)
  • Cash flow generation
  • REST API endpoints
"""

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Counterparty,
    MoneyMarketDeal,
    CashFlow,
    DealType,
    DealDirection,
    DayCountConvention,
    DealStatus,
    CounterpartyType,
    CashFlowType,
)
from .utils import calculate_days, calculate_interest, calculate_maturity_amount


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------

class DayCountConventionTests(TestCase):
    """Tests for the interest calculation utility functions."""

    def test_act365_days(self):
        start = datetime.date(2024, 1, 1)
        end = datetime.date(2024, 7, 1)
        days = calculate_days(start, end, "ACT/365")
        self.assertEqual(days, 182)  # 2024 is a leap year: Jan(31)+Feb(29)+Mar(31)+Apr(30)+May(31)+Jun(30)

    def test_act360_days_same_as_act365(self):
        start = datetime.date(2024, 1, 1)
        end = datetime.date(2024, 4, 1)
        self.assertEqual(
            calculate_days(start, end, "ACT/360"),
            calculate_days(start, end, "ACT/365"),
        )

    def test_30_360_same_month_length(self):
        start = datetime.date(2024, 1, 1)
        end = datetime.date(2024, 4, 1)
        days = calculate_days(start, end, "30/360")
        # 3 months × 30 = 90
        self.assertEqual(days, 90)

    def test_30_360_day_31_treated_as_30(self):
        start = datetime.date(2024, 1, 31)
        end = datetime.date(2024, 3, 31)
        days = calculate_days(start, end, "30/360")
        # Both day 31 → 30; 2 months × 30 = 60
        self.assertEqual(days, 60)

    def test_calculate_interest_act365(self):
        principal = Decimal("1000000")
        rate = Decimal("0.05")  # 5%
        days = 365
        interest = calculate_interest(principal, rate, days, "ACT/365")
        self.assertEqual(interest, Decimal("50000.00"))

    def test_calculate_interest_act360(self):
        principal = Decimal("1000000")
        rate = Decimal("0.05")
        days = 360
        interest = calculate_interest(principal, rate, days, "ACT/360")
        self.assertEqual(interest, Decimal("50000.00"))

    def test_calculate_interest_30_360(self):
        principal = Decimal("500000")
        rate = Decimal("0.04")  # 4%
        days = 180  # half year (30/360 basis → 180/365)
        interest = calculate_interest(principal, rate, days, "30/360")
        expected = (Decimal("500000") * Decimal("0.04") * Decimal("180") / Decimal("365")).quantize(Decimal("0.01"))
        self.assertEqual(interest, expected)

    def test_calculate_maturity_amount(self):
        principal = Decimal("1000000")
        rate = Decimal("0.05")
        days = 365
        maturity = calculate_maturity_amount(principal, rate, days, "ACT/365")
        self.assertEqual(maturity, Decimal("1050000.00"))

    def test_zero_days_gives_zero_interest(self):
        self.assertEqual(
            calculate_interest(Decimal("1000000"), Decimal("0.05"), 0, "ACT/365"),
            Decimal("0.00"),
        )


# ---------------------------------------------------------------------------
# Counterparty model tests
# ---------------------------------------------------------------------------

class CounterpartyModelTests(TestCase):

    def _make_counterparty(self, **kwargs):
        defaults = {
            "name": "Test Bank",
            "short_name": "TBANK",
            "counterparty_type": CounterpartyType.BANK,
            "credit_limit": Decimal("10000000"),
        }
        defaults.update(kwargs)
        return Counterparty(**defaults)

    def test_create_counterparty(self):
        cp = Counterparty.objects.create(
            name="Alpha Bank",
            short_name="ALPHA",
            counterparty_type=CounterpartyType.BANK,
            credit_limit=Decimal("5000000"),
        )
        self.assertEqual(cp.name, "Alpha Bank")
        self.assertTrue(cp.is_active)

    def test_negative_credit_limit_raises(self):
        cp = self._make_counterparty(credit_limit=Decimal("-1"))
        with self.assertRaises(ValidationError):
            cp.full_clean()

    def test_str_representation(self):
        cp = self._make_counterparty()
        self.assertIn("TBANK", str(cp))

    def test_current_exposure_no_deals(self):
        cp = Counterparty.objects.create(
            name="Empty Bank", short_name="EMPTY",
            credit_limit=Decimal("1000000"),
        )
        self.assertEqual(cp.current_exposure, Decimal("0.00"))


# ---------------------------------------------------------------------------
# MoneyMarketDeal model tests
# ---------------------------------------------------------------------------

def make_counterparty(name="Test CP", short="TCP"):
    return Counterparty.objects.create(
        name=name, short_name=short, credit_limit=Decimal("50000000")
    )


def make_deal(counterparty=None, **kwargs):
    if counterparty is None:
        counterparty = make_counterparty()
    defaults = {
        "deal_type": DealType.FIXED_DEPOSIT,
        "direction": DealDirection.PLACEMENT,
        "counterparty": counterparty,
        "currency": "USD",
        "principal_amount": Decimal("1000000"),
        "interest_rate": Decimal("0.05"),
        "day_count_convention": DayCountConvention.ACT_365,
        "trade_date": datetime.date(2024, 1, 1),
        "settlement_date": datetime.date(2024, 1, 2),
        "maturity_date": datetime.date(2024, 7, 1),
    }
    defaults.update(kwargs)
    deal = MoneyMarketDeal(**defaults)
    deal.save()
    return deal


class MoneyMarketDealModelTests(TestCase):

    def test_deal_reference_auto_generated(self):
        deal = make_deal()
        self.assertTrue(deal.deal_reference.startswith("MM"))
        self.assertEqual(len(deal.deal_reference), 14)  # MM + 8 date digits + 4 seq

    def test_tenor_days_calculated(self):
        deal = make_deal(
            settlement_date=datetime.date(2024, 1, 2),
            maturity_date=datetime.date(2024, 7, 1),
        )
        self.assertEqual(deal.tenor_days, (datetime.date(2024, 7, 1) - datetime.date(2024, 1, 2)).days)

    def test_interest_amount(self):
        deal = make_deal(
            principal_amount=Decimal("1000000"),
            interest_rate=Decimal("0.05"),
            settlement_date=datetime.date(2024, 1, 1),
            maturity_date=datetime.date(2025, 1, 1),  # 366 days (leap year)
        )
        expected = calculate_interest(
            Decimal("1000000"), Decimal("0.05"), deal.tenor_days, "ACT/365"
        )
        self.assertEqual(deal.interest_amount, expected)

    def test_maturity_amount(self):
        deal = make_deal()
        self.assertEqual(deal.maturity_amount, deal.principal_amount + deal.interest_amount)

    def test_zero_principal_raises(self):
        cp = make_counterparty(name="Bank2", short="B2")
        deal = MoneyMarketDeal(
            deal_type=DealType.FIXED_DEPOSIT,
            direction=DealDirection.PLACEMENT,
            counterparty=cp,
            currency="USD",
            principal_amount=Decimal("0"),
            interest_rate=Decimal("0.05"),
            trade_date=datetime.date(2024, 1, 1),
            settlement_date=datetime.date(2024, 1, 2),
            maturity_date=datetime.date(2024, 7, 1),
        )
        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_negative_principal_raises(self):
        cp = make_counterparty(name="Bank3", short="B3")
        deal = MoneyMarketDeal(
            deal_type=DealType.FIXED_DEPOSIT,
            direction=DealDirection.PLACEMENT,
            counterparty=cp,
            currency="USD",
            principal_amount=Decimal("-1000"),
            interest_rate=Decimal("0.05"),
            trade_date=datetime.date(2024, 1, 1),
            settlement_date=datetime.date(2024, 1, 2),
            maturity_date=datetime.date(2024, 7, 1),
        )
        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_settlement_before_trade_date_raises(self):
        cp = make_counterparty(name="Bank4", short="B4")
        deal = MoneyMarketDeal(
            deal_type=DealType.FIXED_DEPOSIT,
            direction=DealDirection.PLACEMENT,
            counterparty=cp,
            currency="USD",
            principal_amount=Decimal("1000000"),
            interest_rate=Decimal("0.05"),
            trade_date=datetime.date(2024, 1, 5),
            settlement_date=datetime.date(2024, 1, 3),
            maturity_date=datetime.date(2024, 7, 1),
        )
        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_maturity_before_settlement_raises(self):
        cp = make_counterparty(name="Bank5", short="B5")
        deal = MoneyMarketDeal(
            deal_type=DealType.FIXED_DEPOSIT,
            direction=DealDirection.PLACEMENT,
            counterparty=cp,
            currency="USD",
            principal_amount=Decimal("1000000"),
            interest_rate=Decimal("0.05"),
            trade_date=datetime.date(2024, 1, 1),
            settlement_date=datetime.date(2024, 7, 1),
            maturity_date=datetime.date(2024, 1, 2),
        )
        with self.assertRaises(ValidationError):
            deal.full_clean()

    def test_default_status_is_active(self):
        deal = make_deal()
        self.assertEqual(deal.status, DealStatus.ACTIVE)

    def test_str_representation(self):
        deal = make_deal()
        self.assertIn("USD", str(deal))


# ---------------------------------------------------------------------------
# Cash flow generation tests
# ---------------------------------------------------------------------------

class CashFlowGenerationTests(TestCase):

    def test_placement_generates_three_flows(self):
        deal = make_deal(direction=DealDirection.PLACEMENT)
        deal.generate_cash_flows()
        self.assertEqual(deal.cash_flows.count(), 3)

    def test_borrowing_generates_three_flows(self):
        deal = make_deal(direction=DealDirection.BORROWING)
        deal.generate_cash_flows()
        self.assertEqual(deal.cash_flows.count(), 3)

    def test_placement_settlement_flow_is_outflow(self):
        deal = make_deal(direction=DealDirection.PLACEMENT)
        deal.generate_cash_flows()
        settlement_flow = deal.cash_flows.get(
            flow_date=deal.settlement_date,
            flow_type=CashFlowType.PRINCIPAL_OUT,
        )
        self.assertEqual(settlement_flow.amount, deal.principal_amount)

    def test_borrowing_settlement_flow_is_inflow(self):
        deal = make_deal(direction=DealDirection.BORROWING)
        deal.generate_cash_flows()
        settlement_flow = deal.cash_flows.get(
            flow_date=deal.settlement_date,
            flow_type=CashFlowType.PRINCIPAL_IN,
        )
        self.assertEqual(settlement_flow.amount, deal.principal_amount)

    def test_regeneration_replaces_flows(self):
        deal = make_deal()
        deal.generate_cash_flows()
        deal.generate_cash_flows()  # regenerate
        self.assertEqual(deal.cash_flows.count(), 3)


# ---------------------------------------------------------------------------
# REST API tests
# ---------------------------------------------------------------------------

class CounterpartyAPITests(APITestCase):

    def setUp(self):
        self.cp = Counterparty.objects.create(
            name="API Bank", short_name="APIBANK",
            counterparty_type=CounterpartyType.BANK,
            credit_limit=Decimal("10000000"),
        )

    def test_list_counterparties(self):
        url = "/api/money-market/counterparties/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_counterparty(self):
        url = "/api/money-market/counterparties/"
        data = {
            "name": "New Bank",
            "short_name": "NEWBANK",
            "counterparty_type": "BANK",
            "credit_limit": "5000000.00",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Bank")

    def test_retrieve_counterparty(self):
        url = f"/api/money-market/counterparties/{self.cp.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["short_name"], "APIBANK")

    def test_filter_by_active(self):
        url = "/api/money-market/counterparties/?is_active=true"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class MoneyMarketDealAPITests(APITestCase):

    def setUp(self):
        self.cp = Counterparty.objects.create(
            name="Deal Bank", short_name="DBANK",
            credit_limit=Decimal("50000000"),
        )
        self.deal_data = {
            "deal_type": "FD",
            "direction": "P",
            "counterparty": self.cp.pk,
            "currency": "USD",
            "principal_amount": "1000000.00",
            "interest_rate": "0.050000",
            "day_count_convention": "ACT/365",
            "trade_date": "2024-01-01",
            "settlement_date": "2024-01-02",
            "maturity_date": "2024-07-01",
        }

    def _create_deal(self):
        url = "/api/money-market/deals/"
        return self.client.post(url, self.deal_data, format="json")

    def test_create_deal(self):
        response = self._create_deal()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("deal_reference", response.data)
        self.assertEqual(response.data["status"], "ACTIVE")

    def test_create_deal_generates_cash_flows(self):
        response = self._create_deal()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        deal = MoneyMarketDeal.objects.get(pk=response.data["id"])
        self.assertEqual(deal.cash_flows.count(), 3)

    def test_list_deals(self):
        self._create_deal()
        url = "/api/money-market/deals/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_deal(self):
        create_response = self._create_deal()
        deal_id = create_response.data["id"]
        url = f"/api/money-market/deals/{deal_id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("tenor_days", response.data)
        self.assertIn("interest_amount", response.data)
        self.assertIn("maturity_amount", response.data)

    def test_mature_deal(self):
        create_response = self._create_deal()
        deal_id = create_response.data["id"]
        url = f"/api/money-market/deals/{deal_id}/mature/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "MATURED")

    def test_cancel_deal(self):
        create_response = self._create_deal()
        deal_id = create_response.data["id"]
        url = f"/api/money-market/deals/{deal_id}/cancel/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "CANCELLED")

    def test_cannot_mature_already_matured_deal(self):
        create_response = self._create_deal()
        deal_id = create_response.data["id"]
        self.client.post(f"/api/money-market/deals/{deal_id}/mature/")
        response = self.client.post(f"/api/money-market/deals/{deal_id}/mature/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_cancel_matured_deal(self):
        create_response = self._create_deal()
        deal_id = create_response.data["id"]
        self.client.post(f"/api/money-market/deals/{deal_id}/mature/")
        response = self.client.post(f"/api/money-market/deals/{deal_id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_roll_over_deal(self):
        create_response = self._create_deal()
        deal_id = create_response.data["id"]
        url = f"/api/money-market/deals/{deal_id}/roll-over/"
        roll_data = {
            "new_maturity_date": "2025-01-01",
            "new_interest_rate": "0.055000",
            "notes": "Rolled over at higher rate",
        }
        response = self.client.post(url, roll_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Original deal should now be ROLLED
        original = MoneyMarketDeal.objects.get(pk=deal_id)
        self.assertEqual(original.status, DealStatus.ROLLED_OVER)
        # New deal should be ACTIVE
        self.assertEqual(response.data["status"], "ACTIVE")

    def test_deal_cash_flows_endpoint(self):
        create_response = self._create_deal()
        deal_id = create_response.data["id"]
        url = f"/api/money-market/deals/{deal_id}/cash-flows/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_invalid_deal_zero_principal(self):
        data = dict(self.deal_data, principal_amount="0")
        response = self.client.post("/api/money-market/deals/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_deal_maturity_before_settlement(self):
        data = dict(self.deal_data, maturity_date="2024-01-01")
        response = self.client.post("/api/money-market/deals/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_deals_by_status(self):
        self._create_deal()
        response = self.client.get("/api/money-market/deals/?status=ACTIVE")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_deals_by_currency(self):
        self._create_deal()
        response = self.client.get("/api/money-market/deals/?currency=USD")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PortfolioAPITests(APITestCase):

    def setUp(self):
        self.cp = Counterparty.objects.create(
            name="Port Bank", short_name="PBANK",
            credit_limit=Decimal("50000000"),
        )

    def _create_deal(self, direction="P", principal="1000000.00"):
        url = "/api/money-market/deals/"
        data = {
            "deal_type": "FD",
            "direction": direction,
            "counterparty": self.cp.pk,
            "currency": "USD",
            "principal_amount": principal,
            "interest_rate": "0.050000",
            "day_count_convention": "ACT/365",
            "trade_date": "2024-01-01",
            "settlement_date": "2024-01-02",
            "maturity_date": "2024-07-01",
        }
        return self.client.post(url, data, format="json")

    def test_portfolio_positions(self):
        self._create_deal("P", "1000000.00")
        self._create_deal("B", "500000.00")
        response = self.client.get("/api/money-market/portfolio/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_portfolio_aggregation(self):
        self._create_deal("P", "1000000.00")
        self._create_deal("P", "2000000.00")
        response = self.client.get("/api/money-market/portfolio/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        placement_row = next(r for r in response.data if r["direction"] == "P")
        self.assertEqual(Decimal(placement_row["total_principal"]), Decimal("3000000.00"))

