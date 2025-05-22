import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import plotly.express as px

def load_and_clean_data(file):
    """
    Loads an Excel (.xlsx) or CSV (.csv) file and attempts to find a header row
    containing 'Name' and 'Class'. Cleans column names by stripping whitespace
    and converting to lowercase for internal use, but retains original casing
    for display purposes.
    """
    if file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        # Handle Excel files
        xls = pd.ExcelFile(file)
        sheets = xls.sheet_names
        parser_func = lambda sheet_name, header_val: xls.parse(sheet_name=sheet_name, header=header_val)
    elif file.type == "text/csv":
        # Handle CSV files
        sheets = [None] # CSVs don't have sheets, so we can iterate once
        # Ensure the file pointer is reset for each read attempt in the loop
        file.seek(0) # Reset once before the loop
        parser_func = lambda sheet_name, header_val: (file.seek(0), pd.read_csv(file, header=header_val))[1]
    else:
        raise ValueError("Unsupported file type. Please upload an Excel (.xlsx) or CSV (.csv) file.")

    for sheet in sheets:
        for header_row_index in range(10): # Check first 10 rows for header
            try:
                # Attempt to parse the file with the current header_row_index
                df_try = parser_func(sheet, header_row_index)
                
                # Check for 'Name' and 'Class' columns (case-insensitive, trimmed)
                colnames_cleaned = [str(c).strip().lower() for c in df_try.columns]
                if 'name' in colnames_cleaned and 'class' in colnames_cleaned:
                    df = df_try.copy()
                    # Clean column names by stripping whitespace
                    df.columns = [str(c).strip() for c in df.columns]
                    # Drop any rows that are entirely NaN (often remaining empty rows after header detection)
                    df.dropna(how='all', inplace=True)
                    
                    # Return the DataFrame, the sheet name (or "N/A" for CSV), and the detected header row index
                    return df, sheet if sheet is not None else "N/A", header_row_index
            except Exception as e:
                # If parsing fails or columns are not found, continue to the next header row/sheet
                # print(f"Debug: Attempt with header_row {header_row_index} on sheet {sheet} failed: {e}")
                continue # Try next header row or sheet

    # If no valid header is found after checking all attempts
    raise ValueError("No valid header with 'Name' and 'Class' found in the first 10 rows of any sheet.")

# --- Helper Functions ---
def mark_to_al(subject, mark):
    """
    Converts a subject mark to its corresponding AL category.
    Subject names are expected to be the display names (e.g., 'English', 'Fn Math').
    """
    if pd.isna(mark): return None
    # Ensure mark is numeric
    try:
        mark = float(mark)
    except ValueError:
        return None # Handle non-numeric marks

    if subject.startswith("Fn "):  # Foundation Subjects
        if mark >= 75: return 'A'
        elif mark >= 30: return 'B'
        else: return 'C'
    elif subject in ['HCL', 'HML', 'HTL']:  # Higher Mother Tongue
        if mark >= 80: return 'Distinction'
        elif mark >= 65: return 'Merit'
        elif mark >= 50: return 'Pass'
        else: return 'Ungraded'
    else:  # Standard Subjects
        if mark >= 90: return 'AL1'
        elif mark >= 85: return 'AL2'
        elif mark >= 80: return 'AL3'
        elif mark >= 75: return 'AL4'
        elif mark >= 65: return 'AL5'
        elif mark >= 45: return 'AL6'
        elif mark >= 20: return 'AL7'
        else: return 'AL8'

def al_to_numeric(al):
    """
    Converts an AL category (string) to a numeric value for calculations.
    Lower numeric value implies better performance.
    """
    if al is None: return None
    if isinstance(al, (int, float)): return al # Already numeric

    if al in ['A', 'Distinction']: return 1
    elif al in ['B', 'Merit']: return 2
    elif al in ['C', 'Pass']: return 3
    elif al in ['Ungraded']: return 4 # Ungraded is typically worse than a pass, but numerically "better" (lower) than AL8 score

    try:
        # For AL1 to AL8, extract the number
        return int(str(al).replace("AL", ""))
    except (ValueError, TypeError):
        return None # Handle cases like NaN, unexpected strings

def map_to_al_for_agg(subject, mark):
    """
    Converts a subject mark to a numeric AL score for aggregate calculation.
    Foundation subjects are mapped to equivalent AL scores for standard subjects.
    Higher Mother Tongue is excluded for aggregate AL calculation.
    """
    if pd.isna(mark): return None
    try:
        mark = float(mark)
    except ValueError:
        return None

    if subject.startswith("Fn "):  # Foundation subjects map to standard AL scores
        if mark >= 75: return 6 # Equivalent to AL6
        elif mark >= 30: return 7 # Equivalent to AL7
        else: return 8 # Equivalent to AL8 (or worse if desired)
    elif subject in ['HCL', 'HML', 'HTL']:  # Exclude HMT from aggregate AL
        return None
    else:  # Standard subjects
        if mark >= 90: return 1
        elif mark >= 85: return 2
        elif mark >= 80: return 3
        elif mark >= 75: return 4
        elif mark >= 65: return 5
        elif mark >= 45: return 6
        elif mark >= 20: return 7
        else: return 8 # AL8 or worse

def count_student_weak_subjects(row, all_subject_cols_original, al_converter_func):
    """
    Calculates the *count* of 'weak' subjects for a student for the data column.
    A subject is considered weak if its AL score is 2 or more points worse
    (higher numeric AL value) than the student's average AL score across all their subjects.
    """
    student_all_als_numeric = []
    for s_orig in all_subject_cols_original:
        al_col_name_orig = f"{s_orig}_AL"
        if al_col_name_orig in row.index: # Check if the AL column exists in the student's data row
            al_val_str = row.get(al_col_name_orig)
            al_val_num = al_converter_func(al_val_str)
            if al_val_num is not None:
                student_all_als_numeric.append(al_val_num)

    if not student_all_als_numeric: # No numeric AL scores found for the student
        return 0

    avg_al = np.mean(student_all_als_numeric)
    if pd.isna(avg_al): # Handle case where avg_al might be NaN
        return 0

    weak_subject_count = 0
    for s_orig in all_subject_cols_original:
        al_col_name_orig = f"{s_orig}_AL"
        if al_col_name_orig in row.index:
            al_val_str = row.get(al_col_name_orig)
            numeric_subject_al = al_converter_func(al_val_str)
            if numeric_subject_al is not None:
                if (numeric_subject_al - avg_al) >= 2:
                    weak_subject_count += 1
    return weak_subject_count

def get_weak_subject_styles(row, all_subject_cols_original, al_converter_func):
    """
    Generates CSS styles to highlight 'weak' subject AL cells for DataFrame.style.apply.
    A subject is considered weak if its AL score is 2 or more points worse
    (higher numeric AL value) than the student's average AL score across all their subjects.
    """
    styles_for_row = [''] * len(row.index)

    student_all_als_numeric = []
    for s_orig in all_subject_cols_original:
        al_col_name_orig = f"{s_orig}_AL"
        if al_col_name_orig in row.index:
            al_val_str = row.get(al_col_name_orig)
            al_val_num = al_converter_func(al_val_str)
            if al_val_num is not None:
                student_all_als_numeric.append(al_val_num)

    if not student_all_als_numeric:
        return styles_for_row

    avg_al = np.mean(student_all_als_numeric)
    if pd.isna(avg_al):
        return styles_for_row

    for i, col_name_in_display in enumerate(row.index):
        if col_name_in_display.endswith('_AL'):
            original_subject_name_for_display_col = col_name_in_display.replace('_AL', '')
            if original_subject_name_for_display_col in all_subject_cols_original:
                subject_al_val_str = row.get(col_name_in_display)
                numeric_subject_al = al_converter_func(subject_al_val_str)
                if numeric_subject_al is not None:
                    if (numeric_subject_al - avg_al) >= 2:
                        styles_for_row[i] = 'background-color: #ffcccc' # Light red for weak subjects
    return styles_for_row

# --- App Setup ---
st.set_page_config(page_title="Student Dashboard", layout="wide")
st.title("🎓 Student Performance Dashboard")

uploaded_file = st.file_uploader("Upload Excel or CSV file", type=["xlsx", "csv"])

df = pd.DataFrame() # Initialize df to avoid NameError if no file is uploaded
if uploaded_file:
    try:
        with st.spinner("Loading and processing data... This may take a moment."):
            df, sheet_used, header_row = load_and_clean_data(uploaded_file)
        st.success(f"✅ Successfully loaded data from {'sheet' if sheet_used != 'N/A' else 'file'} '{uploaded_file.name}' (header found at row {header_row + 1}).")

        # --- Data Preprocessing after successful upload ---
        subject_columns = []
        cleaned_df_columns = [col for col in df.columns if not str(col).strip().lower().startswith('unnamed:')]
        
        # Define a more comprehensive list of known non-subject column names
        known_non_subject_names = [
            'name', 'class', 'total marks', 'aggregate al', 'weak subjects', 'weak subjects (count)',
            'age', 'reg#', 'reg no', 'registration number', 'student id', 'index no', 'level', 'gender',
            'grade summary', 'summary', 'remarks', 'conduct', 'attendance', 'overall', 'rank', 'position'
            # Add more known non-subject column names from your specific files if needed
        ]

        for col in cleaned_df_columns:
            col_original_case = str(col).strip() # Keep original case for subject_columns list
            col_lower = col_original_case.lower()
            
            if col_lower in known_non_subject_names:
                continue

            temp_series = pd.to_numeric(df[col_original_case], errors='coerce')
            numeric_ratio = temp_series.count() / len(df) if len(df) > 0 else 0
            
            if pd.api.types.is_numeric_dtype(temp_series) and numeric_ratio > 0.5 and not pd.api.types.is_bool_dtype(df[col_original_case]):
                subject_columns.append(col_original_case) # Use original column name

        subject_columns = [col for col in subject_columns if 'total marks' not in str(col).lower()] # Final filter

        if not subject_columns:
            st.warning("⚠️ No subject mark columns detected automatically. Please ensure your subject columns contain numeric values and are not in the exclusion list. You might need to adjust the `known_non_subject_names` list in the script if valid subjects are being excluded.")
            st.stop()
        else:
            st.info(f"Detected subject columns: {', '.join(subject_columns)}")


        for sub_col in subject_columns:
            if sub_col in df.columns:
                df[sub_col] = pd.to_numeric(df[sub_col], errors='coerce')
            else:
                st.warning(f"Subject column '{sub_col}' was detected but not found in the DataFrame for numeric conversion. Skipping.")

        for sub in subject_columns:
            if sub in df.columns:
                df[f"{sub}_AL"] = df.apply(lambda row: mark_to_al(sub, row[sub]), axis=1)
            else:
                st.warning(f"Automatically detected subject column '{sub}' not found in the loaded data for AL conversion. It will be skipped.")

        mark_columns_for_total = [col for col in subject_columns if col in df.columns]
        if mark_columns_for_total:
            df['Total Marks'] = df[mark_columns_for_total].sum(axis=1, skipna=True)
        else:
            df['Total Marks'] = np.nan
            st.warning("No valid subject mark columns were processed to calculate 'Total Marks'.")

        def calculate_aggregate_al_for_row(row):
            als_for_agg = []
            for sub in subject_columns:
                if sub in row.index: # Ensure subject column exists in the row
                    al_val = map_to_al_
