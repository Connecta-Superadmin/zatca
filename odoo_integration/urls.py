# odoo_integration/urls.py
from django.urls import path
from . import views

app_name = 'odoo_integration'

urlpatterns = [
    path('test/', views.test_connection, name='test_connection'),
    path('sync/<int:invoice_id>/', views.sync_to_odoo, name='sync'),
    path('sync/<int:invoice_id>/ajax/', views.sync_ajax, name='sync_ajax'),
    path('history/', views.sync_history, name='history'),
]
