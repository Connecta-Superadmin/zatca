# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """Custom user with roles for the invoice platform."""
    
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administrator'
        ACCOUNTANT = 'accountant', 'Accountant'
        VIEWER = 'viewer', 'Viewer'
        AUDITOR = 'auditor', 'Auditor'
    
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ACCOUNTANT,
    )
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    
    def is_admin(self):
        return self.role == self.Role.ADMIN
    
    def is_accountant(self):
        return self.role == self.Role.ACCOUNTANT
    
    def can_upload(self):
        """Only admins and accountants can upload invoices."""
        return self.role in [self.Role.ADMIN, self.Role.ACCOUNTANT]
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"