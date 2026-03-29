# odoo_integration/services.py
"""
Odoo XML-RPC integration for invoice sync.
Supports Customer Invoices and Vendor Bills.
"""
import xmlrpc.client
import base64
import logging
from decouple import config

logger = logging.getLogger(__name__)


class OdooConnectionError(Exception):
    """Raised when Odoo connection fails."""
    pass


class OdooClient:
    """Connect to Odoo and create invoices."""
    
    def __init__(self):
        self.url = config('ODOO_URL', default='')
        self.db = config('ODOO_DB', default='')
        self.username = config('ODOO_USERNAME', default='')
        self.password = config('ODOO_PASSWORD', default='')
        self.uid = None
        self._models = None
        
        if not all([self.url, self.db, self.username, self.password]):
            raise OdooConnectionError("Odoo credentials not configured in .env file!")
    
    def connect(self):
        """Authenticate with Odoo."""
        try:
            common = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/common',
                allow_none=True
            )
            
            # Test connection first
            version = common.version()
            logger.info(f"Connected to Odoo {version.get('server_version', 'unknown')}")
            
            # Authenticate
            self.uid = common.authenticate(self.db, self.username, self.password, {})
            
            if not self.uid:
                raise OdooConnectionError(
                    f"Authentication failed for user '{self.username}' on database '{self.db}'. "
                    "Check username/password and ensure user has API access."
                )
            
            logger.info(f"Authenticated as UID: {self.uid}")
            return self.uid
            
        except xmlrpc.client.Fault as e:
            raise OdooConnectionError(f"Odoo XML-RPC error: {e.faultString}")
        except ConnectionRefusedError:
            raise OdooConnectionError(f"Cannot connect to Odoo at {self.url}")
        except Exception as e:
            raise OdooConnectionError(f"Odoo connection failed: {str(e)}")
    
    def _get_models(self):
        """Get models proxy."""
        if not self._models:
            self._models = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/object',
                allow_none=True
            )
        return self._models
    
    def _execute(self, model, method, args, kwargs=None):
        """Execute Odoo model method with error handling."""
        if not self.uid:
            self.connect()
        
        models = self._get_models()
        try:
            if kwargs:
                return models.execute_kw(
                    self.db, self.uid, self.password,
                    model, method, args, kwargs
                )
            else:
                return models.execute_kw(
                    self.db, self.uid, self.password,
                    model, method, args
                )
        except xmlrpc.client.Fault as e:
            logger.error(f"Odoo error on {model}.{method}: {e.faultString}")
            raise OdooConnectionError(f"Odoo error: {e.faultString}")
    
    def test_connection(self):
        """Test if Odoo connection works."""
        try:
            self.connect()
            # Try to read user info
            user = self._execute('res.users', 'read', [[self.uid], ['name', 'email']])
            return {
                'success': True,
                'message': f"Connected as: {user[0]['name']}",
                'uid': self.uid,
                'user': user[0]
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def find_or_create_partner(self, name, vat=None, is_customer=True):
        """Find existing partner or create new one."""
        # Search by VAT first (most accurate)
        if vat:
            partner_ids = self._execute(
                'res.partner', 'search',
                [[('vat', '=', vat)]]
            )
            if partner_ids:
                logger.info(f"Found partner by VAT: {partner_ids[0]}")
                return partner_ids[0]
        
        # Search by name
        if name:
            partner_ids = self._execute(
                'res.partner', 'search',
                [[('name', 'ilike', name)]],
                {'limit': 1}
            )
            if partner_ids:
                logger.info(f"Found partner by name: {partner_ids[0]}")
                return partner_ids[0]
        
        # Create new partner
        partner_data = {
            'name': name or 'Unknown Customer',
            'customer_rank': 1 if is_customer else 0,
            'supplier_rank': 0 if is_customer else 1,
            'active': True,
        }
        if vat:
            partner_data['vat'] = vat
        
        partner_id = self._execute('res.partner', 'create', [partner_data])
        logger.info(f"Created new partner: {partner_id}")
        return partner_id
    
    def get_default_account(self, account_type='income'):
        """Get default account for invoice lines."""
        # Search for income account (for customer invoices)
        domain = [('account_type', '=', 'income' if account_type == 'income' else 'expense')]
        
        account_ids = self._execute(
            'account.account', 'search',
            [domain],
            {'limit': 1}
        )
        return account_ids[0] if account_ids else None
    
    def get_sales_tax(self, tax_percent=15):
        """Find sales tax (VAT) in Odoo by percentage."""
        # Search for tax with given percentage for sales
        domain = [
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', tax_percent),
            ('active', '=', True)
        ]
        tax_ids = self._execute('account.tax', 'search', [domain], {'limit': 1})
        
        if tax_ids:
            logger.info(f"Found {tax_percent}% sales tax: {tax_ids[0]}")
            return tax_ids[0]
        
        # Try without exact match - any sales tax
        domain = [('type_tax_use', '=', 'sale'), ('active', '=', True)]
        tax_ids = self._execute('account.tax', 'search', [domain], {'limit': 1})
        
        if tax_ids:
            logger.info(f"Found sales tax (fallback): {tax_ids[0]}")
            return tax_ids[0]
        
        logger.warning("No sales tax found in Odoo")
        return None
    
    def get_purchase_tax(self, tax_percent=15):
        """Find purchase tax (VAT) in Odoo by percentage."""
        domain = [
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', tax_percent),
            ('active', '=', True)
        ]
        tax_ids = self._execute('account.tax', 'search', [domain], {'limit': 1})
        
        if tax_ids:
            logger.info(f"Found {tax_percent}% purchase tax: {tax_ids[0]}")
            return tax_ids[0]
        
        # Fallback
        domain = [('type_tax_use', '=', 'purchase'), ('active', '=', True)]
        tax_ids = self._execute('account.tax', 'search', [domain], {'limit': 1})
        
        if tax_ids:
            return tax_ids[0]
        
        logger.warning("No purchase tax found in Odoo")
        return None
    
    def create_customer_invoice(self, invoice_data, partner_id=None, attach_image=True):
        """
        Create Customer Invoice (out_invoice) in Odoo.
        
        Args:
            invoice_data: dict with keys:
                - vendor_name / buyer_name
                - vendor_vat / buyer_vat  
                - invoice_number
                - invoice_date (YYYY-MM-DD string or date object)
                - line_items: list of {description, quantity, unit_price, total}
                - subtotal, vat_amount, total_amount
            partner_id: Optional existing partner ID
            attach_image: Whether to attach original invoice image
        
        Returns:
            dict with odoo_id, odoo_name, partner_id
        """
        # Find or create partner (customer)
        if not partner_id:
            partner_id = self.find_or_create_partner(
                name=invoice_data.get('buyer_name') or invoice_data.get('vendor_name', 'Customer'),
                vat=invoice_data.get('buyer_vat') or invoice_data.get('vendor_vat'),
                is_customer=True
            )
        
        # Get VAT tax (15% default for Saudi Arabia)
        tax_id = self.get_sales_tax(15)
        tax_rate = 0.15  # 15% VAT
        
        # Get subtotal from OCR (more accurate than recalculating)
        ocr_subtotal = float(invoice_data.get('subtotal', 0) or 0)
        line_items = invoice_data.get('line_items', [])
        
        # Calculate line items sum for proportional adjustment
        line_items_sum = sum(
            float(item.get('unit_price', 0)) * float(item.get('quantity', 1))
            for item in line_items
        )
        
        # Build invoice lines
        invoice_lines = []
        for item in line_items:
            unit_price = float(item.get('unit_price', 0))
            quantity = float(item.get('quantity', 1))
            
            # If we have OCR subtotal, use proportional pricing to match exactly
            if ocr_subtotal > 0 and line_items_sum > 0:
                # Scale price proportionally to match OCR subtotal
                line_total = unit_price * quantity
                adjusted_total = (line_total / line_items_sum) * ocr_subtotal
                unit_price = round(adjusted_total / quantity, 2)
            elif tax_id and unit_price > 0:
                # Fallback: assume VAT-inclusive and convert
                unit_price = round(unit_price / (1 + tax_rate), 2)
            
            line_data = {
                'name': item.get('description', 'Invoice Line'),
                'quantity': quantity,
                'price_unit': unit_price,
            }
            # Apply tax if found
            if tax_id:
                line_data['tax_ids'] = [(6, 0, [tax_id])]
            invoice_lines.append((0, 0, line_data))
        
        # If no line items, create single line from subtotal or total
        if not invoice_lines:
            if ocr_subtotal > 0:
                amount = ocr_subtotal
            else:
                total_amount = float(invoice_data.get('total_amount', 0) or 0)
                amount = round(total_amount / (1 + tax_rate), 2) if tax_id else total_amount
            
            line_data = {
                'name': f"Invoice {invoice_data.get('invoice_number', '')}",
                'quantity': 1,
                'price_unit': amount,
            }
            if tax_id:
                line_data['tax_ids'] = [(6, 0, [tax_id])]
            invoice_lines.append((0, 0, line_data))
        
        # Prepare invoice date
        invoice_date = invoice_data.get('invoice_date') or invoice_data.get('date')
        if invoice_date and hasattr(invoice_date, 'isoformat'):
            invoice_date = invoice_date.isoformat()
        
        # Create invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': partner_id,
            'ref': invoice_data.get('invoice_number', ''),
            'invoice_line_ids': invoice_lines,
        }
        
        if invoice_date:
            invoice_vals['invoice_date'] = invoice_date
        
        odoo_id = self._execute('account.move', 'create', [invoice_vals])
        
        # Get invoice name (number)
        invoice_info = self._execute(
            'account.move', 'read',
            [[odoo_id], ['name', 'amount_total']]
        )
        odoo_name = invoice_info[0]['name'] if invoice_info else f"INV/{odoo_id}"
        
        logger.info(f"Created Odoo customer invoice: {odoo_name} (ID: {odoo_id})")
        
        return {
            'odoo_id': odoo_id,
            'odoo_name': odoo_name,
            'partner_id': partner_id,
            'amount_total': invoice_info[0].get('amount_total') if invoice_info else None
        }
    
    def create_vendor_bill(self, invoice_data, partner_id=None, attach_image=True):
        """
        Create Vendor Bill (in_invoice) in Odoo.
        Same args as create_customer_invoice.
        """
        # Find or create partner (vendor/supplier)
        if not partner_id:
            partner_id = self.find_or_create_partner(
                name=invoice_data.get('vendor_name', 'Vendor'),
                vat=invoice_data.get('vendor_vat'),
                is_customer=False
            )
        
        # Get VAT tax for purchases (15% default for Saudi Arabia)
        tax_id = self.get_purchase_tax(15)
        tax_rate = 0.15  # 15% VAT
        
        # Get subtotal from OCR (more accurate than recalculating)
        ocr_subtotal = float(invoice_data.get('subtotal', 0) or 0)
        line_items = invoice_data.get('line_items', [])
        
        # Calculate line items sum for proportional adjustment
        line_items_sum = sum(
            float(item.get('unit_price', 0)) * float(item.get('quantity', 1))
            for item in line_items
        )
        
        # Build invoice lines
        invoice_lines = []
        for item in line_items:
            unit_price = float(item.get('unit_price', 0))
            quantity = float(item.get('quantity', 1))
            
            # If we have OCR subtotal, use proportional pricing to match exactly
            if ocr_subtotal > 0 and line_items_sum > 0:
                line_total = unit_price * quantity
                adjusted_total = (line_total / line_items_sum) * ocr_subtotal
                unit_price = round(adjusted_total / quantity, 2)
            elif tax_id and unit_price > 0:
                unit_price = round(unit_price / (1 + tax_rate), 2)
            
            line_data = {
                'name': item.get('description', 'Bill Line'),
                'quantity': quantity,
                'price_unit': unit_price,
            }
            if tax_id:
                line_data['tax_ids'] = [(6, 0, [tax_id])]
            invoice_lines.append((0, 0, line_data))
        
        if not invoice_lines:
            if ocr_subtotal > 0:
                amount = ocr_subtotal
            else:
                total_amount = float(invoice_data.get('total_amount', 0) or 0)
                amount = round(total_amount / (1 + tax_rate), 2) if tax_id else total_amount
            
            line_data = {
                'name': f"Bill {invoice_data.get('invoice_number', '')}",
                'quantity': 1,
                'price_unit': amount,
            }
            if tax_id:
                line_data['tax_ids'] = [(6, 0, [tax_id])]
            invoice_lines.append((0, 0, line_data))
        
        invoice_date = invoice_data.get('invoice_date') or invoice_data.get('date')
        if invoice_date and hasattr(invoice_date, 'isoformat'):
            invoice_date = invoice_date.isoformat()
        
        invoice_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner_id,
            'ref': invoice_data.get('invoice_number', ''),
            'invoice_line_ids': invoice_lines,
        }
        
        if invoice_date:
            invoice_vals['invoice_date'] = invoice_date
        
        odoo_id = self._execute('account.move', 'create', [invoice_vals])
        
        invoice_info = self._execute(
            'account.move', 'read',
            [[odoo_id], ['name', 'amount_total']]
        )
        odoo_name = invoice_info[0]['name'] if invoice_info else f"BILL/{odoo_id}"
        
        logger.info(f"Created Odoo vendor bill: {odoo_name} (ID: {odoo_id})")
        
        return {
            'odoo_id': odoo_id,
            'odoo_name': odoo_name,
            'partner_id': partner_id,
            'amount_total': invoice_info[0].get('amount_total') if invoice_info else None
        }
    
    def attach_file(self, record_id, file_data, filename='invoice.pdf', model='account.move'):
        """Attach file to an Odoo record."""
        try:
            if isinstance(file_data, bytes):
                file_data = base64.b64encode(file_data).decode('utf-8')
            
            attachment_id = self._execute('ir.attachment', 'create', [{
                'name': filename,
                'type': 'binary',
                'datas': file_data,
                'res_model': model,
                'res_id': record_id,
            }])
            logger.info(f"Attached file to {model}/{record_id}")
            return attachment_id
        except Exception as e:
            logger.error(f"Failed to attach file: {e}")
            return None


def sync_invoice_to_odoo(invoice_id, invoice_type='out_invoice', user=None):
    """
    Main function to sync a Django invoice to Odoo.
    
    Args:
        invoice_id: Django Invoice ID
        invoice_type: 'out_invoice' (customer) or 'in_invoice' (vendor)
        user: User performing the sync
    
    Returns:
        dict with success, odoo_id, odoo_name, error
    """
    from invoices.models import Invoice
    from .models import OdooSyncLog
    
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        # Get OCR data
        ocr_data = invoice.ocr_data or {}
        
        # Also try to get from OCRResult if available
        if hasattr(invoice, 'ocr_result'):
            ocr_result = invoice.ocr_result
            if not ocr_data:
                ocr_data = {
                    'vendor_name': ocr_result.vendor_name,
                    'vendor_vat': ocr_result.vendor_vat,
                    'buyer_name': ocr_result.buyer_name,
                    'buyer_vat': ocr_result.buyer_vat,
                    'invoice_number': ocr_result.invoice_number,
                    'invoice_date': ocr_result.invoice_date,
                    'subtotal': ocr_result.subtotal,
                    'vat_amount': ocr_result.vat_amount,
                    'total_amount': ocr_result.total_amount,
                    'line_items': ocr_result.line_items or [],
                }
        
        # Create sync log
        sync_log = OdooSyncLog.objects.create(
            invoice=invoice,
            invoice_type=invoice_type,
            status=OdooSyncLog.Status.PENDING,
            synced_by=user,
            synced_data=ocr_data,
        )
        
        # Connect to Odoo
        odoo = OdooClient()
        odoo.connect()
        
        # Create invoice in Odoo
        if invoice_type == 'out_invoice':
            result = odoo.create_customer_invoice(ocr_data)
        else:
            result = odoo.create_vendor_bill(ocr_data)
        
        # Attach original invoice image
        if invoice.image:
            try:
                with open(invoice.image.path, 'rb') as f:
                    file_data = f.read()
                odoo.attach_file(
                    result['odoo_id'],
                    file_data,
                    filename=invoice.original_filename or 'invoice.pdf'
                )
            except Exception as e:
                logger.warning(f"Could not attach image: {e}")
        
        # Update sync log
        sync_log.status = OdooSyncLog.Status.SYNCED
        sync_log.odoo_invoice_id = result['odoo_id']
        sync_log.odoo_invoice_name = result['odoo_name']
        sync_log.odoo_partner_id = result['partner_id']
        sync_log.save()
        
        # Update invoice status to Posted and store Odoo ID
        invoice.status = Invoice.Status.POSTED_TO_ODOO
        invoice.odoo_invoice_id = result['odoo_id']
        invoice.save(update_fields=['status', 'odoo_invoice_id'])
        
        # Audit log for sync
        from invoices.models import AuditLog
        AuditLog.objects.create(
            invoice=invoice,
            action=AuditLog.Action.SENT_TO_ODOO,
            performed_by=user,
            details={
                'odoo_id': result['odoo_id'],
                'odoo_name': result['odoo_name'],
                'invoice_type': invoice_type,
            },
        )
        
        return {
            'success': True,
            'odoo_id': result['odoo_id'],
            'odoo_name': result['odoo_name'],
            'odoo_url': sync_log.odoo_url,
        }
        
    except Invoice.DoesNotExist:
        return {'success': False, 'error': f'Invoice {invoice_id} not found'}
    except OdooConnectionError as e:
        if 'sync_log' in locals():
            sync_log.status = OdooSyncLog.Status.FAILED
            sync_log.error_message = str(e)
            sync_log.save()
        return {'success': False, 'error': str(e)}
    except Exception as e:
        logger.exception(f"Odoo sync failed for invoice {invoice_id}")
        if 'sync_log' in locals():
            sync_log.status = OdooSyncLog.Status.FAILED
            sync_log.error_message = str(e)
            sync_log.save()
        return {'success': False, 'error': str(e)}
