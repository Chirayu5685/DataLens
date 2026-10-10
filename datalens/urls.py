from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from .views import (
    delete_dataset,
    home,
    authentication,
     logout_user,
    dashboard,
    upload_dataset,
    dataset_preview,
    analysis,
    visualizations,
    visualization_data,
    insights,
    history,
    reports,
    loading,
    empty,
    error,
    impute_nulls,
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
    path(
    'api/visualization-data/',
    visualization_data,
    name='visualization_data'),
    path('insights/', insights, name='insights'),
    path('history/', history, name='history'),
    path('reports/', reports, name='reports'),
    path('loading/', loading, name='loading'),
    path('empty/', empty, name='empty'),
    path('error/', error, name='error'),
    path(
    'logout/',
    logout_user,
    name='logout'
    
),
path(
    'impute-nulls/',
    impute_nulls,
    name='impute_nulls'
),
path(
    'datasets/<int:dataset_id>/delete/',
    delete_dataset,
    name='delete_dataset'
),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)