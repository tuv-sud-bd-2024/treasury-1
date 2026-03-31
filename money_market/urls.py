"""
Money Market Module – URL Configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CounterpartyViewSet,
    MoneyMarketDealViewSet,
    CashFlowViewSet,
    PortfolioPositionView,
)

router = DefaultRouter()
router.register(r"counterparties", CounterpartyViewSet, basename="counterparty")
router.register(r"deals", MoneyMarketDealViewSet, basename="deal")
router.register(r"cash-flows", CashFlowViewSet, basename="cashflow")
router.register(r"portfolio", PortfolioPositionView, basename="portfolio")

urlpatterns = [
    path("", include(router.urls)),
]
