from django.contrib import admin

from .models import Counterparty, MoneyMarketDeal, CashFlow


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ["short_name", "name", "counterparty_type", "credit_rating", "credit_limit", "is_active"]
    list_filter = ["counterparty_type", "is_active"]
    search_fields = ["name", "short_name"]


class CashFlowInline(admin.TabularInline):
    model = CashFlow
    extra = 0
    readonly_fields = ["flow_date", "flow_type", "amount", "currency", "is_settled"]
    can_delete = False


@admin.register(MoneyMarketDeal)
class MoneyMarketDealAdmin(admin.ModelAdmin):
    list_display = [
        "deal_reference", "deal_type", "direction", "counterparty",
        "currency", "principal_amount", "interest_rate", "trade_date",
        "maturity_date", "status",
    ]
    list_filter = ["deal_type", "direction", "status", "currency"]
    search_fields = ["deal_reference", "counterparty__name", "counterparty__short_name"]
    readonly_fields = [
        "deal_reference", "tenor_days", "interest_amount", "maturity_amount",
        "accrued_interest", "created_at", "updated_at",
    ]
    inlines = [CashFlowInline]
    date_hierarchy = "trade_date"


@admin.register(CashFlow)
class CashFlowAdmin(admin.ModelAdmin):
    list_display = ["deal", "flow_date", "flow_type", "amount", "currency", "is_settled"]
    list_filter = ["flow_type", "is_settled", "currency"]
    search_fields = ["deal__deal_reference"]

