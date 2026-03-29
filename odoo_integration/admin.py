# odoo_integration/admin.py
from django.contrib import admin
from .models import OdooSyncLog


@admin.register(OdooSyncLog)
class OdooSyncLogAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'invoice_type', 'status', 'odoo_invoice_name', 'synced_by', 'created_at']
    list_filter = ['status', 'invoice_type', 'created_at']
    search_fields = ['invoice__reference_id', 'odoo_invoice_name']
    readonly_fields = ['created_at', 'updated_at', 'synced_data']
    raw_id_fields = ['invoice', 'synced_by']
    
    def has_add_permission(self, request):
        return False  # Syncs should only be created via the sync process
