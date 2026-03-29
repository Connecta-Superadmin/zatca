# invoices/validators.py
import hashlib
from django.core.exceptions import ValidationError
from django.conf import settings


def validate_file_type(file):
    """Check if uploaded file is JPG, PNG, or PDF."""
    allowed_types = ['image/jpeg', 'image/png', 'application/pdf']
    if file.content_type not in allowed_types:
        raise ValidationError(
            f"File type '{file.content_type}' not allowed. "
            f"Allowed types: JPG, PNG, PDF"
        )


def validate_file_size(file):
    """Check if file is within size limit (10MB)."""
    max_size = getattr(settings, 'MAX_INVOICE_FILE_SIZE', 10 * 1024 * 1024)
    if file.size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ValidationError(
            f"File too large. Maximum size is {max_mb}MB. "
            f"Your file is {file.size / (1024 * 1024):.1f}MB."
        )


def check_duplicate(file, exclude_id=None):
    """Check if this exact image has already been uploaded (hash-based)."""
    from .models import Invoice
    
    sha256 = hashlib.sha256()
    for chunk in file.chunks():
        sha256.update(chunk)
    file_hash = sha256.hexdigest()
    
    # Reset file pointer after reading
    file.seek(0)
    
    query = Invoice.objects.filter(image_hash=file_hash)
    if exclude_id:
        query = query.exclude(id=exclude_id)
    
    if query.exists():
        existing = query.first()
        raise ValidationError(
            f"Duplicate invoice detected! This image matches invoice "
            f"INV-{str(existing.reference_id)[:8]} uploaded on "
            f"{existing.created_at.strftime('%Y-%m-%d %H:%M')}."
        )
    
    return file_hash


def validate_image_quality(file):
    """Basic image quality check (blur detection for images, not PDFs)."""
    if file.content_type == 'application/pdf':
        return True  # Skip blur check for PDFs
    
    try:
        import cv2
        import numpy as np
        
        # Read file into numpy array
        file_bytes = file.read()
        file.seek(0)  # Reset pointer
        
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        
        if img is None:
            raise ValidationError("Could not read image. File may be corrupted.")
        
        # Laplacian variance - lower = more blurry
        laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
        
        BLUR_THRESHOLD = 50  # Adjust based on testing
        if laplacian_var < BLUR_THRESHOLD:
            raise ValidationError(
                f"Image appears to be too blurry (quality score: {laplacian_var:.0f}). "
                f"Please upload a clearer image."
            )
        
        return True
    except ImportError:
        # If OpenCV not installed, skip blur check
        return True