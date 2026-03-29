# zatca/qr_decoder.py
"""
Phase 2: ZATCA TLV QR code decoding.
"""
import base64


class ZATCAQRDecoder:
    """Decode ZATCA Phase-1 TLV QR codes."""
    
    # TLV Tag definitions
    TAGS = {
        1: 'seller_name',
        2: 'vat_number',
        3: 'timestamp',
        4: 'total_with_vat',
        5: 'vat_amount',
    }
    
    def decode_tlv(self, qr_data):
        """
        Decode base64-encoded TLV data from ZATCA QR code.
        Returns dict with seller_name, vat_number, timestamp, total, vat_amount.
        """
        try:
            decoded = base64.b64decode(qr_data)
            result = {}
            index = 0
            
            while index < len(decoded):
                tag = decoded[index]
                length = decoded[index + 1]
                value = decoded[index + 2: index + 2 + length].decode('utf-8')
                
                if tag in self.TAGS:
                    result[self.TAGS[tag]] = value
                
                index += 2 + length
            
            return result
        except Exception as e:
            return {'error': str(e)}
    
    def validate_invoice(self, qr_data, invoice_data):
        """
        Validate invoice against ZATCA QR data.
        Compare extracted OCR data with QR code data.
        """
        qr_info = self.decode_tlv(qr_data)
        
        if 'error' in qr_info:
            return {'valid': False, 'errors': [qr_info['error']]}
        
        errors = []
        
        # Check VAT number matches
        if qr_info.get('vat_number') != invoice_data.get('vat_number'):
            errors.append('VAT number mismatch')
        
        # Check total matches
        if qr_info.get('total_with_vat') != str(invoice_data.get('total', '')):
            errors.append('Total amount mismatch')
        
        return {
            'valid': len(errors) == 0,
            'qr_data': qr_info,
            'errors': errors,
        }