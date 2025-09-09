#!/usr/bin/env python3
"""
Contract PDF Generator
Generate professional PDF contracts from database records with complete vehicle information

Usage:
python generate_contract_pdf.py CAC-VSC-TXN-20250908041348-20250908040634
python generate_contract_pdf.py --transaction TXN-20250908041348-20250908040634
python generate_contract_pdf.py --all
python generate_contract_pdf.py --list
"""

import os
import sys
import json
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Database connection
DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"


def get_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Database connection failed: {e}")
        sys.exit(1)


def get_contract_by_number(contract_number):
    """Get contract details by contract number"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
                   SELECT gc.id,
                          gc.contract_number,
                          gc.customer_data,
                          gc.contract_data,
                          gc.status,
                          gc.generated_date,
                          gc.effective_date,
                          gc.expiration_date,
                          gc.transaction_id,
                          ct.name      as template_name,
                          t.amount,
                          t.currency,
                          t.created_at as transaction_date
                   FROM generated_contracts gc
                            LEFT JOIN contract_templates ct ON gc.template_id = ct.id
                            LEFT JOIN transactions t ON gc.transaction_id = t.transaction_number
                   WHERE gc.contract_number = %s
                   ''', (contract_number,))

    contract = cursor.fetchone()
    cursor.close()
    conn.close()

    return contract


def get_contract_by_transaction(transaction_number):
    """Get contract details by transaction number"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
                   SELECT gc.id,
                          gc.contract_number,
                          gc.customer_data,
                          gc.contract_data,
                          gc.status,
                          gc.generated_date,
                          gc.effective_date,
                          gc.expiration_date,
                          gc.transaction_id,
                          ct.name      as template_name,
                          t.amount,
                          t.currency,
                          t.created_at as transaction_date
                   FROM generated_contracts gc
                            LEFT JOIN contract_templates ct ON gc.template_id = ct.id
                            LEFT JOIN transactions t ON gc.transaction_id = t.transaction_number
                   WHERE gc.transaction_id = %s
                   ''', (transaction_number,))

    contract = cursor.fetchone()
    cursor.close()
    conn.close()

    return contract


def get_all_contracts():
    """Get all contracts"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
                   SELECT gc.contract_number,
                          gc.status,
                          gc.generated_date,
                          gc.customer_data,
                          gc.transaction_id,
                          t.amount
                   FROM generated_contracts gc
                            LEFT JOIN transactions t ON gc.transaction_id = t.transaction_number
                   ORDER BY gc.generated_date DESC
                   ''')

    contracts = cursor.fetchall()
    cursor.close()
    conn.close()

    return contracts


def extract_vehicle_information(contract):
    """Extract comprehensive vehicle information from contract data"""
    contract_data = contract['contract_data'] if contract['contract_data'] else {}
    metadata = contract_data.get('product_info', {}).get('metadata', {})

    # Initialize vehicle info
    vehicle_info = {
        'year': 'N/A',
        'make': 'N/A',
        'model': 'N/A',
        'vin': 'N/A',
        'mileage': 'N/A',
        'trim': 'N/A',
        'body_style': 'N/A',
        'engine': 'N/A',
        'fuel_type': 'N/A',
        'drive_type': 'N/A',
        'series': 'N/A'
    }

    # Extract from multiple possible locations
    sources_to_check = [
        metadata.get('quote_data', {}),  # Main quote data
        metadata.get('vehicle_info', {}),  # Direct vehicle info
        metadata  # Root level
    ]

    for source in sources_to_check:
        if not source:
            continue

        # Basic vehicle info
        if 'vehicle_info' in source:
            vehicle_data = source['vehicle_info']
            if vehicle_data:
                vehicle_info['year'] = str(vehicle_data.get('year', vehicle_info['year']))
                vehicle_info['make'] = str(vehicle_data.get('make', vehicle_info['make']))
                vehicle_info['model'] = str(vehicle_data.get('model', vehicle_info['model']))
                vehicle_info['mileage'] = str(vehicle_data.get('mileage', vehicle_info['mileage']))

        # VIN and detailed info
        if 'vin_info' in source:
            vin_data = source['vin_info']
            if vin_data:
                vehicle_info['vin'] = str(vin_data.get('vin', vehicle_info['vin']))

                # Check for decoded VIN data
                if 'vin_decoded' in vin_data:
                    decoded = vin_data['vin_decoded']
                    vehicle_info['year'] = str(decoded.get('year', vehicle_info['year']))
                    vehicle_info['make'] = str(decoded.get('make', vehicle_info['make']))
                    vehicle_info['model'] = str(decoded.get('model', vehicle_info['model']))
                    vehicle_info['trim'] = str(decoded.get('trim', vehicle_info['trim']))
                    vehicle_info['series'] = str(decoded.get('series', vehicle_info['series']))
                    vehicle_info['body_style'] = str(decoded.get('body_style', vehicle_info['body_style']))
                    vehicle_info['fuel_type'] = str(decoded.get('fuel_type', vehicle_info['fuel_type']))
                    vehicle_info['drive_type'] = str(decoded.get('drive_type', vehicle_info['drive_type']))

                    # Engine information
                    engine_model = decoded.get('engine_model', '')
                    engine_cylinders = decoded.get('engine_cylinders', '')
                    engine_displacement = decoded.get('engine_displacement', '')

                    engine_parts = []
                    if engine_displacement:
                        engine_parts.append(f"{engine_displacement}L")
                    if engine_cylinders:
                        engine_parts.append(f"V{engine_cylinders}")
                    if engine_model:
                        engine_parts.append(engine_model)

                    if engine_parts:
                        vehicle_info['engine'] = ' '.join(engine_parts)

        # Direct fields in source
        for field in ['year', 'make', 'model', 'vin', 'mileage']:
            if field in source and vehicle_info[field] == 'N/A':
                vehicle_info[field] = str(source[field])

    return vehicle_info


def extract_coverage_information(contract):
    """Extract coverage details from contract data"""
    contract_data = contract['contract_data'] if contract['contract_data'] else {}
    metadata = contract_data.get('product_info', {}).get('metadata', {})

    coverage_info = {
        'level': 'N/A',
        'term_months': 'N/A',
        'term_years': 'N/A',
        'deductible': 'N/A',
        'customer_type': 'N/A'
    }

    # Check quote data for coverage details
    if 'quote_data' in metadata and 'coverage_details' in metadata['quote_data']:
        coverage_data = metadata['quote_data']['coverage_details']
        coverage_info['level'] = str(coverage_data.get('level', coverage_info['level']))
        coverage_info['term_months'] = str(coverage_data.get('term_months', coverage_info['term_months']))
        coverage_info['term_years'] = str(coverage_data.get('term_years', coverage_info['term_years']))
        coverage_info['deductible'] = f"${coverage_data.get('deductible', 0)}" if coverage_data.get(
            'deductible') is not None else coverage_info['deductible']
        coverage_info['customer_type'] = str(coverage_data.get('customer_type', coverage_info['customer_type']))

    return coverage_info


def create_contract_pdf(contract, output_dir="./contracts"):
    """Generate PDF from contract data with complete vehicle information"""

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Extract data
    customer_data = contract['customer_data'] if contract['customer_data'] else {}
    contract_data = contract['contract_data'] if contract['contract_data'] else {}

    # Customer info
    customer_name = f"{customer_data.get('first_name', '')} {customer_data.get('last_name', '')}".strip()
    customer_email = customer_data.get('email', 'N/A')
    customer_phone = customer_data.get('phone', 'N/A')

    # Transaction info
    transaction_info = contract_data.get('transaction_info', {})
    product_info = contract_data.get('product_info', {})

    # Create PDF filename
    safe_contract_number = contract['contract_number'].replace('/', '-')
    pdf_filename = f"{safe_contract_number}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)

    # Create PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=18)

    # Create story (content list)
    story = []

    # Get styles
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1f4e79')
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.HexColor('#1f4e79')
    )

    normal_style = styles['Normal']
    normal_style.fontSize = 11
    normal_style.spaceAfter = 6

    # Company Header
    story.append(Paragraph("CONNECTED AUTO CARE", title_style))
    story.append(Paragraph("VEHICLE PROTECTION PLAN CONTRACT", heading_style))
    story.append(Spacer(1, 20))

    # Contract Information Table
    contract_info_data = [
        ['Contract Number:', contract['contract_number']],
        ['Transaction ID:', contract['transaction_id']],
        ['Contract Status:', contract['status'].title()],
        ['Generated Date:', contract['generated_date'].strftime('%B %d, %Y') if contract['generated_date'] else 'N/A'],
        ['Template Used:', contract['template_name'] or 'Standard Contract']
    ]

    contract_info_table = Table(contract_info_data, colWidths=[2 * inch, 4 * inch])
    contract_info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f4e79')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    story.append(contract_info_table)
    story.append(Spacer(1, 20))

    # Customer Information
    story.append(Paragraph("CUSTOMER INFORMATION", heading_style))

    customer_info_data = [
        ['Name:', customer_name or 'N/A'],
        ['Email:', customer_email],
        ['Phone:', customer_phone],
        ['Address:', str(customer_data.get('address', 'N/A'))]
    ]

    customer_info_table = Table(customer_info_data, colWidths=[1.5 * inch, 4.5 * inch])
    customer_info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f4e79')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    story.append(customer_info_table)
    story.append(Spacer(1, 20))

    # Transaction Details
    story.append(Paragraph("TRANSACTION DETAILS", heading_style))

    amount = float(contract['amount']) if contract['amount'] else 0.0
    currency = contract['currency'] or 'USD'

    transaction_details_data = [
        ['Transaction Amount:', f"${amount:,.2f} {currency}"],
        ['Transaction Date:',
         contract['transaction_date'].strftime('%B %d, %Y') if contract['transaction_date'] else 'N/A'],
        ['Payment Method:', transaction_info.get('payment_method', {}).get('method', 'N/A') if isinstance(
            transaction_info.get('payment_method'), dict) else str(transaction_info.get('payment_method', 'N/A'))],
        ['Product Type:', product_info.get('product_type', 'N/A').upper()]
    ]

    transaction_table = Table(transaction_details_data, colWidths=[2 * inch, 4 * inch])
    transaction_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f4e79')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    story.append(transaction_table)
    story.append(Spacer(1, 20))

    # Vehicle Information (Enhanced for VSC)
    if product_info.get('product_type') == 'vsc':
        vehicle_info = extract_vehicle_information(contract)

        story.append(Paragraph("VEHICLE INFORMATION", heading_style))

        # Build vehicle description
        vehicle_description = []
        if vehicle_info['year'] != 'N/A':
            vehicle_description.append(vehicle_info['year'])
        if vehicle_info['make'] != 'N/A':
            vehicle_description.append(vehicle_info['make'])
        if vehicle_info['model'] != 'N/A':
            vehicle_description.append(vehicle_info['model'])
        if vehicle_info['series'] != 'N/A':
            vehicle_description.append(vehicle_info['series'])
        if vehicle_info['trim'] != 'N/A':
            vehicle_description.append(vehicle_info['trim'])

        full_vehicle_name = ' '.join(
            vehicle_description) if vehicle_description else 'Vehicle Information Not Available'

        vehicle_details_data = [
            ['Vehicle:', full_vehicle_name],
            ['VIN:', vehicle_info['vin']],
            ['Current Mileage:', f"{vehicle_info['mileage']} miles" if vehicle_info['mileage'] != 'N/A' else 'N/A'],
            ['Body Style:', vehicle_info['body_style']],
            ['Engine:', vehicle_info['engine']],
            ['Fuel Type:', vehicle_info['fuel_type']],
            ['Drive Type:', vehicle_info['drive_type']]
        ]

        vehicle_table = Table(vehicle_details_data, colWidths=[1.8 * inch, 4.2 * inch])
        vehicle_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f4e79')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(vehicle_table)
        story.append(Spacer(1, 20))

        # Coverage Details
        coverage_info = extract_coverage_information(contract)

        story.append(Paragraph("COVERAGE DETAILS", heading_style))

        coverage_details_data = [
            ['Coverage Level:', coverage_info['level']],
            ['Contract Term:',
             f"{coverage_info['term_months']} months ({coverage_info['term_years']} years)" if coverage_info[
                                                                                                   'term_months'] != 'N/A' else 'N/A'],
            ['Deductible:', coverage_info['deductible']],
            ['Customer Type:', coverage_info['customer_type']]
        ]

        coverage_table = Table(coverage_details_data, colWidths=[1.8 * inch, 4.2 * inch])
        coverage_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f4e79')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(coverage_table)
        story.append(Spacer(1, 20))

    # Footer
    story.append(Spacer(1, 30))
    footer_text = f"Contract generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8,
                                  alignment=TA_CENTER, textColor=colors.grey)
    story.append(Paragraph(footer_text, footer_style))

    # Build PDF
    try:
        doc.build(story)
        return pdf_path
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return None


def generate_pdf_by_contract_number(contract_number):
    """Generate PDF for specific contract number"""
    print(f"Looking up contract: {contract_number}")

    contract = get_contract_by_number(contract_number)
    if not contract:
        print(f"Contract not found: {contract_number}")
        return False

    customer_data = contract['customer_data'] if contract['customer_data'] else {}
    customer_name = f"{customer_data.get('first_name', 'Unknown')} {customer_data.get('last_name', '')}"
    print(f"Found contract for customer: {customer_name}")

    pdf_path = create_contract_pdf(contract)
    if pdf_path:
        print(f"PDF generated successfully: {pdf_path}")
        return True
    else:
        print("Failed to generate PDF")
        return False


def generate_pdf_by_transaction(transaction_number):
    """Generate PDF for contract associated with transaction"""
    print(f"Looking up contract for transaction: {transaction_number}")

    contract = get_contract_by_transaction(transaction_number)
    if not contract:
        print(f"No contract found for transaction: {transaction_number}")
        return False

    print(f"Found contract: {contract['contract_number']}")

    pdf_path = create_contract_pdf(contract)
    if pdf_path:
        print(f"PDF generated successfully: {pdf_path}")
        return True
    else:
        print("Failed to generate PDF")
        return False


def generate_all_pdfs():
    """Generate PDFs for all contracts"""
    contracts = get_all_contracts()

    if not contracts:
        print("No contracts found")
        return

    print(f"Found {len(contracts)} contracts to process")

    success_count = 0
    for contract in contracts:
        print(f"\nProcessing contract: {contract['contract_number']}")

        # Get full contract details
        full_contract = get_contract_by_number(contract['contract_number'])
        if full_contract:
            pdf_path = create_contract_pdf(full_contract)
            if pdf_path:
                success_count += 1
                print(f"  PDF created: {pdf_path}")
            else:
                print(f"  Failed to create PDF")
        else:
            print(f"  Failed to get contract details")

    print(f"\nGenerated {success_count}/{len(contracts)} PDFs successfully")


def list_contracts():
    """List all available contracts"""
    contracts = get_all_contracts()

    if not contracts:
        print("No contracts found")
        return

    print(f"Found {len(contracts)} contracts:")
    print("-" * 80)

    for contract in contracts:
        customer_data = contract['customer_data'] if contract['customer_data'] else {}
        customer_name = f"{customer_data.get('first_name', '')} {customer_data.get('last_name', '')}".strip()
        amount = float(contract['amount']) if contract['amount'] else 0.0

        print(f"Contract: {contract['contract_number']}")
        print(f"  Customer: {customer_name}")
        print(f"  Transaction: {contract['transaction_id']}")
        print(f"  Amount: ${amount:,.2f}")
        print(f"  Status: {contract['status']}")
        print(f"  Generated: {contract['generated_date']}")
        print()


def main():
    parser = argparse.ArgumentParser(description='Generate PDF contracts')
    parser.add_argument('contract_number', nargs='?', help='Contract number (e.g., CAC-VSC-TXN-...)')
    parser.add_argument('--transaction', help='Generate PDF for contract associated with transaction number')
    parser.add_argument('--all', action='store_true', help='Generate PDFs for all contracts')
    parser.add_argument('--list', action='store_true', help='List all available contracts')

    args = parser.parse_args()

    print("ConnectedAutoCare Contract PDF Generator")
    print("=" * 50)

    # Check if reportlab is installed
    try:
        import reportlab
        print(f"Using ReportLab version: {reportlab.Version}")
    except ImportError:
        print("ERROR: ReportLab not installed. Install with: pip install reportlab")
        sys.exit(1)

    if args.list:
        list_contracts()

    elif args.all:
        generate_all_pdfs()

    elif args.transaction:
        if generate_pdf_by_transaction(args.transaction):
            print("\nPDF generation completed successfully!")
        else:
            print("\nPDF generation failed!")

    elif args.contract_number:
        if generate_pdf_by_contract_number(args.contract_number):
            print("\nPDF generation completed successfully!")
        else:
            print("\nPDF generation failed!")

    else:
        print("No action specified. Use --help for options.")
        print("\nQuick commands:")
        print("  python generate_contract_pdf.py --list")
        print("  python generate_contract_pdf.py CAC-VSC-TXN-20250908041348-20250908040634")
        print("  python generate_contract_pdf.py --transaction TXN-20250908041348-20250908040634")
        print("  python generate_contract_pdf.py --all")


if __name__ == '__main__':
    main()