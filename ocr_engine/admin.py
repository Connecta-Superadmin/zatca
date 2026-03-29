# ocr_engine/admin.py
from django.contrib import admin
from .models import OCRResult


@admin.register(OCRResult)
class OCRResultAdmin(admin.ModelAdmin):
    list_display = (
        'invoice', 'vendor_name', 'vendor_vat', 'invoice_number',
        'total_amount', 'overall_confidence', 'is_reviewed', 'processed_at'
    )
    list_filter = ('is_reviewed', 'processed_at')
    search_fields = ('vendor_name', 'vendor_vat', 'invoice_number')