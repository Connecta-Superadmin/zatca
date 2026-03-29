# invoices/admin.py
from django.contrib import admin
from .models import Invoice, AuditLog


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('reference_id', 'invoice_type', 'status', 'uploaded_by', 'created_at')
    list_filter = ('invoice_type', 'status', 'created_at')
    search_fields = ('reference_id', 'original_filename', 'notes')
    readonly_fields = ('reference_id', 'image_hash', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'action', 'performed_by', 'timestamp')
    list_filter = ('action', 'timestamp')
    readonly_fields = ('invoice', 'action', 'performed_by', 'details', 'ip_address', 'timestamp')