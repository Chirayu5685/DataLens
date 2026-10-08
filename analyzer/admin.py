from django.contrib import admin
from .models import Dataset


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'rows',
        'columns',
        'file_size',
        'uploaded_at',
    )

    search_fields = ('name',)