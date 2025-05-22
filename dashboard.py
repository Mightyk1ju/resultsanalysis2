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
        parser_func = lambda sheet_name, header_val: pd.read_csv(file, header=header_val)
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
    elif al in ['Ungraded']: return 4 # Ungraded is typically worse than a pass, but numerically better than AL8

    try:
        # For AL1 to AL8, extract the number
        return int(str(al).replace("AL", ""))
    except (ValueError, TypeError):
        return None # Handle cases like NaN, unexpected strings

def map_to_al_for_agg(subject, mark):
    """
    Converts a subject mark to a numeric AL score for aggregate calculation.
    This uses a simplified mapping where higher AL values (e.g., A=1, B=2, C=3)
    are treated as higher scores for aggregation (e.g., A=1, B=2, C=3).
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

# --- App Setup ---
st.set_page_config(page_title="Student Dashboard", layout="wide")
st.title("🎓 Student Performance Dashboard")

uploaded_file = st.file_uploader("Upload Excel or CSV file", type=["xlsx", "csv"])

df = pd.DataFrame() # Initialize df to avoid NameError if no file is uploaded
if uploaded_file:
    try:
        with st.spinner("Loading and processing data... This may take a moment."):
            df, sheet_used, header_row = load_and_clean_data(uploaded_file)
        st.success(f"✅ Successfully loaded data from {'sheet' if sheet_used != 'N/A' else 'file'} '{uploaded_file.name}' using header row {header_row + 1}.")

        # --- Data Preprocessing after successful upload ---
        # Automatically detect subject columns based on numeric content
        subject_columns = []
        # Filter out "Unnamed: X" columns immediately from the potential columns
        cleaned_df_columns = [col for col in df.columns if not str(col).strip().lower().startswith('unnamed:')]
        
        for col in cleaned_df_columns: # Iterate over the cleaned list of columns
            col_lower = str(col).lower().strip()
            # Exclude known non-subject columns
            if col_lower in ['name', 'class', 'total marks', 'aggregate al', 'weak subjects']:
                continue

            # Check if the column is primarily numeric (marks)
            temp_series = pd.to_numeric(df[col], errors='coerce')
            
            # A column is considered a potential subject column if:
            # 1. It's not a boolean column.
            # 2. It contains numeric data (after coercing errors to NaN).
            # 3. More than 50% of its values are non-NaN numeric. This helps distinguish mark columns from IDs or other mixed data.
            # 4. It's not entirely empty after numeric conversion.
            numeric_ratio = temp_series.count() / len(df) if len(df) > 0 else 0
            
            if pd.api.types.is_numeric_dtype(temp_series) and numeric_ratio > 0.5 and not pd.api.types.is_bool_dtype(df[col]):
                subject_columns.append(col)

        # Final filter: Remove "Total Marks" if it was somehow included by numeric detection
        subject_columns = [col for col in subject_columns if 'total marks' not in col.lower()]

        if not subject_columns:
            st.warning("No subject mark columns detected automatically. Please ensure your subject columns contain numeric values. If not, the current automatic detection may not work.")
            st.stop()

        # Explicitly convert subject columns to numeric to handle mixed types
        for sub_col in subject_columns:
            if sub_col in df.columns:
                df[sub_col] = pd.to_numeric(df[sub_col], errors='coerce')
            else:
                st.warning(f"Subject column '{sub_col}' was detected but not found in the DataFrame for numeric conversion. Skipping.")


        # Apply mark_to_al for each detected subject
        for sub in subject_columns:
            if sub in df.columns: # Ensure the column exists before attempting to apply
                df[f"{sub}_AL"] = df.apply(lambda row: mark_to_al(sub, row[sub]), axis=1)
            else:
                st.warning(f"Automatically detected subject column '{sub}' not found in the loaded data. It will be skipped.")


        # Calculate Total Marks (sum of all subject marks that were actually processed)
        mark_columns_for_total = [col for col in subject_columns if col in df.columns]
        if mark_columns_for_total:
            df['Total Marks'] = df[mark_columns_for_total].sum(axis=1, skipna=True)
        else:
            df['Total Marks'] = np.nan
            st.warning("No valid subject mark columns were processed to calculate 'Total Marks'.")


        # Calculate Aggregate AL (sum of best 4 standard + foundation ALs, excluding HMT)
        def calculate_aggregate_al(row):
            als_for_agg = []
            for sub in subject_columns:
                al_val = map_to_al_for_agg(sub, row.get(sub)) # Use .get to safely access column
                if al_val is not None:
                    als_for_agg.append(al_val)

            if not als_for_agg:
                return None

            # Sort and take the best 4 (lowest AL scores)
            als_for_agg.sort()
            best_4_als = als_for_agg[:4] # Take only the best 4 (lowest AL scores)

            return sum(best_4_als)

        df['Aggregate AL'] = df.apply(calculate_aggregate_al, axis=1)

        # Ensure 'Class' column is of string type for consistent filtering
        if 'Class' in df.columns:
            df['Class'] = df['Class'].astype(str)
        else:
            st.error("The 'Class' column is missing from your data. Please ensure your file has a column named 'Class'.")
            st.stop()


    except ValueError as e:
        st.error(f"❌ Error loading file: {e}")
        st.stop()
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        st.stop()
else:
    st.info("Please upload an Excel or CSV file to begin.")
    st.stop()

# Ensure df is not empty before proceeding with filters and charts
if df.empty:
    st.warning("No data to process. Please upload a valid Excel or CSV file.")
    st.stop()

# --- Sidebar Filters ---
st.sidebar.header("Filter Data")

all_classes = ['All Classes'] + sorted(df['Class'].unique().tolist())
selected_class = st.sidebar.multiselect("Select Class(es)", options=all_classes, default=['All Classes'])

if 'All Classes' in selected_class:
    filtered_df = df.copy()
else:
    filtered_df = df[df['Class'].isin(selected_class)]

# Check if subject_columns is available from the upload process
if 'subject_columns' not in locals() or not subject_columns:
    st.error("No subject columns were automatically detected. Please ensure your data contains numeric subject columns.")
    st.stop()

all_subjects = sorted(subject_columns)
selected_subject = st.sidebar.selectbox("Select Subject for Analysis", options=all_subjects)

if filtered_df.empty:
    st.warning("No data to display after applying class filters.")
    st.stop()

# --- Define Sort Order by Subject Type for charts ---
# This sort order is for AL categories (AL1, AL2, A, B, etc.)
sort_order = []
if selected_subject.startswith("Fn "):
    sort_order = ['A', 'B', 'C']
elif selected_subject in ['HCL', 'HML', 'HTL']:
    sort_order = ['Distinction', 'Merit', 'Pass', 'Ungraded']
else: # Standard Subjects
    sort_order = ['AL1', 'AL2', 'AL3', 'AL4', 'AL5', 'AL6', 'AL7', 'AL8']

# --- Summary Insights ---
st.subheader("📊 Performance Summary")
total_students = len(filtered_df)

# Placeholder for Quantity and Quality Passes - Define your own criteria
# Example: Quantity Pass = AL6 or better for standard, B or better for foundation, Pass or better for HMT
# Quality Pass = AL3 or better for standard, A for foundation, Distinction for HMT
quantity_passes = 0
quality_passes = 0

# Check if the selected subject's AL column exists in the filtered_df
selected_subject_al_col = f"{selected_subject}_AL"
if selected_subject_al_col in filtered_df.columns:
    subject_al_data = filtered_df[selected_subject_al_col].dropna()
    for al_score in subject_al_data:
        if selected_subject.startswith("Fn "):
            if al_score in ['A', 'B']: quantity_passes += 1
            if al_score == 'A': quality_passes += 1
        elif selected_subject in ['HCL', 'HML', 'HTL']:
            if al_score in ['Distinction', 'Merit', 'Pass']: quantity_passes += 1
            if al_score == 'Distinction': quality_passes += 1
        else: # Standard Subjects
            # Ensure al_score can be converted to numeric before comparison
            numeric_al = al_to_numeric(al_score)
            if numeric_al is not None:
                if numeric_al <= 6: quantity_passes += 1
                if numeric_al <= 3: quality_passes += 1

col1, col2, col3 = st.columns(3)

if total_students > 0:
    with col1:
        st.metric("Total Students", total_students)
    with col2:
        qty_pct = (quantity_passes / total_students) * 100
        st.metric(f"Quantity Passes ({selected_subject})", f"{quantity_passes} ({qty_pct:.1f}%)")
    with col3:
        qlt_pct = (quality_passes / total_students) * 100
        st.metric(f"Quality Passes ({selected_subject})", f"{qlt_pct:.1f}%)")
else:
    st.info("No students found matching the selected filters for summary insights.")

st.markdown("---")

# --- Class Summary Table ---
st.subheader(f"📋 Class Summary for {selected_subject}")

# Create a DataFrame for the class summary
# Group by 'Class' and count occurrences of each AL category for the selected subject
if selected_subject_al_col in filtered_df.columns:
    grouped_data = filtered_df.groupby('Class')[selected_subject_al_col].value_counts().unstack(fill_value=0)

    # Reindex to ensure all sort_order categories are present, even if empty
    grouped = grouped_data.reindex(columns=sort_order, fill_value=0)

    # Calculate totals and percentages
    grouped['Total'] = grouped.sum(axis=1)
    for cat in sort_order:
        # Ensure no division by zero if Total is 0
        grouped[f"{cat} (%)"] = (grouped[cat] / grouped['Total'] * 100).replace([np.inf, -np.inf], 0).round(1)

    # Display the summary table
    st.dataframe(grouped)
else:
    st.info(f"No AL data available for '{selected_subject}' to create class summary.")

st.markdown("---")

# --- Distribution Charts ---
st.subheader(f"📈 {selected_subject} Performance Distribution")

col_chart1, col_chart2 = st.columns(2)

# Prepare data for charts
# For Stacked Bar Chart (by Class)
if selected_subject_al_col in filtered_df.columns:
    chart_data = filtered_df.groupby(['Class', selected_subject_al_col]).size().reset_index(name='Count')
    chart_data.columns = ['Class', 'Category', 'Count'] # Rename for Altair
else:
    chart_data = pd.DataFrame() # Empty DataFrame if no data

with col_chart1:
    st.write("### Distribution by Class")
    if not chart_data.empty:
        x_axis = alt.X('Category:N', sort=sort_order, title="Category")
        y_axis = alt.Y('Count:Q', title="No. of Students")
        color = alt.Color('Class:N', title='Class')

        chart = alt.Chart(chart_data).mark_bar().encode(
            x=x_axis,
            y=y_axis,
            color=color,
            tooltip=['Class', 'Category', 'Count']
        ).properties(
            height=400,
            title=f"{selected_subject} Performance Distribution by Class"
        ).interactive() # Make chart interactive for zooming/panning
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No data for distribution by class for the selected subject.")

# For Pie Chart (Overall Breakdown)
if selected_subject_al_col in filtered_df.columns:
    pie_data = filtered_df[selected_subject_al_col].value_counts().reset_index()
    pie_data.columns = ['Category', 'Count'] # Rename for Plotly

    # Ensure sort_order for pie chart categories and colors
    pie_data['Category'] = pd.Categorical(pie_data['Category'], categories=sort_order, ordered=True)
    pie_data = pie_data.sort_values('Category').dropna() # Drop NaN categories if any
else:
    pie_data = pd.DataFrame() # Empty DataFrame if no data

if not pie_data.empty:
    with col_chart2:
        st.write("### Overall Breakdown")
        # Define a color palette based on sort_order and number of categories
        # You can customize these colors further
        # Use a consistent map of AL categories to colors
        category_colors = {
            'AL1': '#003f5c', 'AL2': '#2f4b7c', 'AL3': '#416c99', 'AL4': '#5b8bb4',
            'AL5': '#77a7cf', 'AL6': '#a0c4e4', 'AL7': '#c8e0f9', 'AL8': '#eff6ff',
            'A': '#2ca02c', 'B': '#98df8a', 'C': '#ff7f0e', # Green for A/B, Orange for C
            'Distinction': '#1f77b4', 'Merit': '#aec7e8', 'Pass': '#ffbb78', 'Ungraded': '#d62728' # Blue for HMT Dist/Merit, Orange for Pass, Red for Ungraded
        }
        # Filter colors to only those present in the current pie_data
        colors_for_pie = [category_colors.get(cat, '#cccccc') for cat in pie_data['Category']]

        fig = px.pie(
            pie_data,
            names='Category',
            values='Count',
            title=f"{selected_subject} Breakdown",
            color_discrete_sequence=colors_for_pie # Use the defined color sequence
        )
        fig.update_traces(marker=dict(colors=colors_for_pie), sort=False) # Ensure sorting is by defined order
        fig.update_layout(title_x=0.5) # Center the title
        st.plotly_chart(fig, use_container_width=True)
else:
    with col_chart2:
        st.info("No data for overall breakdown for the selected subject.")

st.markdown("---")

# --- Individual Student Table ---
st.subheader("👤 Individual Student Performance")

# Compute Weak Subjects count
def calculate_weak_subjects(row, all_subject_cols_original, al_converter_func):
    """
    Calculates the number of 'weak' subjects for a student.
    A subject is considered weak if its AL score is 2 or more points worse
    (higher numeric AL value) than the student's average AL score across all subjects.
    This function will be called by pandas styler.apply(axis=1), so 'row' will contain
    the data for the current row across all displayed columns.
    """
    # Initialize styles list for all columns in the current row
    styles_for_row = [''] * len(row.index)

    # Get all valid AL scores for the student from *all* original subject columns
    # This ensures avg_al is calculated across all subjects a student has taken,
    # not just the subset of AL columns that might be displayed or highlighted.
    als_numeric = []
    for s in all_subject_cols_original:
        al_col_name = f"{s}_AL"
        # Check if the AL column for this subject exists in the current row's data
        # (i.e., if it's one of the columns in sorted_df_display)
        if al_col_name in row.index:
            al_val = al_converter_func(row.get(al_col_name))
            if al_val is not None:
                als_numeric.append(al_val)

    avg_al = np.mean(als_numeric) if als_numeric else None

    # Now, iterate through each column in the `row` (which represents `sorted_df_display`'s columns)
    # and apply styles only to the relevant AL columns.
    for i, col_name in enumerate(row.index):
        if col_name.endswith('_AL'):
            original_subject_name = col_name.replace('_AL', '')
            
            # Ensure this is one of the originally selected subject columns
            if original_subject_name in all_subject_cols_original:
                subject_al_val = row.get(col_name) # Get the AL string value from the row
                numeric_subject_al = al_converter_func(subject_al_val) # Convert to numeric for comparison

                if numeric_subject_al is not None and avg_al is not None:
                    # Check for "weak" condition
                    if (numeric_subject_al - avg_al) >= 2:
                        styles_for_row[i] = 'background-color: #ffcccc' # Light red for weak subjects
        # All other columns (non-AL, or AL columns not matching original subjects) will remain with default '' style
    return styles_for_row


# Apply the weak subjects calculation
# Ensure 'subject_columns' is defined before applying
if 'subject_columns' in locals() and subject_columns:
    filtered_df['Weak Subjects'] = filtered_df.apply(
        lambda row: calculate_weak_subjects(
            row,
            all_subject_cols_original=subject_columns, # Pass the original list of all subject columns
            al_converter_func=al_to_numeric
        ),
        axis=1
    )
else:
    st.warning("Cannot calculate 'Weak Subjects': Subject columns not identified.")
    filtered_df['Weak Subjects'] = np.nan # Assign NaN or handle appropriately if no subject columns

# Dynamically create display columns
display_cols = ['Name', 'Class', 'Total Marks', 'Aggregate AL', 'Weak Subjects']
# Add AL columns for subjects that are actually present in the data and subject_columns list
# Ensure subject_columns is not empty before iterating
if 'subject_columns' in locals() and subject_columns:
    for s in subject_columns:
        al_col_name = f"{s}_AL"
        if al_col_name in filtered_df.columns:
            display_cols.append(al_col_name)

# Ensure all display_cols actually exist in filtered_df
display_cols_present = [col for col in display_cols if col in filtered_df.columns]

# Filter options for sorting, ensuring only valid columns are selectable
sort_options_for_display = [col for col in ['Name', 'Total Marks', 'Aggregate AL', 'Weak Subjects'] if col in display_cols_present]

if not sort_options_for_display:
    st.info("No numerical columns available for sorting individual student data.")
    # Display table without sorting if no sortable columns
    st.dataframe(filtered_df[display_cols_present], use_container_width=True)
else:
    sort_option = st.selectbox(
        "Sort students by:",
        options=sort_options_for_display,
        index=0 if 'Name' in sort_options_for_display else (
            (sort_options_for_display.index('Total Marks') if 'Total Marks' in sort_options_for_display else 0)
        )
    )
    ascending = st.checkbox("Sort ascending?", value=False) # Default descending for marks/AL (lower AL sum is better)

    # Apply sorting
    sorted_df_display = filtered_df[display_cols_present].sort_values(by=sort_option, ascending=ascending)

    st.dataframe(
        sorted_df_display.style.apply(
            calculate_weak_subjects, # Use the modified function directly
            axis=1,
            # Pass the original list of all subject columns for average AL calculation
            all_subject_cols_original=subject_columns,
            al_converter_func=al_to_numeric
        ),
        use_container_width=True
    )

st.sidebar.markdown("---")
st.sidebar.info("Dashboard developed using Streamlit, Pandas, Altair, and Plotly.")
