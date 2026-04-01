"""
API route definitions — thin controllers that delegate to the service layer.

Endpoints:
  GET  /api/inventory              - All products with stock status
  POST /api/sales                  - Record a sale (atomic transaction)
  POST /api/restock                - Restock a product
  POST /api/adjustment             - Manual stock adjustment
  GET  /api/transactions           - Stock audit log
  GET  /api/performance            - Distributor intelligence
  GET  /api/stats                  - Sales stats & growth trends
  GET  /api/analytics/forecast     - Burn rate & out-of-stock predictions
  GET  /api/alerts                 - Stock alerts (low/critical)
  GET  /api/alerts/summary         - Daily intelligence summary
  GET  /api/reports                - Custom filterable reports
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import services

api = Blueprint("api", __name__, url_prefix="/api")


# ══════════════════════════════════════════════
#  INVENTORY
# ══════════════════════════════════════════════

@api.route("/inventory", methods=["GET"])
def get_inventory():
    """Fetch all stock items with computed status."""
    try:
        items = services.get_all_inventory()
        summary = services.get_inventory_summary()
        return jsonify({
            "success": True,
            "data": items,
            "summary": summary,
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api.route("/products", methods=["POST"])
def create_product():
    """
    Register a new product in the system.
    Body: { name, sku, category, price, quantity, min_stock_level }
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "JSON body required"}), 400
    try:
        product = services.create_product(payload)
        return jsonify({"success": True, "data": product}), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  SALES (atomic transaction)
# ══════════════════════════════════════════════

@api.route("/sales", methods=["POST"])
def create_sale():
    """
    Record a sale and deduct stock within an atomic transaction.
    Also creates an audit log entry in stock_transactions.

    Body: { product_id, distributor_id, quantity_sold, sale_date? }
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Request body must be JSON."}), 400

    required = ["product_id", "distributor_id", "quantity_sold"]
    missing = [f for f in required if f not in payload]
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required fields: {', '.join(missing)}",
        }), 400

    try:
        sale = services.record_sale(
            product_id=int(payload["product_id"]),
            distributor_id=int(payload["distributor_id"]),
            quantity_sold=int(payload["quantity_sold"]),
            sale_date=payload.get("sale_date"),
        )
        return jsonify({"success": True, "data": sale}), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  RESTOCK & ADJUSTMENT
# ══════════════════════════════════════════════

@api.route("/restock", methods=["POST"])
def restock():
    """
    Add stock to a product. Logged in stock_transactions.

    Body: { product_id, quantity, reason? }
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Request body must be JSON."}), 400

    required = ["product_id", "quantity"]
    missing = [f for f in required if f not in payload]
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required fields: {', '.join(missing)}",
        }), 400

    try:
        result = services.record_restock(
            product_id=int(payload["product_id"]),
            quantity=int(payload["quantity"]),
            reason=payload.get("reason", "Manual restock"),
        )
        return jsonify({"success": True, "data": result}), 200
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api.route("/adjustment", methods=["POST"])
def adjustment():
    """
    Set product stock to an exact number (inventory correction).

    Body: { product_id, new_quantity, reason? }
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Request body must be JSON."}), 400

    required = ["product_id", "new_quantity"]
    missing = [f for f in required if f not in payload]
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required fields: {', '.join(missing)}",
        }), 400

    try:
        result = services.record_adjustment(
            product_id=int(payload["product_id"]),
            new_quantity=int(payload["new_quantity"]),
            reason=payload.get("reason", "Manual adjustment"),
        )
        return jsonify({"success": True, "data": result}), 200
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  STOCK AUDIT LOG
# ══════════════════════════════════════════════

@api.route("/transactions", methods=["GET"])
def get_transactions():
    """
    Retrieve stock audit log.

    Query params: product_id (optional), limit (default 50)
    """
    try:
        product_id = request.args.get("product_id", type=int)
        limit = request.args.get("limit", 50, type=int)
        data = services.get_stock_transactions(product_id=product_id, limit=limit)
        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  DISTRIBUTOR PERFORMANCE
# ══════════════════════════════════════════════

@api.route("/performance", methods=["GET"])
def get_performance():
    """
    Revenue and volume per distributor with:
    - MoM growth, AOV, order count, auto-tier (Gold/Silver/Bronze)
    """
    try:
        data = services.get_distributor_performance()
        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  STATS & TRENDS
# ══════════════════════════════════════════════

@api.route("/stats", methods=["GET"])
def get_stats():
    """Aggregate weekly/monthly sales and growth trends."""
    try:
        stats = services.get_sales_stats()
        return jsonify({"success": True, "data": stats}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  ANALYTICS & FORECAST
# ══════════════════════════════════════════════

@api.route("/analytics/forecast", methods=["GET"])
def get_forecast():
    """
    Predictive analytics for each product:
    - Average daily burn rate (last 30 days)
    - Estimated days until out of stock
    - Restock recommendations
    """
    try:
        data = services.get_forecast()
        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  STOCK ALERTS
# ══════════════════════════════════════════════

@api.route("/alerts", methods=["GET"])
def get_alerts():
    """Products below their min_stock_level threshold."""
    try:
        data = services.get_stock_alerts()
        return jsonify({"success": True, "data": data, "count": len(data)}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api.route("/alerts/summary", methods=["GET"])
def get_daily_summary():
    """
    Daily intelligence summary:
    - Top 3 best-selling products
    - 3 worst-performing distributors
    - Today's revenue & volume
    - Stock alert count
    """
    try:
        data = services.get_daily_summary()
        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  CUSTOM REPORTS
# ══════════════════════════════════════════════

@api.route("/reports/excel", methods=["GET"])
def get_excel_report():
    """Download a complete Excel report of inventory and sales."""
    from flask import send_file
    try:
        excel_data = services.export_to_excel()
        return send_file(
            excel_data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"Prism_Report_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  REVENUE GROWTH TRENDS
# ══════════════════════════════════════════════

@api.route("/trends", methods=["GET"])
def get_trends():
    """Revenue-focused trend data: 7-day daily breakdown, weekly/monthly with WoW/MoM growth."""
    try:
        data = services.get_sales_trends()
        return jsonify({"success": True, "data": data}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  SOCIAL MEDIA QUICK-ORDER
# ══════════════════════════════════════════════

@api.route("/quick-order", methods=["POST"])
def quick_order():
    """
    Social media order intake — minimal fields for admin efficiency.

    Body: { ref, sku, quantity, sale_date? }
    ref: Distributor ref code, e.g. "D5"
    sku: Product SKU string
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "JSON body required."}), 400

    required = ["ref", "sku", "quantity"]
    missing = [f for f in required if f not in payload]
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        sale = services.record_quick_order(
            ref=str(payload["ref"]),
            sku=str(payload["sku"]),
            quantity=int(payload["quantity"]),
            sale_date=payload.get("sale_date"),
        )
        return jsonify({"success": True, "data": sale}), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ══════════════════════════════════════════════
#  AI BRAIN
# ══════════════════════════════════════════════

@api.route("/ai/brain", methods=["POST"])
def ai_brain():
    """
    AI-powered business intelligence & query engine.
    Body: { "query": "string" }
    """
    import ai_service
    
    payload = request.get_json(silent=True)
    if not payload or "query" not in payload:
        return jsonify({"success": False, "error": "Query required."}), 400
        
    try:
        response = ai_service.ask_ai_brain(payload["query"])
        return jsonify({"success": True, "data": response}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
