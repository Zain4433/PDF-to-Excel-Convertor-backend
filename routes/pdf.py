from flask import Blueprint, request, jsonify, send_file
from utils.auth_utils import verify_token
from werkzeug.utils import secure_filename
import os
import tempfile
import tabula
import pandas as pd
from io import BytesIO
import re
import PyPDF2

# Set JAVA_HOME if Java is installed but not in PATH
if not os.environ.get('JAVA_HOME'):
    java_paths = [
        r"C:\Program Files\Microsoft\jdk-17.0.17.10-hotspot",
        r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot",
        r"C:\Program Files\Java\jdk-17",
    ]
    for java_path in java_paths:
        if os.path.exists(java_path) and os.path.exists(os.path.join(java_path, "bin", "java.exe")):
            os.environ['JAVA_HOME'] = java_path
            # Also add to PATH for this process
            current_path = os.environ.get('PATH', '')
            java_bin = os.path.join(java_path, "bin")
            if java_bin not in current_path:
                os.environ['PATH'] = java_bin + os.pathsep + current_path
            print(f"Set JAVA_HOME to: {java_path}")
            break

pdf_bp = Blueprint('pdf', __name__, url_prefix='/api/pdf')

# --- Authentication Mock/Placeholder ---
def get_user_from_token():
    """Extract and verify user from token (Assumes 'utils.auth_utils.verify_token' exists)"""
    # NOTE: This is a placeholder for actual token verification
    auth_header = request.headers.get('Authorization')
    if auth_header and len(auth_header.split(' ')) > 1:
        return {'user_id': '123'}
    return None

# -------------------------
# Helper functions and Regex Patterns
# -------------------------
MONTHS_PATTERN = r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
AMOUNT_PATTERN = r"(\d[\d, ]*\.\d{2})"

date_only_re = re.compile(rf"^{MONTHS_PATTERN}[\s\.]?\s*(\d{{1,2}})$", re.IGNORECASE)
amount_re = re.compile(AMOUNT_PATTERN)

def normalize_desc(s: str) -> str:
    """Normalize description string for dedup checks"""
    return re.sub(r"\s+", " ", (s or "").strip()).upper()

def is_footer_or_header(desc_upper: str) -> bool:
    """
    Identifies and aggressively filters out all known redundant values.
    FIXED: Expanded list and new numeric-only filtering.
    """
    # *** AGGRESSIVE FILTER LIST ***
    footer_phrases = [
        # Headers/Footers/Summaries/Account Labels
        "MONTHLY", "NEXT STATEMENT", "DEP CONTENT", "UNC BATCH", "CHQS ENCLOSED", 
        "BALANCE FORWARD", "CHEQUE/DEBIT", "DEPOSIT/CREDIT", "BALANCE", "DESCRIPTION",
        "ITEMS", "CREDITS", "DEBITS", "NO.", "AMOUNT", "AVER.", "MIN.",
        "STATEMENT OF ACCOUNT", "ACCOUNTS ISSUED BY", "PLEASE ENSURE", "ACCOUNT CAD",
        "BUSINESS CHEQUING", "UNLIMITED",
        
        # Account/Address/Contact Details
        "TDCDA", "TD CANADA TRUST", "BRAMPTON SPRINGDALE", "LAGERFELD DR", "L7A 5L3", 
        "L6R 2K7", "11261991 CANADA INC.", "ARSHAD MOHAMMAD", "TEL:", "TTY:", 
        "BRANCH NO", "ACCOUNT NO", "7594-5300663", "1-866-222-3456", "1-800-361-1180", 
        
        # Numeric/Code strings appearing as noise
        "0028209", "0169", "08209", "0184" 
    ]
    
    # 1. Filter by keyword or phrase match
    if any(p in desc_upper for p in footer_phrases):
        return True
    
    # 2. Filter extremely short strings (less than 4 chars)
    if len(desc_upper) < 4 and not amount_re.search(desc_upper):
        return True
        
    # 3. Filter lines that contain only numbers, spaces, dots, commas, or dashes (e.g., account numbers, balances without description)
    if re.fullmatch(r'^[\d\s\.,-]+$', desc_upper):
        return True
        
    return False

# -------------------------
# upload endpoint
# -------------------------
@pdf_bp.route('/upload', methods=['POST'])
def upload_pdf():
    # ... (Standard upload logic, unchanged)
    try:
        user_payload = get_user_from_token()
        if not user_payload:
            return jsonify({'error': 'Unauthorized'}), 401
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        filename = secure_filename(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            file.save(temp_file.name)
            temp_file_path = temp_file.name
        num_pages = 0
        tables_found = 0
        try:
            # Get page count using PyPDF2
            with open(temp_file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                num_pages = len(pdf_reader.pages)
            
            # Extract tables using tabula-py
            tables = tabula.read_pdf(temp_file_path, pages='all', multiple_tables=True, silent=True)
            if tables:
                tables_found = len(tables)
        except Exception:
            pass
        finally:
            try:
                os.unlink(temp_file_path)
            except:
                pass
        return jsonify({
            'message': 'File uploaded and parsed successfully',
            'file_info': {
                'filename': filename,
                'size_kb': round(file_size / 1024, 2),
                'num_pages': num_pages,
                'tables_found': tables_found,
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# -------------------------
# convert endpoint - Fixed
# -------------------------
@pdf_bp.route('/convert', methods=['POST'])
def convert_to_excel():
    """Convert PDF to Excel endpoint"""
    try:
        user_payload = get_user_from_token()
        if not user_payload:
            return jsonify({'error': 'Unauthorized'}), 401

        if 'file' not in request.files: return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if not file.filename.lower().endswith('.pdf'): return jsonify({'error': 'Only PDF files are allowed'}), 400

        filename = secure_filename(file.filename)
        base_filename = os.path.splitext(filename)[0]

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            file.save(temp_pdf.name)
            temp_pdf_path = temp_pdf.name

        excel_buffer = BytesIO()
        try:
            target_headers = ["DESCRIPTION", "CHEQUE/DEBIT", "DEPOSIT/CREDIT", "DATE"]

            def clean_cell(cell):
                if cell is None: return ""
                text = str(cell).strip()
                return re.sub(r'\s+', ' ', text) if text else ""

            all_rows = []
            seen_keys = set()

            # Extract tables using tabula-py from all pages
            try:
                tables = tabula.read_pdf(temp_pdf_path, pages='all', multiple_tables=True, silent=True)
                if tables is None:
                    tables = []
                print(f"Successfully extracted {len(tables)} tables using tabula-py")
            except Exception as tabula_error:
                # If tabula fails (e.g., Java not installed), continue with text extraction only
                import traceback
                print(f"Warning: tabula-py failed: {tabula_error}")
                print(f"Traceback: {traceback.format_exc()}")
                tables = []
            
            # Get page count for tracking
            with open(temp_pdf_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                total_pages = len(pdf_reader.pages)
            
            # Extract text from all pages for fallback processing
            page_texts = {}
            with open(temp_pdf_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    page_texts[page_num] = page.extract_text() or ""

            # Process tables extracted by tabula-py
            for table_idx, df in enumerate(tables):
                if df is None or df.empty:
                    continue
                
                # Convert DataFrame to list of lists for processing
                tbl = df.values.tolist()
                # Add header row if DataFrame has column names
                if not df.columns.empty:
                    header_row = [str(col) for col in df.columns.tolist()]
                    tbl = [header_row] + tbl
                
                if not tbl or len(tbl) == 0:
                    continue
                
                start_idx = 0
                if tbl and tbl[0] and "DESCRIPTION" in clean_cell(tbl[0][0]).upper():
                    start_idx = 1

                for data_row in tbl[start_idx:]:
                    cleaned = [clean_cell(c) for c in data_row]
                    normalized = cleaned[:5] if len(cleaned) >= 5 else cleaned + [""] * (5 - len(cleaned))
                    desc = normalized[0].strip()
                    desc_norm = normalize_desc(desc)
                    
                    if not any(cell.strip() for cell in normalized) or is_footer_or_header(desc_norm):
                        continue

                    debit_raw = normalized[1].strip()
                    credit_date_raw = normalized[2].strip()
                    date_raw = normalized[3].strip() if len(normalized) > 3 else ""
                    
                    debit = ""
                    credit = ""
                    date = 'N/A'

                    # Extract date from combined amount+date strings (e.g., "3,565.00OCT01")
                    date_match = None
                    combined_string = credit_date_raw + date_raw
                    
                    # Try to find date pattern in the combined string
                    date_match = re.search(rf"({MONTHS_PATTERN}[\s\.]?\s*\d{{1,2}})", combined_string, re.IGNORECASE)
                    if date_match:
                        date_str = date_match.group(1).strip()
                        m_date_parts = date_only_re.match(date_str)
                        if m_date_parts:
                            month = m_date_parts.group(1).upper()
                            day = m_date_parts.group(2).zfill(2)
                            date = month + day
                    
                    # Extract amount from debit column
                    if re.search(AMOUNT_PATTERN, debit_raw):
                        # Remove any date that might be attached to the amount
                        amount_match = re.search(AMOUNT_PATTERN, debit_raw)
                        if amount_match:
                            debit = amount_match.group(0).strip().replace(' ', '')
                    
                    # Extract amount from credit/date column (remove date if present)
                    if re.search(AMOUNT_PATTERN, credit_date_raw):
                        amount_match = re.search(AMOUNT_PATTERN, credit_date_raw)
                        if amount_match:
                            credit = amount_match.group(0).strip().replace(' ', '')
                    
                    # If no date found yet, check the date column separately
                    if date == 'N/A' and date_raw:
                        date_match = re.search(rf"({MONTHS_PATTERN}[\s\.]?\s*\d{{1,2}})", date_raw, re.IGNORECASE)
                        if date_match:
                            date_str = date_match.group(1).strip()
                            m_date_parts = date_only_re.match(date_str)
                            if m_date_parts:
                                month = m_date_parts.group(1).upper()
                                day = m_date_parts.group(2).zfill(2)
                                date = month + day
                        
                    if not debit and not credit:
                        continue

                    key = (desc_norm, (debit or credit), date)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        # Estimate page number based on table index (rough approximation)
                        page_num = min((table_idx // 2) + 1, total_pages) if total_pages > 0 else 1
                        all_rows.append({'row_data': [desc, debit, credit, date], 'page_num': page_num})

            # 2) Advanced fallback using page text lines (Robust for multi-line transactions)
            for page_num, page_text in page_texts.items():
                page_text_lines = [ln for ln in page_text.splitlines() if ln.strip()]
                
                last_desc = None
                i = 0
                while i < len(page_text_lines):
                    line = page_text_lines[i].strip()
                    
                    if is_footer_or_header(normalize_desc(line)):
                        i += 1
                        continue

                    # 2a) If line matches full row (desc + amount + date)
                    m_full = re.search(rf"^(.*?){AMOUNT_PATTERN}.*?{MONTHS_PATTERN}[\s\.]?\s*(\d{{1,2}})$", line, re.IGNORECASE)
                    if m_full:
                        desc = m_full.group(1).strip()
                        amount = m_full.group(2).replace(" ", "")
                        month = m_full.group(3).upper()
                        day = m_full.group(4).zfill(2)
                        date = month + day
                        desc_norm = normalize_desc(desc)

                        if not is_footer_or_header(desc_norm):
                            key = (desc_norm, amount, date)
                            if key not in seen_keys:
                                withdrawal_keywords = ["SEND", "ATM", "WITHDRA", "AP", "TFR-TO"]
                                debit = amount if any(w in desc_norm for w in withdrawal_keywords) else ""
                                credit = "" if debit else amount
                                all_rows.append({'row_data': [desc, debit, credit, date], 'page_num': page_num})
                                seen_keys.add(key)
                        
                        last_desc = None # Reset state after full match
                        i += 1
                        continue

                    # 2b) If line contains AMOUNT and DATE, and we have a pending description (`last_desc`)
                    m_amount_date = re.search(rf"({AMOUNT_PATTERN}).*?({MONTHS_PATTERN}[\s\.]?\s*(\d{{1,2}}))", line, re.IGNORECASE)
                    if m_amount_date and last_desc:
                        amount = m_amount_date.group(1).replace(" ", "")
                        date_str = m_amount_date.group(2).strip()
                        
                        # Extract Month and Day from the date string for normalization
                        m_date_parts = date_only_re.match(date_str)
                        if m_date_parts:
                            month = m_date_parts.group(1).upper()
                            day = m_date_parts.group(2).zfill(2)
                            date = month + day
                        else:
                            # Fallback if only amount is found on this line
                            i += 1
                            continue # Wait for a date line, if any
                        
                        desc_norm = normalize_desc(last_desc)

                        if not is_footer_or_header(desc_norm):
                            key = (desc_norm, amount, date)
                            if key not in seen_keys:
                                withdrawal_keywords = ["SEND", "ATM", "WITHDRA", "AP", "TFR-TO"]
                                debit = amount if any(w in desc_norm for w in withdrawal_keywords) else ""
                                credit = "" if debit else amount
                                all_rows.append({'row_data': [last_desc, debit, credit, date], 'page_num': page_num})
                                seen_keys.add(key)
                        
                        last_desc = None
                        i += 1
                        continue

                    # 2c) If line is alpha-heavy and likely a description (no amount or date), set `last_desc`
                    if re.search(r"[A-Za-z]", line) and not amount_re.search(line) and not date_only_re.match(line):
                        if not is_footer_or_header(normalize_desc(line)):
                            last_desc = line.strip()
                        i += 1
                        continue
                    
                    # Fallthrough: reset state if no pairing was made
                    last_desc = None
                    i += 1

            # Check if we found any rows after processing all pages
            if not all_rows:
                raise Exception("No table found in PDF. Please ensure the PDF contains a table.")

            row_data_only = [row['row_data'] for row in all_rows]
            df = pd.DataFrame(row_data_only, columns=target_headers)
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Sheet1', index=False)

            excel_buffer.seek(0)

        except Exception as parse_error:
            import traceback
            error_msg = str(parse_error)
            print(f"Error in PDF conversion: {error_msg}")
            print(traceback.format_exc())
            raise parse_error
        finally:
            try:
                os.unlink(temp_pdf_path)
            except:
                pass

        excel_filename = f"{base_filename}.xlsx"
        return send_file(
            excel_buffer,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=excel_filename
        )

    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"Error in convert endpoint: {error_msg}")
        print(traceback.format_exc())
        return jsonify({'error': error_msg}), 500

# -------------------------
# get-table-data endpoint - Fixed
# -------------------------
@pdf_bp.route('/get-table-data', methods=['POST'])
def get_table_data():
    """
    Get table data from PDF as JSON endpoint. Targets Page 1 extraction.
    FIXED: Incorporates aggressive filtering and multi-line reassembly logic.
    """
    try:
        user_payload = get_user_from_token()
        if not user_payload:
            return jsonify({'error': 'Unauthorized'}), 401
        
        if 'file' not in request.files: return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if not file.filename.lower().endswith('.pdf'): return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            file.save(temp_pdf.name)
            temp_pdf_path = temp_pdf.name

        try:
            # Check if PDF has pages using PyPDF2
            with open(temp_pdf_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                if len(pdf_reader.pages) == 0:
                    raise Exception("PDF contains no pages.")
                
                # Extract text from first page
                first_page = pdf_reader.pages[0]
                page_text = first_page.extract_text() or ""
                page_text_lines = [ln for ln in page_text.splitlines() if ln.strip()]

            target_headers = ["DESCRIPTION", "CHEQUE/DEBIT", "DEPOSIT/CREDIT", "DATE"]
            
            def clean_cell(cell):
                if cell is None: return ""
                text = str(cell).strip()
                return re.sub(r'\s+', ' ', text) if text else ""

            all_rows = []
            seen_keys = set()
            page_num = 1
            
            # Extract tables from first page using tabula-py
            try:
                tables = tabula.read_pdf(temp_pdf_path, pages=1, multiple_tables=True, silent=True)
                if tables is None:
                    tables = []
                print(f"Successfully extracted {len(tables)} tables using tabula-py for get-table-data")
            except Exception as tabula_error:
                # If tabula fails (e.g., Java not installed), continue with text extraction only
                import traceback
                print(f"Warning: tabula-py failed in get-table-data: {tabula_error}")
                print(f"Traceback: {traceback.format_exc()}")
                tables = []

            # 1) tabula-py table processing (with better filtering)
            if tables:
                for tbl_df in tables:
                    if tbl_df is None or tbl_df.empty:
                        continue
                    
                    # Convert DataFrame to list of lists for processing
                    tbl = tbl_df.values.tolist()
                    # Add header row if DataFrame has column names
                    if not tbl_df.columns.empty:
                        header_row = [str(col) for col in tbl_df.columns.tolist()]
                        tbl = [header_row] + tbl
                    
                    if not tbl or len(tbl) == 0:
                        continue
                    
                    start_idx = 0
                    if tbl and tbl[0] and "DESCRIPTION" in clean_cell(tbl[0][0]).upper():
                        start_idx = 1
                    
                    for data_row in tbl[start_idx:]:
                        cleaned = [clean_cell(c) for c in data_row]
                        normalized = cleaned[:5] if len(cleaned) >= 5 else cleaned + [""] * (5 - len(cleaned))

                        desc = normalized[0].strip()
                        desc_norm = normalize_desc(desc)
                        
                        if not any(cell.strip() for cell in normalized) or is_footer_or_header(desc_norm):
                            continue
                        
                        debit_raw = normalized[1].strip()
                        credit_date_raw = normalized[2].strip()
                        date_raw = normalized[3].strip() if len(normalized) > 3 else ""
                        
                        debit = ""
                        credit = ""
                        date = 'N/A'

                        # Extract date from combined amount+date strings (e.g., "3,565.00OCT01")
                        date_match = None
                        combined_string = credit_date_raw + date_raw
                        
                        # Try to find date pattern in the combined string
                        date_match = re.search(rf"({MONTHS_PATTERN}[\s\.]?\s*\d{{1,2}})", combined_string, re.IGNORECASE)
                        if date_match:
                            date_str = date_match.group(1).strip()
                            m_date_parts = date_only_re.match(date_str)
                            if m_date_parts:
                                month = m_date_parts.group(1).upper()
                                day = m_date_parts.group(2).zfill(2)
                                date = month + day
                        
                        # Extract amount from debit column
                        if re.search(AMOUNT_PATTERN, debit_raw):
                            # Remove any date that might be attached to the amount
                            amount_match = re.search(AMOUNT_PATTERN, debit_raw)
                            if amount_match:
                                debit = amount_match.group(0).strip().replace(' ', '')
                        
                        # Extract amount from credit/date column (remove date if present)
                        if re.search(AMOUNT_PATTERN, credit_date_raw):
                            amount_match = re.search(AMOUNT_PATTERN, credit_date_raw)
                            if amount_match:
                                credit = amount_match.group(0).strip().replace(' ', '')
                        
                        # If no date found yet, check the date column separately
                        if date == 'N/A' and date_raw:
                            date_match = re.search(rf"({MONTHS_PATTERN}[\s\.]?\s*\d{{1,2}})", date_raw, re.IGNORECASE)
                            if date_match:
                                date_str = date_match.group(1).strip()
                                m_date_parts = date_only_re.match(date_str)
                                if m_date_parts:
                                    month = m_date_parts.group(1).upper()
                                    day = m_date_parts.group(2).zfill(2)
                                    date = month + day
                            
                        if not debit and not credit:
                            continue

                        key = (desc_norm, (debit or credit), date)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            all_rows.append({'row_data': [desc, debit, credit, date], 'page_num': page_num})


            # 2) Advanced fallback using page text lines (FIXED multi-line transaction logic)
            last_desc = None
            i = 0
            while i < len(page_text_lines):
                line = page_text_lines[i].strip()
                
                if is_footer_or_header(normalize_desc(line)):
                    i += 1
                    continue
                    
                # 2a) If line matches full row (desc + amount + date)
                m_full = re.search(rf"^(.*?){AMOUNT_PATTERN}.*?{MONTHS_PATTERN}[\s\.]?\s*(\d{{1,2}})$", line, re.IGNORECASE)
                if m_full:
                    desc = m_full.group(1).strip()
                    amount = m_full.group(2).replace(" ", "")
                    month = m_full.group(3).upper()
                    day = m_full.group(4).zfill(2)
                    date = month + day
                    desc_norm = normalize_desc(desc)

                    if not is_footer_or_header(desc_norm):
                        key = (desc_norm, amount, date)
                        if key not in seen_keys:
                            withdrawal_keywords = ["SEND", "ATM", "WITHDRA", "AP", "TFR-TO"]
                            debit = amount if any(w in desc_norm for w in withdrawal_keywords) else ""
                            credit = "" if debit else amount
                            all_rows.append({'row_data': [desc, debit, credit, date], 'page_num': page_num})
                            seen_keys.add(key)
                    
                    last_desc = None
                    i += 1
                    continue

                # 2b) If line contains AMOUNT and DATE, and we have a pending description (`last_desc`)
                m_amount_date = re.search(rf"({AMOUNT_PATTERN}).*?({MONTHS_PATTERN}[\s\.]?\s*(\d{{1,2}}))", line, re.IGNORECASE)
                if m_amount_date and last_desc:
                    amount = m_amount_date.group(1).replace(" ", "")
                    date_str = m_amount_date.group(2).strip()
                    
                    m_date_parts = date_only_re.match(date_str)
                    if m_date_parts:
                        month = m_date_parts.group(1).upper()
                        day = m_date_parts.group(2).zfill(2)
                        date = month + day
                    else:
                        i += 1
                        continue
                    
                    desc_norm = normalize_desc(last_desc)

                    if not is_footer_or_header(desc_norm):
                        key = (desc_norm, amount, date)
                        if key not in seen_keys:
                            withdrawal_keywords = ["SEND", "ATM", "WITHDRA", "AP", "TFR-TO"]
                            debit = amount if any(w in desc_norm for w in withdrawal_keywords) else ""
                            credit = "" if debit else amount
                            all_rows.append({'row_data': [last_desc, debit, credit, date], 'page_num': page_num})
                            seen_keys.add(key)
                    
                    last_desc = None
                    i += 1
                    continue

                # 2c) If line is alpha-heavy and likely a description (no amount or date), set `last_desc`
                if re.search(r"[A-Za-z]", line) and not amount_re.search(line) and not date_only_re.match(line):
                    if not is_footer_or_header(normalize_desc(line)):
                        last_desc = line.strip()
                    i += 1
                    continue

                # Fallthrough: reset state
                last_desc = None
                i += 1
            
            # --- End of Line Parsing ---

            # Check if we found any rows after processing all pages
            if not all_rows:
                raise Exception("No transaction data found in PDF on Page 1.")

            final_table_data = [row['row_data'] for row in all_rows if row['page_num'] == 1]
            
            # Final check to remove any duplicate rows that might have been added by both tabula-py tables and line parsing
            # This uses pandas to drop duplicates
            df = pd.DataFrame(final_table_data, columns=target_headers)
            df.drop_duplicates(subset=["DESCRIPTION", "CHEQUE/DEBIT", "DEPOSIT/CREDIT", "DATE"], keep='first', inplace=True)

            return jsonify({
                'message': 'Table data extracted successfully for Page 1',
                'headers': target_headers,
                'data': df.to_dict('records')
            }), 200

        except Exception as parse_error:
            raise parse_error
        finally:
            try:
                os.unlink(temp_pdf_path)
            except:
                pass

    except Exception as e:
        return jsonify({'error': str(e)}), 500