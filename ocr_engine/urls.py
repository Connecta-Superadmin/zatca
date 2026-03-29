# ocr_engine/urls.py
from django.urls import path
from . import views

app_name = 'ocr_engine'

urlpatterns = [
    path('process/<int:invoice_id>/', views.trigger_ocr, name='process'),
    path('review/<int:invoice_id>/', views.review_ocr, name='review'),
]