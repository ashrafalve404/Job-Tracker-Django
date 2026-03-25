from django.contrib import admin
from django import forms
from django.shortcuts import render
from django.urls import path
from .models import JobSource, Job, SavedJob


class JobSourceForm(forms.Form):
    """Form for bulk adding job sources."""
    urls = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'placeholder': 'Enter one URL per line:\nhttps://remoteok.com\nhttps://weworkremotely.com\nhttps://indeed.com'}),
        help_text='Enter job site URLs, one per line. Format: Name,URL (optional name)'
    )
    activate = forms.BooleanField(required=False, initial=True, help_text='Activate all sources after adding')


@admin.register(JobSource)
class JobSourceAdmin(admin.ModelAdmin):
    """Admin configuration for JobSource model."""
    list_display = ['name', 'base_url', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['name', 'base_url']
    ordering = ['name']
    list_editable = ['is_active']
    
    change_list_template = 'admin/jobsource_changelist.html'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('bulk-add/', self.bulk_add_view, name='jobscraper_jobsource_bulk_add'),
        ]
        return custom_urls + urls
    
    def bulk_add_view(self, request):
        """View for bulk adding job sources."""
        if request.method == 'POST':
            form = JobSourceForm(request.POST)
            if form.is_valid():
                urls_text = form.cleaned_data['urls']
                activate = form.cleaned_data['activate']
                
                lines = urls_text.strip().split('\n')
                count = 0
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse line - can be just URL or "Name,URL"
                    if ',' in line:
                        parts = line.split(',', 1)
                        name = parts[0].strip()
                        url = parts[1].strip()
                    else:
                        # Use domain as name
                        from urllib.parse import urlparse
                        parsed = urlparse(line)
                        name = parsed.netloc or 'Job Source'
                        url = line
                        if not url.startswith('http'):
                            url = 'https://' + url
                    
                    # Check if exists
                    if not JobSource.objects.filter(base_url=url).exists():
                        JobSource.objects.create(
                            name=name,
                            base_url=url,
                            is_active=activate
                        )
                        count += 1
                
                self.message_user(request, f'{count} job source(s) added successfully!')
                return render(request, 'admin/bulk_add_success.html', {
                    'count': count,
                    'back_url': '/admin/jobscraper/jobsource/'
                })
        else:
            form = JobSourceForm()
        
        return render(request, 'admin/bulk_add_form.html', {'form': form})


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Admin configuration for Job model."""
    list_display = ['title', 'company', 'work_mode', 'job_type', 'deadline', 'source', 'is_active', 'scraped_at']
    list_filter = ['work_mode', 'job_type', 'is_active', 'source', 'company']
    search_fields = ['title', 'company', 'location', 'description']
    ordering = ['-created_at']
    list_editable = ['is_active']
    readonly_fields = ['scraped_at', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'company', 'location')
        }),
        ('Job Details', {
            'fields': ('job_type', 'work_mode', 'deadline', 'description')
        }),
        ('Source & URL', {
            'fields': ('source', 'source_job_id', 'apply_url')
        }),
        ('Dates', {
            'fields': ('posted_at', 'scraped_at', 'created_at', 'updated_at')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )


@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    """Admin configuration for SavedJob model."""
    list_display = ['user', 'job', 'saved_at']
    list_filter = ['saved_at']
    search_fields = ['user__username', 'job__title', 'job__company']
    ordering = ['-saved_at']
    readonly_fields = ['saved_at']
    date_hierarchy = 'saved_at'
