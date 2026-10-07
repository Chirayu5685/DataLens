from django.shortcuts import render, redirect
from django.core.files.storage import FileSystemStorage


def home(request):
    return render(request, 'index.html')


def authentication(request):
    return render(request, 'authentication.html')


def dashboard(request):
    return render(request, 'dashboard.html')


def upload_dataset(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('dataset')

        if uploaded_file:
            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)

            request.session['dataset_name'] = uploaded_file.name
            request.session['dataset_path'] = filename

            return redirect('dataset_preview')

    return render(request, 'upload.html')


def dataset_preview(request):
    return render(request, 'dataset_preview.html')


def analysis(request):
    return render(request, 'analysis.html')


def visualizations(request):
    return render(request, 'visualizations.html')


def insights(request):
    return render(request, 'insights.html')


def history(request):
    return render(request, 'history.html')


def reports(request):
    return render(request, 'reports.html')


def loading(request):
    return render(request, 'loading.html')


def empty(request):
    return render(request, 'empty.html')


def error(request):
    return render(request, 'error.html')