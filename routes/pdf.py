from flask import Blueprint, request, jsonify, send_file
from utils.auth_utils import verify_token
from werkzeug.utils import secure_filename
import os
import tempfile
from datetime import datetime
import pdfplumber
import pandas as pd
from io import BytesIO
import re

pdf_bp = Blueprint('pdf', __name__, url_prefix='/api/pdf')

def get_user_from_token():
    """Extract and verify user from token"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    
    try:
        token = auth_header.split(' ')[1]  # Bearer <token>
    except IndexError:
        return None
    
    payload = verify_token(token)
    return payload

@pdf_bp.route('/upload', methods=['POST'])
def upload_pdf():
    """Upload PDF file endpoint"""
    try:
        # Verify authentication
        user_payload = get_user_from_token()
        if not user_payload:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        # Get file information
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        filename = secure_filename(file.filename)
        
        # Print PDF file information
        print("\n" + "="*60)
        print("PDF FILE UPLOADED")
        print("="*60)
        print(f"User ID: {user_payload.get('user_id')}")
        print(f"User Email: {user_payload.get('email')}")
        print(f"Filename: {filename}")
        print(f"Original Filename: {file.filename}")
        print(f"File Size: {file_size} bytes ({file_size / 1024:.2f} KB)")
        print(f"Content Type: {file.content_type}")
        print(f"Upload Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("="*60)
        
        # Parse PDF content using pdfplumber
        file.seek(0)  # Reset file pointer
        pdf_content = ""
        num_pages = 0
        tables_found = 0
        
        # Save file temporarily to parse it
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            file.save(temp_file.name)
            temp_file_path = temp_file.name
        
        try:
            with pdfplumber.open(temp_file_path) as pdf:
                num_pages = len(pdf.pages)
                print(f"\nTotal Pages: {num_pages}")
                print("\n" + "="*60)
                print("PDF CONTENT")
                print("="*60)
                
                # Extract text from each page
                for page_num, page in enumerate(pdf.pages, 1):
                    print(f"\n--- Page {page_num} ---")
                    page_text = page.extract_text()
                    if page_text:
                        print(page_text)
                        pdf_content += f"\n--- Page {page_num} ---\n{page_text}\n"
                    else:
                        print("(No text content found on this page)")
                    
                    # Extract tables if any
                    tables = page.extract_tables()
                    if tables:
                        tables_found += len(tables)
                        print(f"\nTables found on page {page_num}: {len(tables)}")
                        for table_num, table in enumerate(tables, 1):
                            print(f"\nTable {table_num} on Page {page_num}:")
                            for row in table:
                                print(row)
                
                print("\n" + "="*60)
                print(f"SUMMARY")
                print("="*60)
                print(f"Total Pages: {num_pages}")
                print(f"Total Tables Found: {tables_found}")
                print(f"Total Text Length: {len(pdf_content)} characters")
                print("="*60 + "\n")
                
        except Exception as parse_error:
            print(f"\nError parsing PDF: {parse_error}")
            print("="*60 + "\n")
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except:
                pass
        
        return jsonify({
            'message': 'File uploaded and parsed successfully',
            'file_info': {
                'filename': filename,
                'size': file_size,
                'size_kb': round(file_size / 1024, 2),
                'content_type': file.content_type,
                'uploaded_at': datetime.utcnow().isoformat(),
                'num_pages': num_pages,
                'tables_found': tables_found,
                'content_length': len(pdf_content)
            }
        }), 200
        
    except Exception as e:
        print(f"Error uploading file: {e}")
        return jsonify({'error': str(e)}), 500

@pdf_bp.route('/convert', methods=['POST'])
def convert_to_excel():
    """Convert PDF to Excel endpoint"""
    try:
        # Verify authentication
        user_payload = get_user_from_token()
        if not user_payload:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        filename = secure_filename(file.filename)
        base_filename = os.path.splitext(filename)[0]
        
        print("\n" + "="*60)
        print("PDF TO EXCEL CONVERSION")
        print("="*60)
        print(f"User ID: {user_payload.get('user_id')}")
        print(f"User Email: {user_payload.get('email')}")
        print(f"Filename: {filename}")
        print(f"Conversion Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("="*60)
        
        # Save file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            file.save(temp_pdf.name)
            temp_pdf_path = temp_pdf.name
        
        # Create Excel file in memory
        excel_buffer = BytesIO()
        
        try:
            with pdfplumber.open(temp_pdf_path) as pdf:
                num_pages = len(pdf.pages)
                print(f"\nProcessing {num_pages} page(s)...")
                
                # Extract tables using pdfplumber tables and map to fixed headers
                target_headers = ["DESCRIPTION", "CHEQUE/DEBIT", "DEPOSIT/CREDIT", "DATE", "BALANCE"]

                def clean_cell(cell):
                    if cell is None:
                        return ""
                    text = str(cell).strip()
                    return text if text else ""

                all_rows = []
                for page_num, page in enumerate(pdf.pages, 1):
                    print(f"Processing page {page_num}...")
                    tables = page.extract_tables()
                    if not tables:
                        continue
                    for tbl in tables:
                        if not tbl or len(tbl) == 0:
                            continue
                        header_row = [clean_cell(c).upper() for c in tbl[0]]
                        has_description = any("DESCRIP" in h for h in header_row)
                        has_date = any("DATE" in h for h in header_row)

                        # If headers detected, skip the first row; otherwise treat all rows as data
                        start_idx = 1 if (has_description and has_date) else 0
                        for data_row in tbl[start_idx:]:
                            cleaned = [clean_cell(c) for c in data_row]
                            # Normalize to 5 columns
                            normalized = cleaned[:5] if len(cleaned) >= 5 else cleaned + [""] * (5 - len(cleaned))
                            
                            # Find date-like value anywhere in the row
                            date_pattern = re.compile(r"^[A-Z]{3}\d{1,2}$")
                            date_val = None
                            date_idx = None
                            for idx, val in enumerate(normalized):
                                candidate = val.replace(" ", "").upper()
                                if date_pattern.match(candidate):
                                    date_val = candidate
                                    date_idx = idx
                                    break
                            if not date_val:
                                continue
                            # Ensure date is placed in DATE column (index 3)
                            if date_idx != 3:
                                normalized[3] = date_val
                                if date_idx is not None:
                                    normalized[date_idx] = ""
                            
                            desc_val = normalized[0].upper()
                            # Drop footer/summary rows that might still carry a date-like value
                            footer_phrases = [
                                "MONTHLY", "NEXT STATEMENT", "DEP CONTENT", "ITEMS", "UNC BATCH",
                                "CREDITS", "DEBITS", "NO.", "AMOUNT", "AVER.", "MIN."
                            ]
                            if any(phrase in desc_val for phrase in footer_phrases):
                                continue
                            all_rows.append(normalized[:5])

                if not all_rows:
                    raise Exception("No table found in PDF. Please ensure the PDF contains a table.")

                df = pd.DataFrame(all_rows, columns=target_headers)
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Sheet1', index=False)
                print(f"  - Converted table: {len(df)} rows x {len(df.columns)} columns")
                
                excel_buffer.seek(0)
                
                print("\n" + "="*60)
                print("CONVERSION COMPLETE")
                print("="*60)
                print(f"Total Pages Processed: {num_pages}")
                print(f"Table extracted and converted to Excel")
                print("="*60 + "\n")
                
        except Exception as parse_error:
            print(f"\nError converting PDF: {parse_error}")
            print("="*60 + "\n")
            raise parse_error
        finally:
            # Clean up temporary PDF file
            try:
                os.unlink(temp_pdf_path)
            except:
                pass
        
        # Return Excel file
        excel_filename = f"{base_filename}.xlsx"
        return send_file(
            excel_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=excel_filename
        )
        
    except Exception as e:
        print(f"Error converting file: {e}")
        return jsonify({'error': str(e)}), 500

