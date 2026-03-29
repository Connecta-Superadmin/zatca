# ocr_engine/services.py
"""
Invoice OCR using OpenAI GPT-4o Vision.
Extracts: vendor, VAT, invoice number, date, line items, totals.
Supports Arabic + English invoices.
"""
import os
import io
import json
import base64
import logging
from datetime import datetime
from decimal import Decimal
from decouple import config

logger = logging.getLogger(__name__)

# Image optimization settings - BALANCED (fast + accurate)
MAX_IMAGE_DIMENSION = 1280  # Good balance
JPEG_QUALITY = 80  # Good quality
MAX_FILE_SIZE_MB = 1  # 1MB max


class OpenAIOCRService:
    """Extract invoice data using OpenAI GPT-4o Vision."""
    
    def __init__(self):
        self.api_key = config('OPENAI_API_KEY', default='')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in .env file!")
    
    def _optimize_image(self, file_bytes, content_type):
        """
        Resize and compress image to optimize for OpenAI API.
        Returns optimized bytes and content type.
        """
        from PIL import Image
        
        try:
            # Handle PDF - convert first page to image
            if content_type == 'application/pdf':
                file_bytes = self._pdf_to_image(file_bytes)
                content_type = 'image/jpeg'
            
            # Open image
            img = Image.open(io.BytesIO(file_bytes))
            
            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'P', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get original size
            original_width, original_height = img.size
            original_size_kb = len(file_bytes) / 1024
            
            logger.info(f"Original image: {original_width}x{original_height}, {original_size_kb:.1f}KB")
            
            # Resize if larger than max dimension
            if original_width > MAX_IMAGE_DIMENSION or original_height > MAX_IMAGE_DIMENSION:
                # Calculate new size maintaining aspect ratio
                ratio = min(MAX_IMAGE_DIMENSION / original_width, MAX_IMAGE_DIMENSION / original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Resized to: {new_width}x{new_height}")
            
            # Compress to JPEG
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=JPEG_QUALITY, optimize=True)
            optimized_bytes = output.getvalue()
            
            # If still too large, reduce quality further
            quality = JPEG_QUALITY
            while len(optimized_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024 and quality > 40:
                quality -= 10
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=quality, optimize=True)
                optimized_bytes = output.getvalue()
                logger.info(f"Reduced quality to {quality}, size: {len(optimized_bytes)/1024:.1f}KB")
            
            final_size_kb = len(optimized_bytes) / 1024
            logger.info(f"Optimized image: {final_size_kb:.1f}KB (saved {original_size_kb - final_size_kb:.1f}KB)")
            
            return optimized_bytes, 'image/jpeg'
            
        except Exception as e:
            logger.warning(f"Image optimization failed: {e}, using original")
            return file_bytes, content_type
    
    def _pdf_to_image(self, pdf_bytes):
        """Convert first page of PDF to image."""
        try:
            # Try using pdf2image (requires poppler)
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=150)
            if images:
                output = io.BytesIO()
                images[0].save(output, format='JPEG', quality=JPEG_QUALITY)
                logger.info("PDF converted using pdf2image")
                return output.getvalue()
        except ImportError:
            logger.warning("pdf2image not installed, trying PyMuPDF")
        except Exception as e:
            logger.warning(f"pdf2image failed: {e}")
        
        try:
            # Fallback to PyMuPDF
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page = doc[0]
            # Render at 150 DPI
            mat = fitz.Matrix(150/72, 150/72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
            doc.close()
            logger.info("PDF converted using PyMuPDF")
            return img_bytes
        except ImportError:
            logger.warning("PyMuPDF not installed")
        except Exception as e:
            logger.warning(f"PyMuPDF failed: {e}")
        
        # If all else fails, return original (OpenAI might handle it)
        logger.warning("PDF conversion failed, sending original PDF")
        return pdf_bytes
    
    def extract_from_file(self, file_path):
        """Extract invoice data from a file path."""
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        
        # Detect content type
        ext = os.path.splitext(file_path)[1].lower()
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.pdf': 'application/pdf',
        }
        content_type = content_type_map.get(ext, 'image/jpeg')
        
        return self.extract_from_bytes(file_bytes, content_type)
    
    def extract_from_bytes(self, file_bytes, content_type="image/jpeg"):
        """Extract invoice data from file bytes using GPT-4o."""
        from openai import OpenAI
        
        # Optimize image before sending to API
        file_bytes, content_type = self._optimize_image(file_bytes, content_type)
        
        client = OpenAI(api_key=self.api_key)
        
        # Convert to base64
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        # For PDFs, we need to handle differently
        if content_type == 'application/pdf':
            media_type = "application/pdf"
        else:
            media_type = content_type
        
        # Balanced prompt - accurate but concise
        extraction_prompt = """Extract ALL invoice data accurately. Arabic/English both supported.

Return ONLY valid JSON (no markdown):
{
    "vendor_name": "seller company name",
    "vendor_vat": "VAT number",
    "invoice_number": "invoice #",
    "invoice_date": "YYYY-MM-DD",
    "subtotal": 0.00,
    "vat_amount": 0.00,
    "total_amount": 0.00,
    "currency": "SAR",
    "line_items": [
        {"description": "item name", "quantity": 1, "unit_price": 0.00, "total": 0.00}
    ],
    "zatca_info": {"has_qr_code": true, "invoice_type": ""},
    "confidence": {"overall": 0.85}
}

Extract EVERY line item. Be accurate with numbers."""

        # GPT-4o-mini with auto detail (fast + accurate)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": extraction_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}",
                                "detail": "auto"  # auto = good balance
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.1,
        )
        
        # Parse response
        response_text = response.choices[0].message.content.strip()
        
        # Clean up response (remove markdown code blocks if present)
        if response_text.startswith('```'):
            response_text = response_text.split('\n', 1)[1]  # Remove first line
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
        
        try:
            extracted = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GPT response: {e}")
            logger.error(f"Response was: {response_text[:500]}")
            extracted = {
                'error': 'Failed to parse response',
                'raw_response': response_text[:1000],
            }
        
        return self._normalize_data(extracted)
    
    def _normalize_data(self, data):
        """Normalize extracted data to consistent format."""
        if 'error' in data:
            return data
        
        # Ensure all fields exist with defaults
        normalized = {
            'vendor_name': str(data.get('vendor_name', '')),
            'vendor_vat': str(data.get('vendor_vat', '')),
            'vendor_address': str(data.get('vendor_address', '')),
            'buyer_name': str(data.get('buyer_name', '')),
            'buyer_vat': str(data.get('buyer_vat', '')),
            'buyer_address': str(data.get('buyer_address', '')),
            'invoice_number': str(data.get('invoice_number', '')),
            'invoice_date': None,
            'subtotal': None,
            'vat_amount': None,
            'total_amount': None,
            'line_items': data.get('line_items', []),
            'field_confidences': data.get('confidence', {}),
            'overall_confidence': 0.0,
            'raw_fields': data,
            'zatca_info': data.get('zatca_info', {}),
            'currency': data.get('currency', 'SAR'),
            'payment_method': data.get('payment_method', ''),
        }
        
        # Parse date
        date_str = data.get('invoice_date', '')
        if date_str and date_str != 'null':
            try:
                normalized['invoice_date'] = datetime.strptime(str(date_str), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                # Try other date formats
                for fmt in ['%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y']:
                    try:
                        normalized['invoice_date'] = datetime.strptime(str(date_str), fmt).date()
                        break
                    except (ValueError, TypeError):
                        continue
        
        # Parse amounts
        for field in ['subtotal', 'vat_amount', 'total_amount']:
            val = data.get(field)
            if val is not None and val != 'null' and val != '':
                try:
                    normalized[field] = Decimal(str(val))
                except (ValueError, TypeError, Exception):
                    normalized[field] = None
        
        # Calculate overall confidence
        confidences = data.get('confidence', {})
        if isinstance(confidences, dict) and 'overall' in confidences:
            normalized['overall_confidence'] = float(confidences['overall'])
        elif isinstance(confidences, dict) and confidences:
            values = [v for v in confidences.values() if isinstance(v, (int, float))]
            normalized['overall_confidence'] = sum(values) / len(values) if values else 0
        
        return normalized


def process_invoice_ocr(invoice_id):
    """
    Main function: Process an invoice through OCR.
    Call from views or background tasks.
    """
    from invoices.models import Invoice, AuditLog
    from .models import OCRResult
    
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        # Update status
        invoice.status = Invoice.Status.OCR_PROCESSING
        invoice.save()
        
        # Run OCR
        ocr_service = OpenAIOCRService()
        file_path = invoice.image.path
        extracted = ocr_service.extract_from_file(file_path)
        
        # Check for errors
        if 'error' in extracted:
            invoice.status = Invoice.Status.FAILED
            invoice.save()
            return {'success': False, 'error': extracted['error']}
        
        # Save OCR result
        ocr_result, created = OCRResult.objects.update_or_create(
            invoice=invoice,
            defaults={
                'vendor_name': extracted.get('vendor_name', ''),
                'vendor_vat': extracted.get('vendor_vat', ''),
                'buyer_name': extracted.get('buyer_name', ''),
                'buyer_vat': extracted.get('buyer_vat', ''),
                'invoice_number': extracted.get('invoice_number', ''),
                'invoice_date': extracted.get('invoice_date'),
                'subtotal': extracted.get('subtotal'),
                'vat_amount': extracted.get('vat_amount'),
                'total_amount': extracted.get('total_amount'),
                'line_items': extracted.get('line_items', []),
                'overall_confidence': extracted.get('overall_confidence', 0),
                'field_confidences': extracted.get('field_confidences', {}),
                'raw_ocr_response': extracted.get('raw_fields', {}),
                'qr_code_data': extracted.get('zatca_info', {}),
            }
        )
        
        # Update invoice
        invoice.status = Invoice.Status.OCR_COMPLETE
        invoice.ocr_data = extracted.get('raw_fields', {})
        invoice.confidence_score = extracted.get('overall_confidence', 0)
        invoice.save()
        
        # Audit log
        AuditLog.objects.create(
            invoice=invoice,
            action=AuditLog.Action.OCR_PROCESSED,
            details={
                'confidence': extracted.get('overall_confidence', 0),
                'vendor': extracted.get('vendor_name', ''),
                'total': str(extracted.get('total_amount', '')),
                'items_count': len(extracted.get('line_items', [])),
                'engine': 'OpenAI GPT-4o',
            }
        )
        
        return {
            'success': True,
            'invoice_id': invoice_id,
            'data': extracted,
        }
    
    except Invoice.DoesNotExist:
        return {'success': False, 'error': f'Invoice {invoice_id} not found'}
    except Exception as e:
        logger.error(f"OCR failed for invoice {invoice_id}: {str(e)}")
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            invoice.status = Invoice.Status.FAILED
            invoice.save()
        except Exception:
            pass
        return {'success': False, 'error': str(e)}