# ocr_engine/models.py
from django.db import models
from invoices.models import Invoice


class OCRResult(models.Model):
    """Stores OCR extraction results for each invoice."""
    
    invoice = models.OneToOneField(
        Invoice, 
        on_delete=models.CASCADE, 
        related_name='ocr_result'
    )
    
    # Extracted fields
    vendor_name = models.CharField(max_length=255, blank=True)
    vendor_vat = models.CharField(max_length=50, blank=True)
    buyer_name = models.CharField(max_length=255, blank=True)
    buyer_vat = models.CharField(max_length=50, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Raw data
    raw_ocr_response = models.JSONField(default=dict)
    line_items = models.JSONField(default=list)
    
    # Confidence
    overall_confidence = models.FloatField(default=0.0)
    field_confidences = models.JSONField(default=dict)
    
    # QR Code data (ZATCA)
    qr_code_data = models.JSONField(null=True, blank=True)
    
    # Review status
    is_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    
    processed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-processed_at']
    
    def __str__(self):
        return f"OCR: {self.invoice.reference_id} - {self.vendor_name}"