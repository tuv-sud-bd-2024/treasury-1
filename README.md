# Treasury System – Money Market Module

A Django-based REST API for managing money market instruments in a treasury system.

## Features

- **Deal Management** – Create, view, update, and manage money market deals (Fixed Deposit, Call Deposit, Treasury Bills, Commercial Paper, Repos, Certificates of Deposit)
- **Counterparty Management** – Maintain counterparty profiles with credit limits and exposure tracking
- **Interest Calculations** – Accurate interest computation using ACT/365, ACT/360, and 30/360 day-count conventions
- **Cash Flow Projection** – Automatic generation of projected cash flows on deal creation
- **Deal Lifecycle** – Mature, cancel, and roll over deals via dedicated API actions
- **Portfolio Positions** – Aggregated portfolio view by currency, deal type, and direction
- **Django Admin** – Full admin interface for all entities

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## API Endpoints

Base URL: `/api/money-market/`

| Resource | Endpoint | Methods |
|----------|----------|---------|
| Counterparties | `/counterparties/` | GET, POST, PUT, PATCH, DELETE |
| Deals | `/deals/` | GET, POST, PUT, PATCH, DELETE |
| Mature a deal | `/deals/{id}/mature/` | POST |
| Cancel a deal | `/deals/{id}/cancel/` | POST |
| Roll over a deal | `/deals/{id}/roll-over/` | POST |
| Deal cash flows | `/deals/{id}/cash-flows/` | GET |
| Cash flows | `/cash-flows/` | GET |
| Portfolio positions | `/portfolio/` | GET |

### Query Parameters

**Deals:**
- `status` – Filter by status (ACTIVE, MATURED, CANCELLED, ROLLED)
- `deal_type` – Filter by type (FD, CD, TB, CP, REPO, RREPO, COD)
- `direction` – Filter by direction (P = Placement, B = Borrowing)
- `currency` – Filter by currency code
- `counterparty` – Filter by counterparty ID
- `trade_date_from`, `trade_date_to` – Filter by trade date range
- `maturity_date_from`, `maturity_date_to` – Filter by maturity date range

**Counterparties:**
- `is_active` – Filter by active status (true/false)
- `counterparty_type` – Filter by type (BANK, CORP, GOVT, CB, OTHER)

## Deal Types

| Code | Description |
|------|-------------|
| FD | Fixed Deposit |
| CD | Call Deposit |
| TB | Treasury Bill |
| CP | Commercial Paper |
| REPO | Repurchase Agreement |
| RREPO | Reverse Repurchase Agreement |
| COD | Certificate of Deposit |

## Day-Count Conventions

| Convention | Description |
|------------|-------------|
| ACT/365 | Actual days / 365 |
| ACT/360 | Actual days / 360 |
| 30/360 | 30-day months / 360 |

## Running Tests

```bash
python manage.py test money_market
```
