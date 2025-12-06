from django import template
from finanzas.services import DashboardService

register = template.Library()

@register.simple_tag
def get_dashboard_stats():
    """Retorna las métricas para el dashboard"""
    return DashboardService.get_metricas_financieras()