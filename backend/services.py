"""
Service layer — business logic, database transactions, analytics,
forecasting, audit logging, and distributor intelligence.

Routes delegate here; this keeps controllers thin.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, extract, and_, case
from extensions import db
from models import Product, Distributor, Sale, StockTransaction


# ══════════════════════════════════════════════
#  INVENTORY
# ══════════════════════════════════════════════

def get_all_inventory():
    """Return every product with computed stock status."""
    products = Product.query.order_by(Product.name).all()
    return [p.to_dict() for p in products]


def get_inventory_summary():
    """Aggregate inventory KPIs for the dashboard cards."""
    total_sku = db.session.query(func.count(Product.id)).scalar() or 0
    low_stock = (
        db.session.query(func.count(Product.id))
        .filter(Product.quantity > 0, Product.quantity <= Product.min_stock_level)
        .scalar()
    ) or 0
    critical = (
        db.session.query(func.count(Product.id))
        .filter(
            Product.quantity > 0,
            Product.quantity <= (Product.min_stock_level / 2),
        )
        .scalar()
    ) or 0
    out_of_stock = (
        db.session.query(func.count(Product.id))
        .filter(Product.quantity <= 0)
        .scalar()
    ) or 0
    inventory_value = (
        db.session.query(
            func.sum(Product.quantity * Product.price)
        ).scalar()
    ) or 0

    return {
        "total_sku": total_sku,
        "low_stock_alerts": low_stock,
        "critical_alerts": critical,
        "out_of_stock": out_of_stock,
        "inventory_value": float(inventory_value),
    }


# ══════════════════════════════════════════════
#  SALES (transactional + audit logging)
# ══════════════════════════════════════════════

def record_sale(product_id: int, distributor_id: int, quantity_sold: int,
                sale_date: str | None = None):
    """
    Record a sale inside an atomic database transaction.

    1. Lock the product row (SELECT ... FOR UPDATE) to prevent races.
    2. Verify sufficient stock.
    3. Deduct quantity.
    4. Insert sale record.
    5. Log a StockTransaction audit entry.
    6. Commit — or rollback on any error.
    """
    product = (
        db.session.query(Product)
        .filter_by(id=product_id)
        .with_for_update()
        .first()
    )
    if product is None:
        raise ValueError(f"Product with id {product_id} not found.")

    distributor = Distributor.query.get(distributor_id)
    if distributor is None:
        raise ValueError(f"Distributor with id {distributor_id} not found.")

    if quantity_sold <= 0:
        raise ValueError("Quantity sold must be a positive integer.")

    if product.quantity < quantity_sold:
        raise ValueError(
            f"Insufficient stock. Available: {product.quantity}, "
            f"requested: {quantity_sold}."
        )

    # --- begin atomic mutation ---
    qty_before = product.quantity
    product.quantity -= quantity_sold
    qty_after = product.quantity

    total_price = float(product.price) * quantity_sold
    timestamp = (
        datetime.fromisoformat(sale_date)
        if sale_date
        else datetime.now(timezone.utc)
    )

    sale = Sale(
        product_id=product_id,
        distributor_id=distributor_id,
        quantity_sold=quantity_sold,
        total_price=total_price,
        timestamp=timestamp,
    )
    db.session.add(sale)
    db.session.flush()  # get sale.id

    # Audit log
    txn = StockTransaction(
        product_id=product_id,
        transaction_type="SALE",
        quantity_change=-quantity_sold,
        quantity_before=qty_before,
        quantity_after=qty_after,
        reason=f"Sale to {distributor.name}",
        reference_id=sale.id,
        timestamp=timestamp,
    )
    db.session.add(txn)
    db.session.commit()

    return sale.to_dict()


def record_restock(product_id: int, quantity: int, reason: str = "Manual restock"):
    """
    Add stock to a product and log the transaction.
    """
    product = (
        db.session.query(Product)
        .filter_by(id=product_id)
        .with_for_update()
        .first()
    )
    if product is None:
        raise ValueError(f"Product with id {product_id} not found.")
    if quantity <= 0:
        raise ValueError("Restock quantity must be positive.")

    qty_before = product.quantity
    product.quantity += quantity
    qty_after = product.quantity

    txn = StockTransaction(
        product_id=product_id,
        transaction_type="RESTOCK",
        quantity_change=quantity,
        quantity_before=qty_before,
        quantity_after=qty_after,
        reason=reason,
    )
    db.session.add(txn)
    db.session.commit()

    return product.to_dict()


def record_adjustment(product_id: int, new_quantity: int, reason: str = "Manual adjustment"):
    """
    Set product stock to an exact number (inventory correction).
    """
    product = (
        db.session.query(Product)
        .filter_by(id=product_id)
        .with_for_update()
        .first()
    )
    if product is None:
        raise ValueError(f"Product with id {product_id} not found.")

    qty_before = product.quantity
    change = new_quantity - qty_before
    product.quantity = new_quantity

    txn = StockTransaction(
        product_id=product_id,
        transaction_type="ADJUSTMENT",
        quantity_change=change,
        quantity_before=qty_before,
        quantity_after=new_quantity,
        reason=reason,
    )
    db.session.add(txn)
    db.session.commit()

    return product.to_dict()


def get_stock_transactions(product_id: int | None = None, limit: int = 50):
    """Return recent stock audit log entries."""
    q = StockTransaction.query.order_by(StockTransaction.timestamp.desc())
    if product_id:
        q = q.filter(StockTransaction.product_id == product_id)
    return [t.to_dict() for t in q.limit(limit).all()]


# ══════════════════════════════════════════════
#  ANALYTICS & FORECASTING
# ══════════════════════════════════════════════

def get_forecast():
    """
    For each product, calculate:
    - Average daily burn rate (last 30 days of sales)
    - Estimated days until out of stock
    - Stock alert level
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Get last-30-day sales volume per product
    burn_data = (
        db.session.query(
            Sale.product_id,
            func.coalesce(func.sum(Sale.quantity_sold), 0).label("total_sold"),
        )
        .filter(Sale.timestamp >= thirty_days_ago)
        .group_by(Sale.product_id)
        .all()
    )
    burn_map = {row.product_id: int(row.total_sold) for row in burn_data}

    products = Product.query.order_by(Product.name).all()
    forecasts = []

    for p in products:
        sold_30d = burn_map.get(p.id, 0)
        daily_burn = round(sold_30d / 30, 2)

        if daily_burn > 0 and p.quantity > 0:
            days_remaining = round(p.quantity / daily_burn, 1)
        elif p.quantity <= 0:
            days_remaining = 0
        else:
            days_remaining = None  # no recent sales, can't predict

        forecasts.append({
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku,
            "current_stock": p.quantity,
            "min_stock_level": p.min_stock_level,
            "sold_last_30_days": sold_30d,
            "avg_daily_burn_rate": daily_burn,
            "estimated_days_until_oos": days_remaining,
            "status": p.stock_status,
            "alert_level": p.alert_level,
            "restock_recommended": (
                daily_burn > 0 and p.quantity <= p.min_stock_level
            ),
        })

    # Sort: most urgent first (lowest days remaining)
    forecasts.sort(
        key=lambda x: (
            x["estimated_days_until_oos"]
            if x["estimated_days_until_oos"] is not None
            else 9999
        )
    )

    return forecasts


# ══════════════════════════════════════════════
#  AUTOMATED ALERTS & DAILY SUMMARY
# ══════════════════════════════════════════════

def get_stock_alerts():
    """
    Return products that are below their min_stock_level threshold.
    Sorted by severity: Critical first, then Low Stock.
    """
    products = (
        Product.query
        .filter(Product.quantity <= Product.min_stock_level)
        .order_by(Product.quantity.asc())
        .all()
    )
    return [p.to_dict() for p in products]


def get_daily_summary():
    """
    Generate a daily intelligence summary:
    - Top 3 best-selling products (by volume, last 7 days)
    - 3 worst-performing distributors (lowest revenue, last 30 days)
    - Stock alerts count
    - Total revenue today
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # Top 3 best-selling products (last 7 days)
    top_products = (
        db.session.query(
            Product.name,
            func.sum(Sale.quantity_sold).label("volume"),
            func.sum(Sale.total_price).label("revenue"),
        )
        .join(Sale, Sale.product_id == Product.id)
        .filter(Sale.timestamp >= week_start)
        .group_by(Product.name)
        .order_by(func.sum(Sale.quantity_sold).desc())
        .limit(3)
        .all()
    )

    # 3 worst-performing distributors (last 30 days, lowest revenue)
    worst_distributors = (
        db.session.query(
            Distributor.name,
            func.coalesce(func.sum(Sale.quantity_sold), 0).label("volume"),
            func.coalesce(func.sum(Sale.total_price), 0).label("revenue"),
        )
        .outerjoin(Sale, and_(
            Sale.distributor_id == Distributor.id,
            Sale.timestamp >= month_start,
        ))
        .group_by(Distributor.name)
        .order_by(func.coalesce(func.sum(Sale.total_price), 0).asc())
        .limit(3)
        .all()
    )

    # Today's revenue
    today_revenue = (
        db.session.query(func.coalesce(func.sum(Sale.total_price), 0))
        .filter(Sale.timestamp >= today_start)
        .scalar()
    )
    today_volume = (
        db.session.query(func.coalesce(func.sum(Sale.quantity_sold), 0))
        .filter(Sale.timestamp >= today_start)
        .scalar()
    )

    # Stock alerts count
    alert_count = (
        db.session.query(func.count(Product.id))
        .filter(Product.quantity <= Product.min_stock_level)
        .scalar()
    ) or 0

    return {
        "date": now.strftime("%Y-%m-%d"),
        "top_3_products": [
            {"name": r.name, "volume": int(r.volume), "revenue": float(r.revenue)}
            for r in top_products
        ],
        "worst_3_distributors": [
            {"name": r.name, "volume": int(r.volume), "revenue": float(r.revenue)}
            for r in worst_distributors
        ],
        "today_revenue": float(today_revenue),
        "today_volume": int(today_volume),
        "stock_alerts": alert_count,
    }


# ══════════════════════════════════════════════
#  DISTRIBUTOR INTELLIGENCE
# ══════════════════════════════════════════════

def get_distributor_performance():
    """
    Revenue and volume per distributor, plus:
    - Month-over-month growth
    - Average order value (AOV)
    - Order count
    - Auto-calculated tier (Gold/Silver/Bronze)
    """
    results = (
        db.session.query(
            Distributor.id,
            Distributor.name,
            Distributor.region,
            Distributor.tier,
            func.coalesce(func.sum(Sale.quantity_sold), 0).label("total_volume"),
            func.coalesce(func.sum(Sale.total_price), 0).label("total_revenue"),
            func.count(Sale.id).label("order_count"),
        )
        .outerjoin(Sale, Sale.distributor_id == Distributor.id)
        .group_by(Distributor.id, Distributor.name, Distributor.region, Distributor.tier)
        .order_by(func.sum(Sale.total_price).desc().nullslast())
        .all()
    )

    # Calculate monthly revenues for tier ranking
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    monthly_revs = (
        db.session.query(
            Sale.distributor_id,
            func.sum(Sale.total_price).label("monthly_revenue"),
        )
        .filter(Sale.timestamp >= month_start)
        .group_by(Sale.distributor_id)
        .all()
    )
    monthly_rev_map = {r.distributor_id: float(r.monthly_revenue) for r in monthly_revs}

    performance = []
    for row in results:
        growth = _distributor_growth(row.id)
        total_rev = float(row.total_revenue)
        order_count = int(row.order_count)
        aov = round(total_rev / order_count, 2) if order_count > 0 else 0.0
        monthly_rev = monthly_rev_map.get(row.id, 0.0)

        # Auto-tier based on monthly revenue
        auto_tier = _calculate_tier(monthly_rev)

        performance.append({
            "id": row.id,
            "name": row.name,
            "region": row.region,
            "tier": auto_tier,
            "total_volume": int(row.total_volume),
            "total_revenue": total_rev,
            "order_count": order_count,
            "avg_order_value": aov,
            "monthly_revenue": monthly_rev,
            "growth_percent": growth,
        })

    return performance


def _calculate_tier(monthly_revenue: float) -> str:
    """
    Auto-rank distributors into tiers based on monthly revenue.
      Gold:   >= 5000 GHC/month
      Silver: >= 2000 GHC/month
      Bronze: < 2000 GHC/month
    """
    if monthly_revenue >= 5000:
        return "Gold"
    elif monthly_revenue >= 2000:
        return "Silver"
    else:
        return "Bronze"


def _distributor_growth(distributor_id: int) -> float:
    """
    Month-over-month growth for a single distributor.
    Compares current month revenue to previous month revenue.
    """
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

    current_rev = (
        db.session.query(func.coalesce(func.sum(Sale.total_price), 0))
        .filter(
            Sale.distributor_id == distributor_id,
            Sale.timestamp >= current_month_start,
        )
        .scalar()
    )
    prev_rev = (
        db.session.query(func.coalesce(func.sum(Sale.total_price), 0))
        .filter(
            Sale.distributor_id == distributor_id,
            Sale.timestamp >= prev_month_start,
            Sale.timestamp < current_month_start,
        )
        .scalar()
    )

    return calculate_growth_trend(float(current_rev), float(prev_rev))


# ══════════════════════════════════════════════
#  STATS & GROWTH TRENDS
# ══════════════════════════════════════════════

def calculate_growth_trend(current_value: float, previous_value: float) -> float:
    """
    Pure function — percentage change between two periods.
    Positive for growth, negative for decline, 0.0 when no baseline.
    """
    if previous_value == 0:
        return 100.0 if current_value > 0 else 0.0
    return round(((current_value - previous_value) / previous_value) * 100, 2)


def get_sales_stats():
    """
    Aggregate sales data for dashboard stat cards and trend charts.
    Returns weekly sales, monthly sales, total revenue, and a 12-month
    revenue timeline with month-over-month growth.
    """
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Aggregate KPIs
    weekly_sales = (
        db.session.query(func.coalesce(func.sum(Sale.quantity_sold), 0))
        .filter(Sale.timestamp >= week_start)
        .scalar()
    )
    weekly_revenue = (
        db.session.query(func.coalesce(func.sum(Sale.total_price), 0))
        .filter(Sale.timestamp >= week_start)
        .scalar()
    )
    monthly_sales = (
        db.session.query(func.coalesce(func.sum(Sale.quantity_sold), 0))
        .filter(Sale.timestamp >= month_start)
        .scalar()
    )
    monthly_revenue = (
        db.session.query(func.coalesce(func.sum(Sale.total_price), 0))
        .filter(Sale.timestamp >= month_start)
        .scalar()
    )
    total_revenue = (
        db.session.query(func.coalesce(func.sum(Sale.total_price), 0)).scalar()
    )
    total_sales_volume = (
        db.session.query(func.coalesce(func.sum(Sale.quantity_sold), 0)).scalar()
    )

    # Previous-period comparison
    prev_week_start = week_start - timedelta(days=7)
    prev_weekly_sales = (
        db.session.query(func.coalesce(func.sum(Sale.quantity_sold), 0))
        .filter(Sale.timestamp >= prev_week_start, Sale.timestamp < week_start)
        .scalar()
    )

    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_monthly_sales = (
        db.session.query(func.coalesce(func.sum(Sale.quantity_sold), 0))
        .filter(Sale.timestamp >= prev_month_start, Sale.timestamp < month_start)
        .scalar()
    )

    # Monthly revenue timeline (Jan to Dec of the current year)
    current_year = now.year
    
    monthly_data = (
        db.session.query(
            extract("month", Sale.timestamp).label("month"),
            func.sum(Sale.total_price).label("revenue"),
            func.sum(Sale.quantity_sold).label("volume"),
        )
        .filter(extract("year", Sale.timestamp) == current_year)
        .group_by("month")
        .order_by("month")
        .all()
    )
    
    data_map = {int(r.month): r for r in monthly_data}
    timeline = []
    
    # Always return 12 months (Jan to Dec)
    for month_idx in range(1, 13):
        row = data_map.get(month_idx)
        rev = float(row.revenue) if row else 0.0
        vol = int(row.volume) if row else 0
        
        # Calculate growth relative to previous month in the timeline
        prev_rev = timeline[-1]["revenue"] if month_idx > 1 else 0.0
        growth = calculate_growth_trend(rev, prev_rev)
        
        timeline.append({
            "year": current_year,
            "month": month_idx,
            "revenue": rev,
            "volume": vol,
            "growth_percent": growth,
        })

    return {
        "weekly_sales": int(weekly_sales),
        "weekly_revenue": float(weekly_revenue),
        "weekly_growth": calculate_growth_trend(
            float(weekly_sales), float(prev_weekly_sales)
        ),
        "monthly_sales": int(monthly_sales),
        "monthly_revenue": float(monthly_revenue),
        "monthly_growth": calculate_growth_trend(
            float(monthly_sales), float(prev_monthly_sales)
        ),
        "total_revenue": float(total_revenue),
        "total_sales_volume": int(total_sales_volume),
        "monthly_timeline": timeline,
    }


# ══════════════════════════════════════════════
#  CUSTOM REPORTS
# ══════════════════════════════════════════════

def generate_report(start_date: str | None = None, end_date: str | None = None,
                    category: str | None = None, distributor_id: int | None = None):
    """
    Generate a custom performance report filtered by date range,
    product category, and/or distributor.

    Returns per-product breakdown with aggregated metrics.
    """
    q = (
        db.session.query(
            Product.name.label("product_name"),
            Product.sku,
            Product.category,
            Distributor.name.label("distributor_name"),
            func.sum(Sale.quantity_sold).label("total_volume"),
            func.sum(Sale.total_price).label("total_revenue"),
            func.count(Sale.id).label("order_count"),
            func.min(Sale.timestamp).label("first_sale"),
            func.max(Sale.timestamp).label("last_sale"),
        )
        .join(Sale, Sale.product_id == Product.id)
        .join(Distributor, Sale.distributor_id == Distributor.id)
    )

    # Apply filters
    if start_date:
        q = q.filter(Sale.timestamp >= datetime.fromisoformat(start_date))
    if end_date:
        end_dt = datetime.fromisoformat(end_date).replace(
            hour=23, minute=59, second=59
        )
        q = q.filter(Sale.timestamp <= end_dt)
    if category:
        q = q.filter(Product.category.ilike(f"%{category}%"))
    if distributor_id:
        q = q.filter(Sale.distributor_id == distributor_id)

    rows = (
        q.group_by(
            Product.name, Product.sku, Product.category, Distributor.name
        )
        .order_by(func.sum(Sale.total_price).desc())
        .all()
    )

    total_revenue = sum(float(r.total_revenue) for r in rows)
    total_volume = sum(int(r.total_volume) for r in rows)

    report_data = []
    for r in rows:
        rev = float(r.total_revenue)
        vol = int(r.total_volume)
        orders = int(r.order_count)
        report_data.append({
            "product_name": r.product_name,
            "sku": r.sku,
            "category": r.category,
            "distributor_name": r.distributor_name,
            "total_volume": vol,
            "total_revenue": rev,
            "order_count": orders,
            "avg_order_value": round(rev / orders, 2) if orders > 0 else 0,
            "revenue_share_pct": round((rev / total_revenue) * 100, 2) if total_revenue > 0 else 0,
            "first_sale": r.first_sale.isoformat() if r.first_sale else None,
            "last_sale": r.last_sale.isoformat() if r.last_sale else None,
        })

    return {
        "filters_applied": {
            "start_date": start_date,
            "end_date": end_date,
            "category": category,
            "distributor_id": distributor_id,
        },
        "summary": {
            "total_revenue": total_revenue,
            "total_volume": total_volume,
            "total_line_items": len(report_data),
        },
        "data": report_data,
    }
