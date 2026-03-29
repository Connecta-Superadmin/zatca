# invoices/models.py
import uuid
import hashlib
from django.db import models
from django.conf import settings


class Invoice(models.Model):
    """Core invoice model - stores uploaded invoice images with metadata."""
    
    class InvoiceType(models.TextChoices):
        PURCHASE = 'purchase', 'Purchase Invoice'
        SALES = 'sales', 'Sales Invoice'
        OTHER = 'other', 'Other'
    
    class Status(models.TextChoices):
        UPLOADED = 'uploaded', 'Uploaded'
        VALIDATED = 'validated', 'Validated'
        OCR_PROCESSING = 'ocr_processing', 'OCR Processing'
        OCR_COMPLETE = 'ocr_complete', 'OCR Complete'
        VERIFIED = 'verified', 'Verified'
        POSTED_TO_ODOO = 'posted', 'Posted to Odoo'
        FAILED = 'failed', 'Failed'
        REJECTED = 'rejected', 'Rejected'
    
    # Unique reference
    reference_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    
    # Image file
    image = models.FileField(upload_to='invoices/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    file_type = models.CharField(max_length=50)  # image/jpeg, image/png, application/pdf
    image_hash = models.CharField(max_length=64, db_index=True, help_text="SHA-256 hash for duplicate detection")
    
    # Mandatory tagging (Phase 1)
    invoice_type = models.CharField(
        max_length=20,
        choices=InvoiceType.choices,
        help_text="Required: classify as Purchase, Sales, or Other"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    
    # User tracking
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='uploaded_invoices'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Phase 2 fields (nullable for now)
    ocr_data = models.JSONField(null=True, blank=True, help_text="OCR extracted data")
    odoo_invoice_id = models.IntegerField(null=True, blank=True, help_text="Odoo invoice record ID")
    zatca_status = models.CharField(max_length=50, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['invoice_type']),
            models.Index(fields=['image_hash']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"INV-{str(self.reference_id)[:8]} | {self.get_invoice_type_display()} | {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        # Calculate hash if not set
        if not self.image_hash and self.image:
            self.image_hash = self.calculate_hash()
        super().save(*args, **kwargs)
    
    def calculate_hash(self):
        """Calculate SHA-256 hash of the file for duplicate detection."""
        sha256 = hashlib.sha256()
        for chunk in self.image.chunks():
            sha256.update(chunk)
        return sha256.hexdigest()


class AuditLog(models.Model):
    """Complete audit trail for all invoice actions."""
    
    class Action(models.TextChoices):
        UPLOAD = 'upload', 'Uploaded'
        TAG_CHANGED = 'tag_changed', 'Tag Changed'
        STATUS_CHANGED = 'status_changed', 'Status Changed'
        OCR_PROCESSED = 'ocr_processed', 'OCR Processed'
        SENT_TO_ODOO = 'sent_to_odoo', 'Sent to Odoo'
        ZATCA_VERIFIED = 'zatca_verified', 'ZATCA Verified'
        REJECTED = 'rejected', 'Rejected'
        VIEWED = 'viewed', 'Viewed'
    
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=Action.choices)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    details = models.JSONField(default=dict, help_text="Before/after state and extra info")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.get_action_display()} - {self.invoice.reference_id} - {self.timestamp}"