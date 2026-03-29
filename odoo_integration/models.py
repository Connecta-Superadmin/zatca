# odoo_integration/models.py
from django.db import models
from django.conf import settings


class OdooSyncLog(models.Model):
    """Track invoices synced to Odoo."""
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SYNCED = 'synced', 'Synced'
        FAILED = 'failed', 'Failed'
    
    class InvoiceType(models.TextChoices):
        CUSTOMER = 'out_invoice', 'Customer Invoice'
        VENDOR = 'in_invoice', 'Vendor Bill'
    
    invoice = models.ForeignKey(
        'invoices.Invoice',
        on_delete=models.CASCADE,
        related_name='odoo_syncs'
    )
    odoo_invoice_id = models.IntegerField(null=True, blank=True)
    odoo_invoice_name = models.CharField(max_length=100, blank=True)
    odoo_partner_id = models.IntegerField(null=True, blank=True)
    invoice_type = models.CharField(
        max_length=20,
        choices=InvoiceType.choices,
        default=InvoiceType.CUSTOMER
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    error_message = models.TextField(blank=True)
    synced_data = models.JSONField(default=dict, blank=True)
    
    synced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Odoo Sync Log'
        verbose_name_plural = 'Odoo Sync Logs'
    
    def __str__(self):
        return f"{self.invoice} → Odoo ({self.status})"
    
    @property
    def odoo_url(self):
        """Get direct link to invoice in Odoo."""
        if self.odoo_invoice_id:
            from decouple import config
            base_url = config('ODOO_URL', default='')
            return f"{base_url}/web#id={self.odoo_invoice_id}&model=account.move&view_type=form"
        return None
