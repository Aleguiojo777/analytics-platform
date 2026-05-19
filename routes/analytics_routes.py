from flask import Blueprint
from controllers.analytics_controller import export_smart_insights_pdf, get_executive_summary, get_table_analytics

bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

bp.add_url_rule('/table', view_func=get_table_analytics, methods=['POST'])
bp.add_url_rule('/executive-summary', view_func=get_executive_summary, methods=['POST'])
bp.add_url_rule('/export-pdf', view_func=export_smart_insights_pdf, methods=['POST'])
