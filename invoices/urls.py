# invoices/urls.py
from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('', views.invoice_list, name='list'),
    path('upload/', views.upload_invoice, name='upload'),
    path('<int:pk>/', views.invoice_detail, name='detail'),
    path('<int:pk>/delete/', views.delete_invoice, name='delete'),
    path('<int:pk>/download/', views.download_invoice, name='download'),
]