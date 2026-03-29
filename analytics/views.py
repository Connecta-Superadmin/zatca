# analytics/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from invoices.models import Invoice, AuditLog
from accounts.models import CustomUser


@login_required
def dashboard(request):
    """Main analytics dashboard with summary stats and chart data."""
    invoices = Invoice.objects.all()

    # Summary counts
    total_invoices = invoices.count()
    purchase_count = invoices.filter(invoice_type='purchase').count()
    sales_count = invoices.filter(invoice_type='sales').count()
    other_count = invoices.filter(invoice_type='other').count()

    # Status counts
    uploaded_count = invoices.filter(status='uploaded').count()
    ocr_complete_count = invoices.filter(status='ocr_complete').count()
    verified_count = invoices.filter(status='verified').count()
    posted_count = invoices.filter(status='posted').count()
    failed_count = invoices.filter(status='failed').count()

    # Last 30 days daily uploads
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_uploads = (
        invoices.filter(created_at__gte=thirty_days_ago)
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    chart_labels = [entry['date'].strftime('%d %b') for entry in daily_uploads]
    chart_data = [entry['count'] for entry in daily_uploads]

    # Top uploaders
    top_uploaders = (
        invoices.values('uploaded_by__username')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    # Recent activity
    recent_activity = AuditLog.objects.select_related('invoice', 'performed_by').exclude(
        action='viewed'
    ).order_by('-timestamp')[:10]

    context = {
        'total_invoices': total_invoices,
        'purchase_count': purchase_count,
        'sales_count': sales_count,
        'other_count': other_count,
        'uploaded_count': uploaded_count,
        'ocr_complete_count': ocr_complete_count,
        'verified_count': verified_count,
        'posted_count': posted_count,
        'failed_count': failed_count,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'top_uploaders': top_uploaders,
        'recent_activity': recent_activity,
    }
    return render(request, 'analytics/dashboard.html', context)
