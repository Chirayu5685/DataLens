import os
import pandas as pd
import numpy as np
from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from analyzer.models import Dataset

def get_selected_dataset(request):
    """
    Returns the dataset selected by the current user.

    Priority:
    1. dataset GET parameter
    2. dataset stored in session
    3. no dataset

    Only datasets belonging to the logged-in user are allowed.
    """

    dataset_id = request.GET.get('dataset')

    if dataset_id:
        dataset = Dataset.objects.filter(
            id=dataset_id,
            user=request.user
        ).first()

        if dataset:
            request.session['dataset_id'] = dataset.id
            return dataset

    session_dataset_id = request.session.get('dataset_id')

    if session_dataset_id:
        dataset = Dataset.objects.filter(
            id=session_dataset_id,
            user=request.user
        ).first()

        if dataset:
            return dataset

        request.session.pop('dataset_id', None)

    return None
def home(request):
    return render(request, 'index.html')


def authentication(request):

    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':

        action = request.POST.get('action', 'login').strip()

        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        # =====================================================
        # LOGIN
        # =====================================================

        if action == 'login':

            if not email or not password:
                messages.error(
                    request,
                    'Please enter your email and password.'
                )
                return render(
                    request,
                    'authentication.html'
                )

            # Email is used as the Django username
            user = authenticate(
                request,
                username=email,
                password=password
            )

            if user is not None:

                login(request, user)

                messages.success(
                    request,
                    f'Welcome back, {user.first_name or user.username}!'
                )

                return redirect('dashboard')

            messages.error(
                request,
                'Invalid email or password.'
            )

            return render(
                request,
                'authentication.html'
            )

        # =====================================================
        # REGISTRATION
        # =====================================================

        elif action == 'register':

            fullname = request.POST.get(
                'fullname',
                ''
            ).strip()

            if not fullname:
                messages.error(
                    request,
                    'Please enter your full name.'
                )

                return render(
                    request,
                    'authentication.html'
                )

            if not email or not password:
                messages.error(
                    request,
                    'Email and password are required.'
                )

                return render(
                    request,
                    'authentication.html'
                )

            # Check whether email already exists
            if User.objects.filter(
                username=email
            ).exists():

                messages.error(
                    request,
                    'An account with this email already exists. '
                    'Please sign in.'
                )

                return render(
                    request,
                    'authentication.html'
                )

            # Split full name
            name_parts = fullname.split()

            first_name = name_parts[0]

            last_name = (
                ' '.join(name_parts[1:])
                if len(name_parts) > 1
                else ''
            )

            # Create Django user
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )

            # Automatically log the user in
            login(request, user)

            messages.success(
                request,
                'Your DataLens account has been created successfully.'
            )

            return redirect('dashboard')

    return render(
        request,
        'authentication.html'
    )
def logout_user(request):

    logout(request)

    messages.success(
        request,
        'You have been logged out successfully.'
    )

    return redirect('authentication')


@login_required(login_url='authentication')
def dashboard(request):
    datasets = Dataset.objects.filter(
        user=request.user
    ).order_by('-uploaded_at')

    total_datasets = datasets.count()

    total_rows = sum(
        dataset.rows for dataset in datasets
    )

    total_columns = sum(
        dataset.columns for dataset in datasets
    )

    total_storage = sum(
        dataset.file_size for dataset in datasets
    )

    latest_dataset = datasets.first()

    recent_datasets = datasets[:5]

    # ---------------------------------------------------------
    # RECORDS DISTRIBUTION
    # ---------------------------------------------------------

    records_distribution = []

    for dataset in datasets[:5]:
        records_distribution.append({
            'name': dataset.name,
            'rows': dataset.rows,
        })

    max_rows = max(
        [item['rows'] for item in records_distribution],
        default=0
    )

    for item in records_distribution:
        if max_rows > 0:
            item['percentage'] = round(
                (item['rows'] / max_rows) * 100
            )
        else:
            item['percentage'] = 0

    # ---------------------------------------------------------
    # DATA TYPE DISTRIBUTION
    # ---------------------------------------------------------

    data_types = {
        'Numeric': 0,
        'Categorical': 0,
        'DateTime': 0,
        'Boolean': 0,
    }

    for dataset in datasets:

        try:
            file_path = dataset.file.path

            if dataset.name.lower().endswith('.csv'):
                df_sample = pd.read_csv(
                    file_path,
                    nrows=1000
                )

            elif dataset.name.lower().endswith(
                ('.xlsx', '.xls')
            ):
                df_sample = pd.read_excel(
                    file_path,
                    nrows=1000
                )

            else:
                continue

            for column in df_sample.columns:

                series = df_sample[column]

                if pd.api.types.is_bool_dtype(series):
                    data_types['Boolean'] += 1

                elif pd.api.types.is_numeric_dtype(series):
                    data_types['Numeric'] += 1

                elif pd.api.types.is_datetime64_any_dtype(series):
                    data_types['DateTime'] += 1

                else:
                    # Try detecting datetime-like columns
                    converted = pd.to_datetime(
                        series,
                        errors='coerce'
                    )

                    if (
                        len(series) > 0
                        and converted.notna().mean() >= 0.8
                    ):
                        data_types['DateTime'] += 1
                    else:
                        data_types['Categorical'] += 1

        except Exception:
            continue

    total_data_type_fields = sum(data_types.values())

    data_type_percentages = {}

    for key, value in data_types.items():

        if total_data_type_fields > 0:
            data_type_percentages[key] = round(
                (value / total_data_type_fields) * 100
            )
        else:
            data_type_percentages[key] = 0

    # ---------------------------------------------------------
    # DATASET ACTIVITY — LAST 30 DAYS
    # ---------------------------------------------------------

    today = timezone.localdate()

    activity_map = defaultdict(int)

    for dataset in datasets:

        dataset_date = timezone.localtime(
            dataset.uploaded_at
        ).date()

        activity_map[dataset_date] += dataset.rows

    activity_labels = []
    activity_values = []

    for days_ago in range(29, -1, -1):

        current_date = today - timedelta(
            days=days_ago
            )

        activity_labels.append(
            current_date.strftime('%d %b')
        )

        activity_values.append(
            activity_map.get(current_date, 0)
        )

    # ---------------------------------------------------------
    # TOTAL PROCESSING VOLUME
    # ---------------------------------------------------------

    peak_rows = max(
        activity_values,
        default=0
    )

    return render(
        request,
        'dashboard.html',
        {
            'datasets': recent_datasets,

            'total_datasets': total_datasets,
            'total_rows': total_rows,
            'total_columns': total_columns,
            'total_storage': total_storage,
            'latest_dataset': latest_dataset,

            'records_distribution': records_distribution,

            'data_types': data_types,
            'data_type_percentages': data_type_percentages,
            'total_data_type_fields': total_data_type_fields,

            'activity_labels': activity_labels,
            'activity_values': activity_values,
            'peak_rows': peak_rows,
        }
    )

@login_required(login_url='authentication')
def upload_dataset(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('dataset')

        if not uploaded_file:
            messages.error(request, 'Please select a dataset file.')
            return render(request, 'upload.html')

        # Check file extension
        extension = os.path.splitext(uploaded_file.name)[1].lower()

        if extension not in ['.csv', '.xlsx', '.xls']:
            messages.error(
                request,
                'Unsupported file format. Please upload CSV or Excel files.'
            )
            return render(request, 'upload.html')

        try:
            # Save file
            fs = FileSystemStorage()
            filename = fs.save(
                f'datasets/{uploaded_file.name}',
                uploaded_file
            )

            file_path = fs.path(filename)

            # Read dataset using Pandas
            if extension == '.csv':
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)

            # Basic dataset information
            rows = len(df)
            columns = len(df.columns)
            file_size = uploaded_file.size

            # Save information to database
            dataset = Dataset.objects.create(
                user=request.user,
                name=uploaded_file.name,
                file=filename,
                rows=rows,
                columns=columns,
                file_size=file_size,
            )

            # Store latest dataset in session
            request.session['dataset_id'] = dataset.id

            messages.success(
                request,
                f'{uploaded_file.name} uploaded successfully.'
            )

            return redirect('dataset_preview')

        except Exception as e:
            messages.error(
                request,
                f'Unable to process the dataset: {str(e)}'
            )

            return render(request, 'upload.html')

    return render(request, 'upload.html')


@login_required(login_url='authentication')
def dataset_preview(request):

    from math import ceil

    dataset = get_selected_dataset(request)

    if not dataset:
        messages.warning(
            request,
            "Please upload a dataset first."
        )
        return redirect('upload_dataset')

    try:

        file_path = dataset.file.path
        extension = os.path.splitext(dataset.name)[1].lower()

        # --------------------------------------------------
        # READ DATASET
        # --------------------------------------------------

        if extension == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # --------------------------------------------------
        # BASIC DATASET INFORMATION
        # --------------------------------------------------

        total_rows = len(df)
        total_columns = len(df.columns)
        total_cells = total_rows * total_columns

        total_missing = int(
            df.isna().sum().sum()
        )

        duplicate_rows = int(
            df.duplicated().sum()
        )

        # --------------------------------------------------
        # DATA QUALITY
        # --------------------------------------------------

        if total_cells > 0:
            quality_score = round(
                (
                    (total_cells - total_missing)
                    / total_cells
                ) * 100,
                2
            )
        else:
            quality_score = 100

        # --------------------------------------------------
        # SEARCH
        # --------------------------------------------------

        search_query = request.GET.get(
            'q',
            ''
        ).strip()

        if search_query:

            search_mask = df.astype(str).apply(
                lambda column: column.str.contains(
                    search_query,
                    case=False,
                    na=False,
                    regex=False
                )
            ).any(axis=1)

            filtered_df = df[search_mask]

        else:
            filtered_df = df

        total_filtered_rows = len(filtered_df)

        # --------------------------------------------------
        # PAGINATION
        # --------------------------------------------------

        allowed_page_sizes = [
            25,
            50,
            100,
            250
        ]

        try:
            page_size = int(
                request.GET.get(
                    'page_size',
                    25
                )
            )
        except (ValueError, TypeError):
            page_size = 25

        if page_size not in allowed_page_sizes:
            page_size = 25

        try:
            page = int(
                request.GET.get(
                    'page',
                    1
                )
            )
        except (ValueError, TypeError):
            page = 1

        total_pages = max(
            1,
            ceil(
                total_filtered_rows
                / page_size
            )
        )

        page = max(
            1,
            min(
                page,
                total_pages
            )
        )

        start_index = (
            page - 1
        ) * page_size

        end_index = (
            start_index
            + page_size
        )

        preview_df = filtered_df.iloc[
            start_index:end_index
        ]

        # --------------------------------------------------
        # GLOBAL ROW NUMBER
        # --------------------------------------------------

        if total_filtered_rows == 0:
            row_start = 0
            row_end = 0
        else:
            row_start = start_index + 1
            row_end = min(
                end_index,
                total_filtered_rows
            )

        # --------------------------------------------------
        # PREVIEW TABLE
        # --------------------------------------------------

        columns = list(df.columns)

        preview_rows = (
            preview_df
            .fillna('')
            .astype(object)
            .values
            .tolist()
        )

        # --------------------------------------------------
        # COLUMN INFORMATION
        # --------------------------------------------------

        column_info = []

        for column in df.columns:

            series = df[column]

            is_numeric = pd.api.types.is_numeric_dtype(
                series
            )

            info = {
                'name': column,

                'dtype': str(
                    series.dtype
                ),

                'missing': int(
                    series.isna().sum()
                ),

                'unique': int(
                    series.nunique()
                ),

                'non_null': int(
                    series.notna().sum()
                ),

                'is_numeric': is_numeric,

                'min': None,
                'max': None,
                'mean': None,
                'median': None,
                'std': None,

                'missing_percentage': round(
                    (
                        series.isna().sum()
                        / len(series)
                    ) * 100,
                    2
                ) if len(series) > 0 else 0,

                # Distribution information
                'distribution': [],
                'distribution_min': None,
                'distribution_max': None,
                'distribution_type': 'No numeric distribution',
            }

            # --------------------------------------------------
            # NUMERIC STATISTICS
            # --------------------------------------------------

            if is_numeric:

                clean_series = (
                    pd.to_numeric(
                        series,
                        errors='coerce'
                    )
                    .dropna()
                )

                if not clean_series.empty:

                    info['min'] = round(
                        float(
                            clean_series.min()
                        ),
                        2
                    )

                    info['max'] = round(
                        float(
                            clean_series.max()
                        ),
                        2
                    )

                    info['mean'] = round(
                        float(
                            clean_series.mean()
                        ),
                        2
                    )

                    info['median'] = round(
                        float(
                            clean_series.median()
                        ),
                        2
                    )

                    info['std'] = round(
                        float(
                            clean_series.std()
                        ),
                        2
                    )

                    # --------------------------------------------------
                    # REAL HISTOGRAM DISTRIBUTION
                    # --------------------------------------------------

                    if len(clean_series) >= 2:

                        try:

                            histogram, bin_edges = np.histogram(
                                clean_series,
                                bins=10
                            )

                            distribution = []

                            max_count = (
                                int(histogram.max())
                                if len(histogram) > 0
                                else 0
                            )

                            for index in range(len(histogram)):

                                count = int(histogram[index])

                                height_percentage = (
                                    round(
                                        (count / max_count) * 100,
                                        2
                                    )
                                    if max_count > 0
                                    else 0
                                )

                                distribution.append({
                                    'start': round(
                                        float(bin_edges[index]),
                                        2
                                    ),

                                    'end': round(
                                        float(bin_edges[index + 1]),
                                        2
                                    ),

                                    'count': count,

                                    'height': height_percentage,
                                })

                                info['distribution'] = distribution

                                info['distribution_min'] = round(
                                    float(
                                        bin_edges[0]
                                    ),
                                    2
                                )

                                info['distribution_max'] = round(
                                    float(
                                        bin_edges[-1]
                                    ),
                                    2
                                )

                                # Simple distribution description
                                if clean_series.nunique() <= 1:
                                    info['distribution_type'] = (
                                        'Constant Distribution'
                                    )

                                elif clean_series.skew() > 1:
                                    info['distribution_type'] = (
                                        'Right-Skewed Distribution'
                                    )

                                elif clean_series.skew() < -1:
                                    info['distribution_type'] = (
                                        'Left-Skewed Distribution'
                                    )

                                else:
                                    info['distribution_type'] = (
                                        'Approximately Symmetric'
                                    )
                        except Exception:
                            pass

            column_info.append(info)

        # --------------------------------------------------
        # SELECTED COLUMN
        # --------------------------------------------------

        selected_column_name = request.GET.get(
            'column'
        )

        selected_column = None

        if selected_column_name:

            for info in column_info:

                if info['name'] == selected_column_name:

                    selected_column = info

                    break

        # --------------------------------------------------
        # DEFAULT COLUMN
        # --------------------------------------------------

        if (
            selected_column is None
            and column_info
        ):
            selected_column = column_info[0]

        # --------------------------------------------------
        # COLUMN COUNTS
        # --------------------------------------------------

        numeric_count = sum(
            1
            for info in column_info
            if info['is_numeric']
        )

        categorical_count = (
            total_columns
            - numeric_count
        )

        # --------------------------------------------------
        # PAGE NUMBERS
        # --------------------------------------------------

        page_numbers = list(
            range(
                max(
                    1,
                    page - 2
                ),
                min(
                    total_pages,
                    page + 2
                ) + 1
            )
        )

        # --------------------------------------------------
        # CONTEXT
        # --------------------------------------------------

        context = {

            'dataset': dataset,

            'total_rows':
                total_rows,

            'total_columns':
                total_columns,

            'total_cells':
                total_cells,

            'total_missing':
                total_missing,

            'duplicate_rows':
                duplicate_rows,

            'quality_score':
                quality_score,

            'numeric_count':
                numeric_count,

            'categorical_count':
                categorical_count,

            'columns':
                columns,

            'preview_rows':
                preview_rows,

            'column_info':
                column_info,

            'selected_column':
                selected_column,

            'file_size_mb': round(
                dataset.file_size
                / (1024 * 1024),
                2
            ),

            'search_query':
                search_query,

            'page':
                page,

            'page_size':
                page_size,

            'total_pages':
                total_pages,

            'page_numbers':
                page_numbers,

            'total_filtered_rows':
                total_filtered_rows,

            'row_start':
                row_start,

            'row_end':
                row_end,
        }

        return render(
            request,
            'dataset_preview.html',
            context
        )

    except Dataset.DoesNotExist:

        messages.error(
            request,
            'Dataset not found.'
        )

        return redirect(
            'upload_dataset'
        )

    except Exception as e:

        messages.error(
            request,
            f'Unable to preview dataset: {str(e)}'
        )

        return redirect(
            'upload_dataset'
        )  
@login_required(login_url='authentication')
def analysis(request):

    dataset = get_selected_dataset(request)

    if not dataset:
        messages.warning(
            request,
            "Please upload a dataset first."
        )
        return redirect('upload_dataset')

    try:

        file_path = dataset.file.path
        extension = os.path.splitext(dataset.name)[1].lower()

        # Read dataset
        if extension == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Basic statistics
        total_rows = len(df)
        total_columns = len(df.columns)
        total_cells = total_rows * total_columns

        # Missing values
        total_missing = int(df.isna().sum().sum())

        # Duplicate rows
        duplicate_rows = int(df.duplicated().sum())

        # Numeric and categorical columns
        numeric_columns = df.select_dtypes(
            include='number'
        ).columns.tolist()

        categorical_columns = df.select_dtypes(
            exclude='number'
        ).columns.tolist()

        # Data quality percentage
        if total_cells > 0:
            quality_score = round(
                ((total_cells - total_missing) / total_cells) * 100,
                2
            )
        else:
            quality_score = 100

        # Column statistics
        analysis_columns = []

        for column in df.columns:

            series = df[column]
            info = {
                    'name': column,
                        'dtype': str(series.dtype),
                        'missing': int(series.isna().sum()),
                        'unique': int(series.nunique()),
                        'non_null': int(series.notna().sum()),
                        'is_numeric': pd.api.types.is_numeric_dtype(series),
                    }

            if pd.api.types.is_numeric_dtype(series):

                clean = series.dropna()

                if not clean.empty:
                    info.update({
                        'min': round(float(clean.min()), 2),
                        'max': round(float(clean.max()), 2),
                        'mean': round(float(clean.mean()), 2),
                        'median': round(float(clean.median()), 2),
                        'std': round(float(clean.std()), 2),
                    })
                else:
                    info.update({
                        'min': None,
                        'max': None,
                        'mean': None,
                        'median': None,
                        'std': None,
                    })

            analysis_columns.append(info)

        context = {
            'dataset': dataset,

            'total_rows': total_rows,
            'total_columns': total_columns,
            'total_cells': total_cells,

            'total_missing': total_missing,
            'duplicate_rows': duplicate_rows,

            'numeric_count': len(numeric_columns),
            'categorical_count': len(categorical_columns),

            'quality_score': quality_score,

            'numeric_columns': numeric_columns,
            'categorical_columns': categorical_columns,

            'analysis_columns': analysis_columns,
        }

        return render(
            request,
            'analysis.html',
            context
        )

    except Dataset.DoesNotExist:
        messages.error(request, 'Dataset not found.')
        return redirect('upload_dataset')

    except Exception as e:
        messages.error(
            request,
            f'Unable to analyze dataset: {str(e)}'
        )
        return redirect('dataset_preview')

@login_required(login_url='authentication')
def visualizations(request):

    dataset = get_selected_dataset(request)

    if not dataset:
        messages.warning(
            request,
            "Please upload a dataset first."
        )
        return redirect('upload_dataset')

    try:

        file_path = dataset.file.path
        extension = os.path.splitext(dataset.name)[1].lower()

        if extension == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        numeric_columns = df.select_dtypes(include='number').columns.tolist()
        categorical_columns = df.select_dtypes(exclude='number').columns.tolist()

        context = {
            'dataset': dataset,
            'numeric_columns': numeric_columns,
            'categorical_columns': categorical_columns,
            'total_rows': len(df),
            'total_columns': len(df.columns),
        }

        return render(request, 'visualizations.html', context)

    except Dataset.DoesNotExist:
        messages.error(request, 'Dataset not found.')
        return redirect('upload_dataset')

    except Exception as e:
        messages.error(
            request,
            f'Unable to load visualization data: {str(e)}'
        )
        return redirect('dataset_preview')

@login_required(login_url='authentication')
def visualization_data(request):
    """
    API endpoint used by the Visualizations page.

    Returns:
    - X/Y column names
    - whether X/Y are numeric
    - chart labels and values
    - Pearson correlation
    - R²
    - valid data points
    """

    dataset_id = request.session.get("dataset_id")

    if not dataset_id:
        return JsonResponse(
            {"error": "No dataset selected."},
            status=400
        )

    try:
        dataset = Dataset.objects.get(
            id=dataset_id,
            user=request.user
        )
    except Dataset.DoesNotExist:
        request.session.pop("dataset_id", None)
        return JsonResponse(
                {"error": "Dataset not found."},
                    status=404
                )

    x_column = request.GET.get("x", "").strip()
    y_column = request.GET.get("y", "").strip()

    if not x_column or not y_column:
        return JsonResponse(
            {"error": "Both X and Y columns are required."},
            status=400
        )

    try:
        # --------------------------------------------------
        # READ DATASET
        # --------------------------------------------------

        file_path = dataset.file.path
        extension = os.path.splitext(file_path)[1].lower()

        if extension == ".csv":
            df = pd.read_csv(file_path)

        elif extension in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)

        else:
            return JsonResponse(
                {"error": "Unsupported dataset format."},
                status=400
            )

        # --------------------------------------------------
        # VALIDATE COLUMNS
        # --------------------------------------------------

        if x_column not in df.columns:
            return JsonResponse(
                {"error": f"X column '{x_column}' was not found."},
                status=400
            )

        if y_column not in df.columns:
            return JsonResponse(
                {"error": f"Y column '{y_column}' was not found."},
                status=400
            )

        # --------------------------------------------------
        # DETERMINE COLUMN TYPES
        # --------------------------------------------------

        x_series = df[x_column]
        y_series = df[y_column]

        x_is_numeric = pd.api.types.is_numeric_dtype(x_series)
        y_is_numeric = pd.api.types.is_numeric_dtype(y_series)

        # --------------------------------------------------
        # PREPARE X LABELS
        # --------------------------------------------------

        labels_series = x_series.copy()

        # Convert datetime values into readable strings
        if pd.api.types.is_datetime64_any_dtype(labels_series):
            labels_series = labels_series.dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        else:
            labels_series = labels_series.astype(str)

        labels_series = labels_series.replace(
            ["nan", "NaT", "None"],
            ""
        )

        labels = labels_series.tolist()

        # --------------------------------------------------
        # PREPARE Y VALUES
        # --------------------------------------------------

        y_numeric = pd.to_numeric(
            y_series,
            errors="coerce"
        )

        values = []

        for value in y_numeric:
            if pd.isna(value):
                values.append(None)
            else:
                values.append(float(value))

        # --------------------------------------------------
        # LIMIT DATA SENT TO CHART
        # --------------------------------------------------

        max_points = 100

        if len(labels) > max_points:
            labels = labels[:max_points]
            values = values[:max_points]

        # --------------------------------------------------
        # CORRELATION / R²
        # --------------------------------------------------

        correlation = None
        r_squared = None
        valid_points = 0

        # Correlation requires numeric X and Y
        if x_is_numeric and y_is_numeric:

            x_numeric = pd.to_numeric(
                x_series,
                errors="coerce"
            )

            y_numeric_full = pd.to_numeric(
                y_series,
                errors="coerce"
            )

            valid_mask = (
                x_numeric.notna()
                & y_numeric_full.notna()
            )

            valid_x = x_numeric[valid_mask]
            valid_y = y_numeric_full[valid_mask]

            valid_points = int(len(valid_x))

            # At least 2 points are required
            if valid_points >= 2:

                # Avoid correlation problems with constant columns
                if (
                    valid_x.nunique() > 1
                    and valid_y.nunique() > 1
                ):

                    correlation_value = (
                        valid_x.corr(valid_y)
                    )

                    if pd.notna(correlation_value):
                        correlation = float(
                            correlation_value
                        )

                        r_squared = float(
                            correlation ** 2
                        )

        else:
            # Count valid Y observations
            valid_points = int(
                y_numeric.notna().sum()
            )

        # --------------------------------------------------
        # RESPONSE
        # --------------------------------------------------

        response_data = {
            "dataset_name": dataset.name,

            "x_column": x_column,
            "y_column": y_column,

            "x_is_numeric": bool(x_is_numeric),
            "y_is_numeric": bool(y_is_numeric),

            "labels": labels,
            "values": values,

            "correlation": correlation,
            "r_squared": r_squared,

            # p-value will be implemented later with SciPy
            "p_value": None,

            "valid_points": valid_points,

            "total_rows": int(len(df)),
            "total_columns": int(len(df.columns)),
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse(
            {
                "error": f"Unable to generate visualization data: {str(e)}"
            },
            status=500
        )
@login_required(login_url='authentication')
def insights(request):

    dataset = get_selected_dataset(request)

    if not dataset:
        messages.warning(
            request,
            "Please upload a dataset first."
        )
        return redirect('upload_dataset')

    try:

        file_path = dataset.file.path
        extension = os.path.splitext(dataset.name)[1].lower()

        # --------------------------------------------------
        # READ DATASET
        # --------------------------------------------------

        if extension == '.csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # --------------------------------------------------
        # BASIC INFORMATION
        # --------------------------------------------------

        total_rows = len(df)
        total_columns = len(df.columns)
        total_cells = total_rows * total_columns

        total_missing = int(
            df.isna().sum().sum()
        )

        duplicate_rows = int(
            df.duplicated().sum()
        )

        # --------------------------------------------------
        # DATA QUALITY
        # --------------------------------------------------

        if total_cells > 0:
            quality_score = round(
                (
                    (total_cells - total_missing)
                    / total_cells
                ) * 100,
                2
            )
        else:
            quality_score = 100

        # --------------------------------------------------
        # COLUMN TYPES
        # --------------------------------------------------

        numeric_columns = df.select_dtypes(
            include='number'
        ).columns.tolist()

        categorical_columns = df.select_dtypes(
            exclude='number'
        ).columns.tolist()

        # --------------------------------------------------
        # NUMERIC INSIGHTS
        # --------------------------------------------------

        numeric_insights = []

        for column in numeric_columns:

            series = pd.to_numeric(
                df[column],
                errors='coerce'
            ).dropna()

            if series.empty:
                continue

            numeric_insights.append({
                'name': column,
                'min': round(float(series.min()), 2),
                'max': round(float(series.max()), 2),
                'mean': round(float(series.mean()), 2),
                'median': round(float(series.median()), 2),
                'std': round(float(series.std()), 2),
                'missing': int(df[column].isna().sum()),
                'unique': int(df[column].nunique()),
            })

        # --------------------------------------------------
        # CATEGORICAL INSIGHTS
        # --------------------------------------------------

        categorical_insights = []

        for column in categorical_columns:

            series = df[column]

            value_counts = (
                series
                .dropna()
                .astype(str)
                .value_counts()
            )

            top_value = None
            top_count = 0

            if not value_counts.empty:
                top_value = str(value_counts.index[0])
                top_count = int(value_counts.iloc[0])

            categorical_insights.append({
                'name': column,
                'unique': int(series.nunique()),
                'missing': int(series.isna().sum()),
                'top_value': top_value,
                'top_count': top_count,
            })

        # --------------------------------------------------
        # MISSING VALUE INSIGHTS
        # --------------------------------------------------

        missing_columns = []

        for column in df.columns:

            missing_count = int(
                df[column].isna().sum()
            )

            if missing_count > 0:

                missing_percentage = round(
                    (missing_count / total_rows) * 100,
                    2
                ) if total_rows > 0 else 0

                missing_columns.append({
                    'name': column,
                    'count': missing_count,
                    'percentage': missing_percentage,
                })

        # Highest missing column first
        missing_columns.sort(
            key=lambda item: item['percentage'],
            reverse=True
        )
                # --------------------------------------------------
        # TOP CATEGORICAL INSIGHTS
        # --------------------------------------------------

        top_categories = []

        for item in categorical_insights:

            if item['top_value'] is None:
                continue

            percentage = round(
                (item['top_count'] / total_rows) * 100,
                2
            ) if total_rows > 0 else 0

            top_categories.append({
                'name': item['name'],
                'value': item['top_value'],
                'count': item['top_count'],
                'percentage': percentage,
                'unique': item['unique'],
            })

        top_categories.sort(
            key=lambda item: item['percentage'],
            reverse=True
        )

        # --------------------------------------------------
        # NUMERIC CORRELATIONS
        # --------------------------------------------------

        correlations = []

        if len(numeric_columns) >= 2:

            correlation_matrix = df[numeric_columns].corr()

            for i in range(len(numeric_columns)):

                for j in range(i + 1, len(numeric_columns)):

                    column_x = numeric_columns[i]
                    column_y = numeric_columns[j]

                    correlation_value = correlation_matrix.loc[
                        column_x,
                        column_y
                    ]

                    if pd.notna(correlation_value):

                        correlations.append({
                            'x': column_x,
                            'y': column_y,
                            'value': round(
                                float(correlation_value),
                                3
                            ),
                            'strength': abs(
                                float(correlation_value)
                            ),
                        })

        correlations.sort(
            key=lambda item: item['strength'],
            reverse=True
        )

        # --------------------------------------------------
        # OUTLIER INSIGHTS
        # --------------------------------------------------

        outlier_insights = []

        for column in numeric_columns:

            series = pd.to_numeric(
                df[column],
                errors='coerce'
            ).dropna()

            if len(series) < 4:
                continue

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)

            iqr = q3 - q1

            if iqr == 0:

                outlier_count = 0

            else:

                lower_bound = q1 - (1.5 * iqr)
                upper_bound = q3 + (1.5 * iqr)

                outlier_count = int(
                    (
                        (series < lower_bound)
                        | (series > upper_bound)
                    ).sum()
                )

            outlier_percentage = round(
                (outlier_count / len(series)) * 100,
                2
            )

            outlier_insights.append({
                'name': column,
                'count': outlier_count,
                'percentage': outlier_percentage,
            })

        outlier_insights.sort(
            key=lambda item: item['count'],
            reverse=True
        )


        # --------------------------------------------------
        # AUTOMATIC RECOMMENDATIONS
        # --------------------------------------------------

        recommendations = []

        if total_missing > 0:
            recommendations.append({
                'type': 'warning',
                'title': 'Missing values detected',
                'message': (
                    f'{total_missing} missing values were found '
                    'in the dataset. Consider cleaning or '
                    'imputing these values.'
                ),
                'icon': 'warning'
            })

        else:
            recommendations.append({
                'type': 'success',
                'title': 'No missing values',
                'message': (
                    'The dataset does not contain missing values.'
                ),
                'icon': 'check_circle'
            })

        if duplicate_rows > 0:
            recommendations.append({
                'type': 'warning',
                'title': 'Duplicate rows detected',
                'message': (
                    f'{duplicate_rows} duplicate rows were found. '
                    'Review them before further analysis.'
                ),
                'icon': 'content_copy'
            })

        else:
            recommendations.append({
                'type': 'success',
                'title': 'No duplicate rows',
                'message': (
                    'No duplicate rows were detected '
                    'in the dataset.'
                ),
                'icon': 'verified'
            })

        if quality_score >= 95:
            quality_message = (
                'Excellent dataset quality. '
                'The dataset is ready for analysis.'
            )

        elif quality_score >= 85:
            quality_message = (
                'Good dataset quality, but some cleaning '
                'may improve the results.'
            )

        elif quality_score >= 70:
            quality_message = (
                'Moderate dataset quality. '
                'Data cleaning is recommended before analysis.'
            )

        else:
            quality_message = (
                'The dataset requires significant cleaning '
                'before reliable analysis.'
            )

        recommendations.append({
            'type': 'info',
            'title': 'Data quality assessment',
            'message': quality_message,
            'icon': 'analytics'
        })

        # --------------------------------------------------
        # LARGEST NUMERIC RANGE
        # --------------------------------------------------

        highest_range_column = None
        highest_range = None

        for item in numeric_insights:

            current_range = item['max'] - item['min']

            if (
                highest_range is None
                or current_range > highest_range
            ):
                highest_range = current_range
                highest_range_column = item['name']

        # --------------------------------------------------
        # CONTEXT
        # --------------------------------------------------

        context = {
            'dataset': dataset,

            'total_rows': total_rows,
            'total_columns': total_columns,
            'total_cells': total_cells,

            'total_missing': total_missing,
            'duplicate_rows': duplicate_rows,

            'quality_score': quality_score,

            'numeric_count': len(numeric_columns),
            'categorical_count': len(categorical_columns),

            'numeric_columns': numeric_columns,
            'categorical_columns': categorical_columns,

            'numeric_insights': numeric_insights,

            'categorical_insights': categorical_insights,

            'missing_columns': missing_columns,

            'top_categories': top_categories,

            'correlations': correlations,

            'outlier_insights': outlier_insights,

            'recommendations': recommendations,
            'highest_range_column': highest_range_column,
            'highest_range': (
                round(highest_range, 2)
                if highest_range is not None
                else None
            ),
        }

        return render(
            request,
            'insights.html',
            context
        )

    except Dataset.DoesNotExist:

        messages.error(
            request,
            'Dataset not found.'
        )

        return redirect('upload_dataset')

    except Exception as e:

        messages.error(
            request,
            f'Unable to generate insights: {str(e)}'
        )

        return redirect('dataset_preview')


@login_required(login_url='authentication')
def history(request):
    datasets = Dataset.objects.filter(
        user=request.user
    ).order_by('-uploaded_at')

    return render(
        request,
        'history.html',
        {
            'datasets': datasets,
        }
    )

@login_required(login_url='authentication')
def reports(request):

    dataset = get_selected_dataset(request)

    if not dataset:
        messages.warning(
            request,
            "Please upload a dataset first."
        )
        return redirect('upload_dataset')

    try:

        # Read dataset
        file_path = dataset.file.path

        if dataset.name.lower().endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # -----------------------------
        # Basic Dataset Statistics
        # -----------------------------
        total_rows = len(df)
        total_columns = len(df.columns)
        total_cells = total_rows * total_columns

        total_missing = int(df.isna().sum().sum())
        duplicate_rows = int(df.duplicated().sum())

        # -----------------------------
        # Data Quality Score
        # -----------------------------
        if total_cells > 0:
            missing_percentage = (total_missing / total_cells) * 100
            duplicate_percentage = (
                (duplicate_rows / total_rows) * 100
                if total_rows > 0 else 0
            )

            quality_score = max(
                0,
                round(
                    100
                    - missing_percentage
                    - (duplicate_percentage * 0.5),
                    1
                )
            )
        else:
            quality_score = 0

        # -----------------------------
        # Column Types
        # -----------------------------
        numeric_columns = df.select_dtypes(
            include=np.number
        ).columns.tolist()

        categorical_columns = [
            column for column in df.columns
            if column not in numeric_columns
        ]

        # -----------------------------
        # Numeric Analysis
        # -----------------------------
        numeric_insights = []

        for column in numeric_columns:
            series = pd.to_numeric(
                df[column],
                errors='coerce'
            )

            numeric_insights.append({
                'name': column,
                'min': round(float(series.min()), 2)
                    if series.notna().any() else None,
                'max': round(float(series.max()), 2)
                    if series.notna().any() else None,
                'mean': round(float(series.mean()), 2)
                    if series.notna().any() else None,
                'median': round(float(series.median()), 2)
                    if series.notna().any() else None,
                'std': round(float(series.std()), 2)
                    if series.notna().sum() > 1 else None,
                'missing': int(series.isna().sum()),
                'unique': int(series.nunique(dropna=True)),
            })

        # -----------------------------
        # Categorical Analysis
        # -----------------------------
        categorical_insights = []

        for column in categorical_columns:
            series = df[column]

            value_counts = series.value_counts(
                dropna=True
            )

            top_value = (
                str(value_counts.index[0])
                if len(value_counts) > 0
                else "N/A"
            )

            top_count = (
                int(value_counts.iloc[0])
                if len(value_counts) > 0
                else 0
            )

            categorical_insights.append({
                'name': column,
                'unique': int(series.nunique(dropna=True)),
                'missing': int(series.isna().sum()),
                'top_value': top_value,
                'top_count': top_count,
            })

        # -----------------------------
        # Missing Value Analysis
        # -----------------------------
        missing_columns = []

        for column in df.columns:
            missing_count = int(df[column].isna().sum())

            if total_rows > 0:
                percentage = round(
                    (missing_count / total_rows) * 100,
                    2
                )
            else:
                percentage = 0

            missing_columns.append({
                'name': column,
                'missing': missing_count,
                'percentage': percentage,
            })

        missing_columns.sort(
            key=lambda item: item['percentage'],
            reverse=True
        )

        # -----------------------------
        # Top Categories
        # -----------------------------
        top_categories = []

        for column in categorical_columns:
            counts = df[column].value_counts(
                dropna=True
            ).head(5)

            for value, count in counts.items():
                percentage = round(
                    (int(count) / total_rows) * 100,
                    2
                ) if total_rows > 0 else 0

                top_categories.append({
                    'column': column,
                    'value': str(value),
                    'count': int(count),
                    'percentage': percentage,
                })

        top_categories.sort(
            key=lambda item: item['percentage'],
            reverse=True
        )

        top_categories = top_categories[:10]

        # -----------------------------
        # Correlation Analysis
        # -----------------------------
        correlations = []

        if len(numeric_columns) >= 2:
            correlation_matrix = df[numeric_columns].corr()

            for i, column_a in enumerate(numeric_columns):
                for j, column_b in enumerate(numeric_columns):

                    if j <= i:
                        continue

                    value = correlation_matrix.loc[
                        column_a,
                        column_b
                    ]

                    if pd.notna(value):
                        correlations.append({
                            'column_a': column_a,
                            'column_b': column_b,
                            'value': round(float(value), 3),
                            'absolute': abs(float(value)),
                        })

        correlations.sort(
            key=lambda item: item['absolute'],
            reverse=True
        )

        correlations = correlations[:10]

        # -----------------------------
        # Outlier Detection
        # -----------------------------
        outlier_insights = []

        for column in numeric_columns:

            series = pd.to_numeric(
                df[column],
                errors='coerce'
            ).dropna()

            if len(series) < 4:
                continue

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)

            iqr = q3 - q1

            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            outliers = series[
                (series < lower_bound)
                | (series > upper_bound)
            ]

            outlier_count = len(outliers)

            percentage = round(
                (outlier_count / len(series)) * 100,
                2
            )

            outlier_insights.append({
                'name': column,
                'outliers': int(outlier_count),
                'percentage': percentage,
                'lower_bound': round(
                    float(lower_bound), 2
                ),
                'upper_bound': round(
                    float(upper_bound), 2
                ),
            })

        outlier_insights.sort(
            key=lambda item: item['outliers'],
            reverse=True
        )

        # -----------------------------
        # Recommendations
        # -----------------------------
        recommendations = []

        if total_missing > 0:
            recommendations.append(
                "Review columns containing missing values "
                "before performing further analysis."
            )

        if duplicate_rows > 0:
            recommendations.append(
                "Consider checking duplicate rows to improve "
                "dataset consistency."
            )

        if quality_score >= 90:
            recommendations.append(
                "The dataset has a strong overall data quality score."
            )
        elif quality_score >= 70:
            recommendations.append(
                "The dataset has moderate quality and may benefit "
                "from some cleaning."
            )
        else:
            recommendations.append(
                "The dataset requires additional data cleaning "
                "before advanced analysis."
            )

        if len(numeric_columns) >= 2:
            recommendations.append(
                "Correlation analysis can be used to investigate "
                "relationships between numeric variables."
            )

        if not recommendations:
            recommendations.append(
                "No major data-quality recommendations were generated."
            )

        # -----------------------------
        # Final Context
        # -----------------------------
        context = {
            'dataset': dataset,

            'total_rows': total_rows,
            'total_columns': total_columns,
            'total_cells': total_cells,

            'total_missing': total_missing,
            'duplicate_rows': duplicate_rows,
            'quality_score': quality_score,

            'numeric_columns': numeric_columns,
            'categorical_columns': categorical_columns,

            'numeric_insights': numeric_insights,
            'categorical_insights': categorical_insights,

            'missing_columns': missing_columns,
            'top_categories': top_categories,

            'correlations': correlations,
            'outlier_insights': outlier_insights,

            'recommendations': recommendations,
        }

        return render(
            request,
            'reports.html',
            context
        )

    except Exception as e:
        messages.error(
            request,
            f"Unable to generate report: {str(e)}"
        )
        return redirect('dashboard')


def loading(request):
    return render(request, 'loading.html')


def empty(request):
    return render(request, 'empty.html')


def error(request):
    return render(request, 'error.html')