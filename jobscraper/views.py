from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from datetime import date

from .models import Job, JobSource, SavedJob
from .forms import UserRegistrationForm, JobFilterForm


def home(request):
    """Home page view with quick stats and latest jobs."""
    # Get stats
    total_active_jobs = Job.objects.filter(is_active=True).count()
    total_companies = Job.objects.filter(is_active=True).values('company').distinct().count()
    total_sources = JobSource.objects.filter(is_active=True).count()
    
    # Get latest jobs (only active ones)
    latest_jobs = Job.objects.filter(is_active=True).order_by('-created_at')[:6]
    
    context = {
        'total_active_jobs': total_active_jobs,
        'total_companies': total_companies,
        'total_sources': total_sources,
        'latest_jobs': latest_jobs,
    }
    return render(request, 'jobscraper/home.html', context)


def job_list(request):
    """Job listing page with search and filters."""
    jobs = Job.objects.filter(is_active=True).order_by('-created_at')
    
    # Get filter parameters from GET request
    search = request.GET.get('search', '')
    work_mode = request.GET.get('work_mode', '')
    job_type = request.GET.get('job_type', '')
    company = request.GET.get('company', '')
    source_id = request.GET.get('source', '')
    active_only = request.GET.get('active_only', 'on')
    
    # Build query based on filters
    if search:
        jobs = jobs.filter(
            Q(title__icontains=search) |
            Q(company__icontains=search) |
            Q(location__icontains=search) |
            Q(description__icontains=search)
        )
    
    if work_mode:
        jobs = jobs.filter(work_mode=work_mode)
    
    if job_type:
        jobs = jobs.filter(job_type=job_type)
    
    if company:
        jobs = jobs.filter(company__icontains=company)
    
    if source_id:
        jobs = jobs.filter(source_id=source_id)
    
    # If active_only is NOT checked, show all jobs
    if not active_only:
        jobs = Job.objects.order_by('-created_at')
        # Re-apply filters
        if search:
            jobs = jobs.filter(
                Q(title__icontains=search) |
                Q(company__icontains=search) |
                Q(location__icontains=search) |
                Q(description__icontains=search)
            )
        if work_mode:
            jobs = jobs.filter(work_mode=work_mode)
        if job_type:
            jobs = jobs.filter(job_type=job_type)
        if company:
            jobs = jobs.filter(company__icontains=company)
        if source_id:
            jobs = jobs.filter(source_id=source_id)
    
    # Pagination
    paginator = Paginator(jobs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get user's saved jobs if logged in
    saved_job_ids = []
    if request.user.is_authenticated:
        saved_job_ids = list(SavedJob.objects.filter(user=request.user).values_list('job_id', flat=True))
    
    # Get sources for filter dropdown
    from jobscraper.models import JobSource
    sources = JobSource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'saved_job_ids': saved_job_ids,
        'sources': sources,
        # Pass filter values back to template
        'filter_search': search,
        'filter_work_mode': work_mode,
        'filter_job_type': job_type,
        'filter_company': company,
        'filter_source': source_id,
        'filter_active': active_only,
    }
    return render(request, 'jobscraper/job_list.html', context)


def job_detail(request, job_id):
    """Job detail page."""
    job = get_object_or_404(Job, pk=job_id)
    
    # Check if user has saved this job
    is_saved = False
    if request.user.is_authenticated:
        is_saved = SavedJob.objects.filter(user=request.user, job=job).exists()
    
    context = {
        'job': job,
        'is_saved': is_saved,
    }
    return render(request, 'jobscraper/job_detail.html', context)


@login_required
def saved_jobs(request):
    """User's saved jobs page."""
    saved_jobs = SavedJob.objects.filter(user=request.user).select_related('job', 'job__source')
    
    context = {
        'saved_jobs': saved_jobs,
    }
    return render(request, 'jobscraper/saved_jobs.html', context)


@login_required
def save_job(request, job_id):
    """Save a job."""
    job = get_object_or_404(Job, pk=job_id)
    
    # Check if already saved
    if not SavedJob.objects.filter(user=request.user, job=job).exists():
        SavedJob.objects.create(user=request.user, job=job)
        messages.success(request, f'Job "{job.title}" saved successfully!')
    else:
        messages.info(request, 'This job is already saved.')
    
    # Redirect back to the referring page or job list
    return redirect(request.META.get('HTTP_REFERER', 'jobscraper:jobs'))


@login_required
def remove_saved_job(request, job_id):
    """Remove a saved job."""
    job = get_object_or_404(Job, pk=job_id)
    saved_job = SavedJob.objects.filter(user=request.user, job=job).first()
    
    if saved_job:
        saved_job.delete()
        messages.success(request, f'Job "{job.title}" removed from saved jobs.')
    else:
        messages.error(request, 'This job is not in your saved list.')
    
    return redirect(request.META.get('HTTP_REFERER', 'jobscraper:saved_jobs'))


def register(request):
    """User registration view."""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to JobTrack.')
            return redirect('jobscraper:home')
    else:
        form = UserRegistrationForm()
    
    context = {
        'form': form,
    }
    return render(request, 'jobscraper/register.html', context)


def login_view(request):
    """User login view."""
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                next_url = request.GET.get('next')
                return redirect(next_url if next_url else 'jobscraper:home')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    context = {
        'form': form,
    }
    return render(request, 'jobscraper/login.html', context)


def logout_view(request):
    """User logout view."""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('jobscraper:home')
