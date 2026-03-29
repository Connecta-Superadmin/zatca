# odoo_integration/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from invoices.models import Invoice
from .models import OdooSyncLog
from .services import OdooClient, OdooConnectionError, sync_invoice_to_odoo


@login_required
def test_connection(request):
    """Test Odoo connection and show status."""
    try:
        odoo = OdooClient()
        result = odoo.test_connection()
        
        if result['success']:
            messages.success(request, f"✅ {result['message']}")
        else:
            messages.error(request, f"❌ Connection failed: {result['message']}")
    except OdooConnectionError as e:
        messages.error(request, f"❌ {str(e)}")
    except Exception as e:
        messages.error(request, f"❌ Unexpected error: {str(e)}")
    
    return redirect(request.META.get('HTTP_REFERER', 'invoices:list'))


@login_required
def sync_to_odoo(request, invoice_id):
    """Sync invoice to Odoo - shows confirmation page or processes sync."""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    # Check if already synced
    existing_sync = OdooSyncLog.objects.filter(
        invoice=invoice,
        status=OdooSyncLog.Status.SYNCED
    ).first()
    
    if request.method == 'POST':
        invoice_type = request.POST.get('invoice_type', 'out_invoice')
        
        result = sync_invoice_to_odoo(
            invoice_id=invoice.id,
            invoice_type=invoice_type,
            user=request.user
        )
        
        if result['success']:
            messages.success(
                request,
                f"✅ Invoice synced to Odoo as {result['odoo_name']}! "
                f'<a href="{result["odoo_url"]}" target="_blank">Open in Odoo</a>'
            )
            return redirect('invoices:detail', pk=invoice.id)
        else:
            messages.error(request, f"❌ Sync failed: {result['error']}")
            return redirect('odoo_integration:sync', invoice_id=invoice.id)
    
    # GET - show confirmation page
    # Get OCR data for preview
    ocr_data = invoice.ocr_data or {}
    if hasattr(invoice, 'ocr_result'):
        ocr_result = invoice.ocr_result
        ocr_data = {
            'vendor_name': ocr_result.vendor_name,
            'vendor_vat': ocr_result.vendor_vat,
            'buyer_name': ocr_result.buyer_name,
            'invoice_number': ocr_result.invoice_number,
            'invoice_date': ocr_result.invoice_date,
            'total_amount': ocr_result.total_amount,
            'line_items': ocr_result.line_items or [],
        }
    
    context = {
        'invoice': invoice,
        'ocr_data': ocr_data,
        'existing_sync': existing_sync,
        'sync_history': OdooSyncLog.objects.filter(invoice=invoice)[:5],
    }
    return render(request, 'odoo_integration/sync_confirm.html', context)


@login_required
def sync_history(request):
    """View all Odoo sync history."""
    syncs = OdooSyncLog.objects.select_related('invoice', 'synced_by').all()
    
    # Filters
    status = request.GET.get('status')
    if status:
        syncs = syncs.filter(status=status)
    
    context = {
        'syncs': syncs[:100],
        'status_choices': OdooSyncLog.Status.choices,
        'selected_status': status,
    }
    return render(request, 'odoo_integration/sync_history.html', context)


@login_required
@require_POST
def sync_ajax(request, invoice_id):
    """AJAX endpoint for quick sync."""
    invoice_type = request.POST.get('invoice_type', 'out_invoice')
    
    result = sync_invoice_to_odoo(
        invoice_id=invoice_id,
        invoice_type=invoice_type,
        user=request.user
    )
    
    return JsonResponse(result)
