# ocr_engine/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from invoices.models import Invoice, AuditLog
from .models import OCRResult
from .services import process_invoice_ocr


@login_required
def trigger_ocr(request, invoice_id):
    """Trigger OCR processing for an invoice."""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    if invoice.status not in ['uploaded', 'validated', 'failed']:
        messages.warning(request, 'This invoice has already been processed.')
        return redirect('invoices:detail', pk=invoice_id)
    
    result = process_invoice_ocr(invoice_id)
    
    if result['success']:
        messages.success(request, '✅ Data extracted successfully! Please review below.')
    else:
        messages.error(request, f'❌ OCR failed: {result.get("error", "Unknown error")}')
        return redirect('invoices:detail', pk=invoice_id)
    
    return redirect('ocr_engine:review', invoice_id=invoice_id)


@login_required
def review_ocr(request, invoice_id):
    """Review and edit OCR extracted data."""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    try:
        ocr_result = invoice.ocr_result
    except OCRResult.DoesNotExist:
        messages.info(request, 'OCR not run yet. Click "Extract Data" first.')
        return redirect('invoices:detail', pk=invoice_id)
    
    if request.method == 'POST':
        # Save edited fields
        ocr_result.vendor_name = request.POST.get('vendor_name', '')
        ocr_result.vendor_vat = request.POST.get('vendor_vat', '')
        ocr_result.buyer_name = request.POST.get('buyer_name', '')
        ocr_result.buyer_vat = request.POST.get('buyer_vat', '')
        ocr_result.invoice_number = request.POST.get('invoice_number', '')
        
        date_str = request.POST.get('invoice_date', '')
        if date_str:
            try:
                from datetime import datetime
                ocr_result.invoice_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        for field in ['subtotal', 'vat_amount', 'total_amount']:
            val = request.POST.get(field, '')
            if val:
                try:
                    setattr(ocr_result, field, val)
                except (ValueError, TypeError):
                    pass
        
        ocr_result.is_reviewed = True
        ocr_result.reviewed_by = request.user
        ocr_result.save()
        
        invoice.status = Invoice.Status.VERIFIED
        invoice.save()
        
        AuditLog.objects.create(
            invoice=invoice,
            action=AuditLog.Action.STATUS_CHANGED,
            performed_by=request.user,
            details={'new_status': 'verified', 'action': 'OCR reviewed and approved'}
        )
        
        messages.success(request, '✅ Data approved and saved!')
        return redirect('invoices:detail', pk=invoice_id)
    
    # Parse line items for template
    line_items = ocr_result.line_items if ocr_result.line_items else []
    
    context = {
        'invoice': invoice,
        'ocr': ocr_result,
        'line_items': line_items,
    }
    return render(request, 'ocr_engine/review.html', context)