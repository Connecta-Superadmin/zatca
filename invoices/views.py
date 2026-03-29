# invoices/views.py
import hashlib
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse
from .models import Invoice, AuditLog
from .validators import validate_file_type, validate_file_size, check_duplicate, validate_image_quality


@login_required
def upload_invoice(request):
    """Upload invoice image(s) with mandatory tagging. Supports single and bulk upload."""
    
    if not request.user.can_upload():
        messages.error(request, "You don't have permission to upload invoices.")
        return redirect('invoices:list')
    
    if request.method == 'POST':
        upload_mode = request.POST.get('upload_mode', 'single')
        invoice_type = request.POST.get('invoice_type')
        notes = request.POST.get('notes', '')
        
        # Validate mandatory tag
        if not invoice_type or invoice_type not in ['purchase', 'sales', 'other']:
            messages.error(request, '⚠️ Please select an invoice type (Purchase, Sales, or Other).')
            return render(request, 'invoices/upload.html')
        
        if upload_mode == 'bulk':
            return _handle_bulk_upload(request, invoice_type, notes)
        else:
            return _handle_single_upload(request, invoice_type, notes)
    
    return render(request, 'invoices/upload.html')


def _handle_single_upload(request, invoice_type, notes):
    """Handle single file upload."""
    file = request.FILES.get('invoice_file')
    
    if not file:
        messages.error(request, '⚠️ Please select a file to upload.')
        return render(request, 'invoices/upload.html')
    
    # Run validations
    try:
        validate_file_type(file)
        validate_file_size(file)
        validate_image_quality(file)
        file_hash = check_duplicate(file)
    except Exception as e:
        messages.error(request, f'❌ {str(e)}')
        return render(request, 'invoices/upload.html')
    
    # Create invoice record
    invoice = Invoice(
        image=file,
        original_filename=file.name,
        file_size=file.size,
        file_type=file.content_type,
        image_hash=file_hash,
        invoice_type=invoice_type,
        uploaded_by=request.user,
        status=Invoice.Status.UPLOADED,
        notes=notes,
    )
    invoice.save()
    
    # Create audit log
    AuditLog.objects.create(
        invoice=invoice,
        action=AuditLog.Action.UPLOAD,
        performed_by=request.user,
        details={
            'filename': file.name,
            'file_size': file.size,
            'invoice_type': invoice_type,
        },
        ip_address=get_client_ip(request),
    )
    
    messages.success(
        request,
        f'✅ Invoice uploaded successfully! Reference: INV-{str(invoice.reference_id)[:8]}'
    )
    return redirect('invoices:detail', pk=invoice.pk)


def _handle_bulk_upload(request, invoice_type, notes):
    """Handle bulk (multiple) file upload."""
    files = request.FILES.getlist('invoice_files')
    
    if not files:
        messages.error(request, '⚠️ Please select at least one file to upload.')
        return render(request, 'invoices/upload.html')
    
    total_files = len(files)
    success_count = 0
    failed_files = []
    uploaded_invoices = []
    
    for file in files:
        try:
            validate_file_type(file)
            validate_file_size(file)
            validate_image_quality(file)
            file_hash = check_duplicate(file)
        except Exception as e:
            failed_files.append((file.name, str(e)))
            continue
        
        invoice = Invoice(
            image=file,
            original_filename=file.name,
            file_size=file.size,
            file_type=file.content_type,
            image_hash=file_hash,
            invoice_type=invoice_type,
            uploaded_by=request.user,
            status=Invoice.Status.UPLOADED,
            notes=notes,
        )
        invoice.save()
        uploaded_invoices.append(invoice)
        
        AuditLog.objects.create(
            invoice=invoice,
            action=AuditLog.Action.UPLOAD,
            performed_by=request.user,
            details={
                'filename': file.name,
                'file_size': file.size,
                'invoice_type': invoice_type,
                'upload_mode': 'bulk',
            },
            ip_address=get_client_ip(request),
        )
        success_count += 1
    
    if success_count == 0:
        messages.error(request, '❌ No invoices were uploaded. Please check the errors below.')
        for fname, error in failed_files:
            messages.warning(request, f'⚠️ {fname}: {error}')
        return render(request, 'invoices/upload.html')
    
    # Show detailed summary
    return render(request, 'invoices/bulk_result.html', {
        'total_files': total_files,
        'success_count': success_count,
        'failed_count': len(failed_files),
        'failed_files': failed_files,
        'uploaded_invoices': uploaded_invoices,
        'invoice_type': invoice_type,
    })


@login_required
def invoice_list(request):
    """List all invoices with filtering and search."""
    invoices = Invoice.objects.all()
    
    # Filters
    invoice_type = request.GET.get('type')
    status = request.GET.get('status')
    search = request.GET.get('search')
    
    if invoice_type:
        invoices = invoices.filter(invoice_type=invoice_type)
    if status:
        invoices = invoices.filter(status=status)
    if search:
        invoices = invoices.filter(
            Q(original_filename__icontains=search) |
            Q(reference_id__icontains=search) |
            Q(notes__icontains=search)
        )
    
    # Pagination
    paginator = Paginator(invoices, 20)
    page = request.GET.get('page')
    invoices = paginator.get_page(page)
    
    context = {
        'invoices': invoices,
        'type_choices': Invoice.InvoiceType.choices,
        'status_choices': Invoice.Status.choices,
        'current_type': invoice_type,
        'current_status': status,
        'search': search or '',
    }
    return render(request, 'invoices/list.html', context)


@login_required
def invoice_detail(request, pk):
    """View invoice details and audit trail."""
    invoice = get_object_or_404(Invoice, pk=pk)
    audit_logs = invoice.audit_logs.all()[:20]
    
    # Log the view
    AuditLog.objects.create(
        invoice=invoice,
        action=AuditLog.Action.VIEWED,
        performed_by=request.user,
        ip_address=get_client_ip(request),
    )
    
    return render(request, 'invoices/detail.html', {
        'invoice': invoice,
        'audit_logs': audit_logs,
    })


@login_required
def delete_invoice(request, pk):
    """Delete an invoice with permission check and audit logging."""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    # Only the uploader or admin can delete
    if invoice.uploaded_by != request.user and not request.user.is_admin():
        messages.error(request, "You don't have permission to delete this invoice.")
        return redirect('invoices:detail', pk=pk)
    
    # Don't allow deleting posted invoices
    if invoice.status == Invoice.Status.POSTED_TO_ODOO:
        messages.error(request, '❌ Cannot delete an invoice that has been posted to Odoo.')
        return redirect('invoices:detail', pk=pk)
    
    if request.method == 'POST':
        ref = str(invoice.reference_id)[:8]
        invoice.delete()
        messages.success(request, f'🗑️ Invoice INV-{ref} has been deleted.')
        return redirect('invoices:list')
    
    return render(request, 'invoices/delete_confirm.html', {'invoice': invoice})


@login_required
def download_invoice(request, pk):
    """Download the original invoice file."""
    invoice = get_object_or_404(Invoice, pk=pk)
    content_type = invoice.file_type or mimetypes.guess_type(invoice.original_filename)[0] or 'application/octet-stream'
    response = FileResponse(invoice.image.open('rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{invoice.original_filename}"'
    return response


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')