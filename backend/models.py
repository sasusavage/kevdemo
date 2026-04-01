"""
SQLAlchemy models for the Prism Portal Inventory Management System.

Tables:
  - products           : product catalog with stock tracking & thresholds
  - distributors       : partner distributor entities
  - sales              : immutable sales ledger linking products <-> distributors
  - stock_transactions : audit log for every inventory change
"""
from datetime import datetime, timezone
from extensions import db


class Product(db.Model):
    """Represents a product / SKU in the warehouse."""

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)  # Revenue price
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0.00) # Purchase cost
    category = db.Column(db.String(100), nullable=True)
    image_url = db.Column(db.Text, nullable=True)
    min_stock_level = db.Column(db.Integer, nullable=False, default=20)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    sales = db.relationship("Sale", back_populates="product", lazy="dynamic")
    stock_transactions = db.relationship(
        "StockTransaction", back_populates="product", lazy="dynamic"
    )

    def to_dict(self):
        """Serialize to JSON-safe dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "sku": self.sku,
            "quantity": self.quantity,
            "price": float(self.price),
            "cost_price": float(self.cost_price),
            "margin": float(self.price - self.cost_price) if self.price and self.cost_price else 0.0,
            "margin_percent": float(((self.price - self.cost_price) / self.price) * 100) if self.price and self.price > 0 else 0.0,
            "category": self.category,
            "image_url": self.image_url,
            "min_stock_level": self.min_stock_level,
            "status": self.stock_status,
            "alert_level": self.alert_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def stock_status(self):
        """Derive human-readable stock status using min_stock_level threshold."""
        if self.quantity <= 0:
            return "Out of Stock"
        elif self.quantity <= (self.min_stock_level // 2):
            return "Critical"
        elif self.quantity <= self.min_stock_level:
            return "Low Stock"
        return "In Stock"

    @property
    def alert_level(self):
        """Return alert severity: none, warning, critical."""
        if self.quantity <= 0:
            return "critical"
        elif self.quantity <= (self.min_stock_level // 2):
            return "critical"
        elif self.quantity <= self.min_stock_level:
            return "warning"
        return "none"


class Distributor(db.Model):
    """Represents a distribution partner entity."""

    __tablename__ = "distributors"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    contact = db.Column(db.String(200), nullable=True)
    region = db.Column(db.String(100), nullable=True)
    tier = db.Column(db.String(20), nullable=True)
    # Commission rate as a decimal fraction, e.g. 0.05 = 5%.
    # Migration: ALTER TABLE distributors ADD COLUMN commission_rate NUMERIC(5,4) NOT NULL DEFAULT 0.0500;
    commission_rate = db.Column(db.Numeric(5, 4), nullable=False, default=0.0500)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    sales = db.relationship("Sale", back_populates="distributor", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "contact": self.contact,
            "region": self.region,
            "tier": self.tier,
            "commission_rate": float(self.commission_rate),
            "ref_code": f"D{self.id}",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Sale(db.Model):
    """Immutable sales record linking a product to a distributor."""

    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False, index=True
    )
    distributor_id = db.Column(
        db.Integer, db.ForeignKey("distributors.id"), nullable=False, index=True
    )
    quantity_sold = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Numeric(12, 2), nullable=False)  # Total Revenue
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0.00) # Cost at time of sale
    profit = db.Column(db.Numeric(12, 2), nullable=False, default=0.00) # total_price - (unit_cost * quantity)
    # commission_earned = distributor.commission_rate * total_price, snapshotted at sale time.
    # Migration: ALTER TABLE sales ADD COLUMN commission_earned NUMERIC(12,2) NOT NULL DEFAULT 0.00;
    commission_earned = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Relationships
    product = db.relationship("Product", back_populates="sales")
    distributor = db.relationship("Distributor", back_populates="sales")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "distributor_id": self.distributor_id,
            "distributor_name": self.distributor.name if self.distributor else None,
            "quantity_sold": self.quantity_sold,
            "total_price": float(self.total_price),
            "unit_cost": float(self.unit_cost),
            "profit": float(self.profit),
            "commission_earned": float(self.commission_earned),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class StockTransaction(db.Model):
    """
    Audit log for every inventory change.

    Types: SALE, RESTOCK, RETURN, ADJUSTMENT
    Every row records who/what changed stock, by how much, and why.
    """

    __tablename__ = "stock_transactions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False, index=True
    )
    transaction_type = db.Column(
        db.String(20), nullable=False, index=True
    )  # SALE, RESTOCK, RETURN, ADJUSTMENT
    quantity_change = db.Column(db.Integer, nullable=False)  # negative for deductions
    quantity_before = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    reference_id = db.Column(db.Integer, nullable=True)  # links to sale.id etc
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Relationship
    product = db.relationship("Product", back_populates="stock_transactions")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "transaction_type": self.transaction_type,
            "quantity_change": self.quantity_change,
            "quantity_before": self.quantity_before,
            "quantity_after": self.quantity_after,
            "reason": self.reason,
            "reference_id": self.reference_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
