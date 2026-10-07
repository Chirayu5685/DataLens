from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    home,
    authentication,
    dashboard,
    upload_dataset,
    dataset_preview,
    analysis,
    visualizations,
    insights,
    history,
    reports,
    loading,
    empty,
    error,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', home, name='home'),
    path('authentication/', authentication, name='authentication'),
    path('dashboard/', dashboard, name='dashboard'),
    path('upload/', upload_dataset, name='upload_dataset'),
    path('preview/', dataset_preview, name='dataset_preview'),
    path('analysis/', analysis, name='analysis'),
    path('visualizations/', visualizations, name='visualizations'),
    path('insights/', insights, name='insights'),
    path('history/', history, name='history'),
    path('reports/', reports, name='reports'),
    path('loading/', loading, name='loading'),
    path('empty/', empty, name='empty'),
    path('error/', error, name='error'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)