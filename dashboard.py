import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import plotly.express as px

def load_and_clean_data(file):
    """
    Loads an Excel (.xlsx) or CSV (.csv) file and attempts to find a header row
    containing 'Name' and 'Class'. Cleans column names by stripping whitespace.
    """
    if file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        xls = pd.ExcelFile(file)
        sheets = xls.sheet_names
        parser_func = lambda sheet_name, header_val: xls.parse(sheet_name=sheet_name, header=header_val)
    elif file.type == "text/csv":
        sheets = [None]  # CSVs don't have sheets
        # Ensure file pointer is reset for multiple reads in CSV header detection
        file.seek(0) 
        def csv_parser_with_seek(f, hv):
            f.seek(0) # Reset before each read attempt
            return pd.read_csv(f, header=hv)
        parser_func = lambda sheet_name, header_val: csv_parser_with_seek(file, header_val)
    else:
        raise ValueError("Unsupported file type. Please upload an Excel (.xlsx) or CSV (.csv) file.")

    for sheet in sheets:
        for header_row_index in range(10):  # Check first 10 rows for header
            try:
                df_try = parser_func(sheet, header_row_index)
                colnames_cleaned = [str(c).strip().lower() for c in df_try.columns]
                if 'name' in colnames_cleaned and 'class' in colnames_cleaned:
                    df = df_try.copy()
                    df.columns = [str(c).strip() for c in df.columns]
                    df.dropna(how='all', inplace=True)
                    return df, sheet if sheet is not None else "N/A", header_row_index
            except Exception:
                continue  # Try next header row or sheet
    raise ValueError("No valid header with 'Name' and 'Class' found in the first 10 rows of any sheet.")

# --- Helper Functions ---
def mark_to_al(subject, mark):
    if pd.isna(mark): return None
    try:
        mark = float(mark)
    except ValueError:
        return None
    if subject.startswith("Fn "):
        if mark >= 75: return 'A'
        elif mark >= 30: return 'B'
        else: return 'C'
    elif subject in ['HCL', 'HML', 'HTL']:
        if mark >= 80: return 'Distinction'
        elif mark >= 65: return 'Merit'
        elif mark >= 50: return 'Pass'
        else: return 'Ungraded'
    else:
        if mark >= 90: return 'AL1'
        elif mark >= 85: return 'AL2'
        elif mark >= 80: return 'AL3'
        elif mark >= 75: return 'AL4'
        elif mark >= 65: return 'AL5'
        elif mark >= 45: return 'AL6'
        elif mark >= 20: return 'AL7'
        else: return 'AL8'

def al_to_numeric(al):
    if al is None: return None
    if isinstance(al, (int, float)): return al
    if al in ['A', 'Distinction']: return 1
    elif al in ['B', 'Merit']: return 2
    elif al in ['C', 'Pass']: return 3
    elif al == 'Ungraded': return 4 # Higher number could be used if Ungraded is worse than AL8 for this logic
    try:
        return int(str(al).replace("AL", ""))
    except (ValueError, TypeError):
        return None

def map_to_al_for_agg(subject, mark):
    if pd.isna(mark): return None
    try:
        mark = float(mark)
    except ValueError:
        return None
    if subject.startswith("Fn "):
        if mark >= 75: return 6
        elif mark >= 30: return 7
        else: return 8
    elif subject in ['HCL', 'HML', 'HTL']:
        return None
    else:
        if mark >= 90: return 1
        elif mark >= 85: return 2
        elif mark >= 80: return 3
        elif mark >= 75: return 4
        elif mark >= 65: return 5
        elif mark >= 45: return 6
        elif mark >= 20: return 7
        else: return 8

def count_student_weak_subjects(row, all_subject_cols_original, al_converter_func):
    als_numeric = []
    for s in all_subject_cols_original:
        al_col_name = f"{s}_AL"
        al_grade_str = row.get(al_col_name)
        if al_grade_str is not None:
            numeric_val = al_converter_func(al_grade_str)
            if numeric_val is not None:
                als_numeric.append(numeric_val)
    if not als_numeric: return 0
    avg_al = np.mean(als_numeric)
    weak_subject_count = 0
    for s in all_subject_cols_original:
        al_col_name = f"{s}_AL"
        al_grade_str = row.get(al_col_name)
        if al_grade_str is not None:
            numeric_subject_al = al_converter_func(al_grade_str)
            if numeric_subject_al is not None and avg_al is not None:
                if (numeric_subject_al - avg_al) >= 2:
                    weak_subject_count += 1
    return weak_subject_count

# --- App Setup ---
st.set_page_config(page_title="Student Dashboard", layout="wide")
st.title("🎓 Student Performance Dashboard")

uploaded_file = st.file_uploader("Upload Excel or CSV file", type=["xlsx", "csv"])
df = pd.DataFrame()
subject_columns = [] # Initialize subject_columns in a broader scope

if uploaded_file:
    try:
        with st.spinner("Loading and processing data..."):
            df, sheet_used, header_row = load_and_clean_data(uploaded_file)
        st.success(f"✅ Loaded data from '{uploaded_file.name}' " +
                   (f"(Sheet: {sheet_used})" if sheet_used != "N/A" else "") +
                   f" using header row {header_row + 1}.")

        cleaned_df_columns = [col for col in df.columns if not str(col).strip().lower().startswith('unnamed:')]
        temp_subject_columns = [] # Use a temporary list for detection
        for col in cleaned_df_columns:
            col_lower = str(col).lower().strip()
            known_non_subject_names = [
                'name', 'class', 'total marks', 'aggregate al', 'weak subjects',
                'age', 'reg#', 'reg no', 'registration number', 'student id', 'index', 'index no',
                'grade summary', 'summary', 'remarks', 'level'
            ]
            if col_lower in known_non_subject_names:
                continue
            try: # Add try-except for numeric conversion robustness
                temp_series = pd.to_numeric(df[col], errors='coerce')
                numeric_ratio = temp_series.count() / len(df) if len(df) > 0 else 0
                if pd.api.types.is_numeric_dtype(temp_series) and \
                   numeric_ratio > 0.5 and \
                   not pd.api.types.is_bool_dtype(df[col].dtype): # Check original dtype for bool
                    temp_subject_columns.append(col)
            except Exception: # Catch any error during conversion/check for a column
                continue 
        
        subject_columns = [col for col in temp_subject_columns if 'total marks' not in col.lower()]


        if not subject_columns:
            st.warning("No subject mark columns detected. Ensure columns have numeric marks and are not in the exclusion list.")
            st.stop()

        for sub_col in subject_columns:
            if sub_col in df.columns:
                df[sub_col] = pd.to_numeric(df[sub_col], errors='coerce')

        for sub in subject_columns:
            if sub in df.columns:
                df[f"{sub}_AL"] = df.apply(lambda row: mark_to_al(sub, row[sub]), axis=1)

        mark_columns_for_total = [col for col in subject_columns if col in df.columns]
        if mark_columns_for_total:
            df['Total Marks'] = df[mark_columns_for_total].sum(axis=1, skipna=True)
        else:
            df['Total Marks'] = np.nan

        def calculate_aggregate_al(row):
            als_for_agg = []
            for sub in subject_columns:
                al_val = map_to_al_for_agg(sub, row.get(sub))
                if al_val is not None:
                    als_for_agg.append(al_val)
            if not als_for_agg: return None
            als_for_agg.sort()
            return sum(als_for_agg[:4])
        df['Aggregate AL'] = df.apply(calculate_aggregate_al, axis=1)

        if 'Class' in df.columns:
            df['Class'] = df['Class'].astype(str)
        else:
            st.error("The 'Class' column is missing. Please ensure your file has a column named 'Class'.")
            st.stop()

    except ValueError as e:
        st.error(f"❌ Error: {e}")
        st.stop()
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        st.stop()
else:
    st.info("Please upload an Excel or CSV file to begin.")
    st.stop()

if df.empty: # Should be caught by st.stop() earlier if processing failed
    st.warning("No data to process. Please upload a valid file.")
    st.stop()

# --- Sidebar Filters ---
st.sidebar.header("Filter Data")
all_classes = ['All Classes'] + sorted(df['Class'].unique().tolist())
selected_class = st.sidebar.multiselect("Select Class(es)", options=all_classes, default=['All Classes'])

filtered_df = df.copy() if 'All Classes' in selected_class else df[df['Class'].isin(selected_class)]

if not subject_columns: # Check again in case it was cleared or error before population
    st.error("Subject columns not identified. Cannot proceed with subject-specific analysis.")
    st.stop()

all_subjects = sorted(subject_columns)
selected_subject = st.sidebar.selectbox("Select Subject for Analysis", options=all_subjects)

if filtered_df.empty:
    st.warning("No data to display after applying class filters.")
    st.stop()

# --- Define Sort Order by Subject Type for charts ---
sort_order = []
if selected_subject: # Ensure selected_subject is not None
    if selected_subject.startswith("Fn "):
        sort_order = ['A', 'B', 'C']
    elif selected_subject in ['HCL', 'HML', 'HTL']:
        sort_order = ['Distinction', 'Merit', 'Pass', 'Ungraded']
    else:
        sort_order = ['AL1', 'AL2', 'AL3', 'AL4', 'AL5', 'AL6', 'AL7', 'AL8']

# --- Summary Insights ---
st.subheader("📊 Performance Summary")
total_students = len(filtered_df)
quantity_passes = 0
quality_passes = 0
selected_subject_al_col = f"{selected_subject}_AL"

if selected_subject_al_col in filtered_df.columns:
    subject_al_data = filtered_df[selected_subject_al_col].dropna()
    for al_score in subject_al_data:
        numeric_al = al_to_numeric(al_score) # Convert once for standard subjects
        if selected_subject.startswith("Fn "):
            if al_score in ['A', 'B']: quantity_passes += 1
            if al_score == 'A': quality_passes += 1
        elif selected_subject in ['HCL', 'HML', 'HTL']:
            if al_score in ['Distinction', 'Merit', 'Pass']: quantity_passes += 1
            if al_score == 'Distinction': quality_passes += 1
        else: # Standard Subjects
            if numeric_al is not None:
                if numeric_al <= 6: quantity_passes += 1
                if numeric_al <= 3: quality_passes += 1

col1, col2, col3 = st.columns(3)
if total_students > 0:
    with col1: st.metric("Total Students", total_students)
    with col2: st.metric(f"Quantity Passes ({selected_subject})", f"{quantity_passes} ({(quantity_passes/total_students*100 if total_students else 0):.1f}%)")
    with col3: st.metric(f"Quality Passes ({selected_subject})", f"{quality_passes} ({(quality_passes/total_students*100 if total_students else 0):.1f}%)")
else:
    st.info("No students for summary insights with current filters.")

st.markdown("---")
st.subheader(f"📋 Class Summary for {selected_subject}")
if selected_subject_al_col in filtered_df.columns:
    grouped_data = filtered_df.groupby('Class')[selected_subject_al_col].value_counts().unstack(fill_value=0)
    if not sort_order and not grouped_data.empty: # Fallback sort order if subject type unknown
        sort_order = sorted(grouped_data.columns.tolist(), key=al_to_numeric)

    grouped = grouped_data.reindex(columns=sort_order, fill_value=0)
    grouped['Total'] = grouped.sum(axis=1)
    for cat in sort_order:
        if cat in grouped.columns:
             grouped[f"{cat} (%)"] = (grouped[cat] / grouped['Total'].replace(0, np.nan) * 100).fillna(0).round(1)
        else:
             grouped[f"{cat} (%)"] = 0.0
    st.dataframe(grouped)
else:
    st.info(f"No AL data for '{selected_subject}' for class summary.")

st.markdown("---")
st.subheader(f"📈 {selected_subject} Performance Distribution")
col_chart1, col_chart2 = st.columns(2)

chart_data = pd.DataFrame()
if selected_subject_al_col in filtered_df.columns:
    chart_data = filtered_df.groupby(['Class', selected_subject_al_col]).size().reset_index(name='Count')
    if not chart_data.empty:
        chart_data.columns = ['Class', 'Category', 'Count']

with col_chart1:
    st.write("### Distribution by Class")
    if not chart_data.empty:
        alt_chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('Category:N', sort=sort_order, title="Category"),
            y=alt.Y('Count:Q', title="No. of Students"),
            color=alt.Color('Class:N', title='Class'),
            tooltip=['Class', 'Category', 'Count']
        ).properties(height=400, title=f"{selected_subject} Dist. by Class").interactive()
        st.altair_chart(alt_chart, use_container_width=True)
    else: st.info("No data for class distribution chart.")

pie_data = pd.DataFrame()
if selected_subject_al_col in filtered_df.columns:
    pie_data = filtered_df[selected_subject_al_col].value_counts().reset_index()
    if not pie_data.empty:
        pie_data.columns = ['Category', 'Count']
        pie_data['Category'] = pd.Categorical(pie_data['Category'], categories=sort_order, ordered=True)
        pie_data = pie_data.sort_values('Category').dropna(subset=['Category'])


with col_chart2:
    st.write("### Overall Breakdown")
    if not pie_data.empty:
        category_colors = {
            'AL1': '#003f5c', 'AL2': '#2f4b7c', 'AL3': '#416c99', 'AL4': '#5b8bb4',
            'AL5': '#77a7cf', 'AL6': '#a0c4e4', 'AL7': '#c8e0f9', 'AL8': '#eff6ff',
            'A': '#2ca02c', 'B': '#98df8a', 'C': '#ff7f0e',
            'Distinction': '#1f77b4', 'Merit': '#aec7e8', 'Pass': '#ffbb78', 'Ungraded': '#d62728'
        }
        fig = px.pie(pie_data, names='Category', values='Count', title=f"{selected_subject} Breakdown",
                     color='Category', color_discrete_map={cat: category_colors.get(cat, '#cccccc') for cat in pie_data['Category']})
        fig.update_layout(title_x=0.5)
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("No data for overall breakdown chart.")

st.markdown("---")
st.subheader("👤 Individual Student Performance")

def style_weak_subject_cells(row, all_subject_cols_original, al_converter_func):
    styles_for_row = [''] * len(row.index)
    als_numeric = []
    for s in all_subject_cols_original:
        al_col_name = f"{s}_AL"
        if al_col_name in row.index:
            al_val_str = row.get(al_col_name)
            al_val_num = al_converter_func(al_val_str)
            if al_val_num is not None: als_numeric.append(al_val_num)
    avg_al = np.mean(als_numeric) if als_numeric else None
    for i, col_name in enumerate(row.index):
        if col_name.endswith('_AL'):
            original_subject_name = col_name.replace('_AL', '')
            if original_subject_name in all_subject_cols_original:
                subject_al_val_str = row.get(col_name)
                numeric_subject_al = al_converter_func(subject_al_val_str)
                if numeric_subject_al is not None and avg_al is not None:
                    if (numeric_subject_al - avg_al) >= 2:
                        styles_for_row[i] = 'background-color: #ffcccc'
    return styles_for_row

if 'subject_columns' in globals() and subject_columns: # Check globals if defined outside a local scope
    filtered_df['Weak Subjects'] = filtered_df.apply(
        lambda r: count_student_weak_subjects(r, subject_columns, al_to_numeric), axis=1
    )
else:
    filtered_df['Weak Subjects'] = 0 # Default to 0 if no subjects

display_cols = ['Name', 'Class', 'Total Marks', 'Aggregate AL', 'Weak Subjects']
if 'subject_columns' in globals() and subject_columns:
    for s in subject_columns:
        al_col_name = f"{s}_AL"
        if al_col_name in filtered_df.columns: display_cols.append(al_col_name)

display_cols_present = [col for col in display_cols if col in filtered_df.columns]
sort_options_for_display = [col for col in ['Name', 'Total Marks', 'Aggregate AL', 'Weak Subjects'] if col in display_cols_present]

if not sort_options_for_display:
    if display_cols_present: st.dataframe(filtered_df[display_cols_present], use_container_width=True)
    else: st.info("No data or columns for individual student table.")
else:
    default_idx = sort_options_for_display.index('Name') if 'Name' in sort_options_for_display else 0
    sort_option = st.selectbox("Sort students by:", options=sort_options_for_display, index=default_idx)
    default_asc = True if sort_option == 'Name' else False
    ascending = st.checkbox("Sort ascending?", value=default_asc)
    sorted_df_display = filtered_df[display_cols_present].sort_values(by=sort_option, ascending=ascending)
    
    styler_params = {}
    if 'subject_columns' in globals() and subject_columns: # Ensure subject_columns is available for styler
        styler_params = {
            "all_subject_cols_original": subject_columns,
            "al_converter_func": al_to_numeric
        }
        st.dataframe(sorted_df_display.style.apply(style_weak_subject_cells, axis=1, **styler_params), use_container_width=True)
    else: # Display without styling if subject_columns isn't available
        st.dataframe(sorted_df_display, use_container_width=True)


st.sidebar.markdown("---")
st.sidebar.info("Dashboard v2.0")
