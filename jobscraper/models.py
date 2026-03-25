from django.db import models
from django.contrib.auth.models import User
from datetime import date


class JobSource(models.Model):
    """Model representing a job source website."""
    name = models.CharField(max_length=200, unique=True)
    base_url = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Job(models.Model):
    """Model representing a job listing."""

    # Job type choices
    JOB_TYPE_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('internship', 'Internship'),
        ('contract', 'Contract'),
    ]

    # Work mode choices
    WORK_MODE_CHOICES = [
        ('remote', 'Remote'),
        ('onsite', 'On-site'),
        ('hybrid', 'Hybrid'),
    ]

    title = models.CharField(max_length=300)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True, default='')
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default='full_time')
    work_mode = models.CharField(max_length=20, choices=WORK_MODE_CHOICES, default='onsite')
    deadline = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    apply_url = models.URLField(max_length=500, blank=True, default='')
    source = models.ForeignKey(JobSource, on_delete=models.CASCADE, related_name='jobs')
    source_job_id = models.CharField(max_length=200, blank=True, default='')
    posted_at = models.DateField(null=True, blank=True)
    scraped_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # Unique constraint to prevent duplicates
        unique_together = ['source', 'apply_url']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['is_active']),
            models.Index(fields=['company']),
        ]

    def __str__(self):
        return f"{self.title} at {self.company}"

    def save(self, *args, **kwargs):
        # Check if deadline has passed and mark as inactive
        if self.deadline:
            if self.deadline < date.today():
                self.is_active = False
        super().save(*args, **kwargs)


class SavedJob(models.Model):
    """Model representing a saved/bookmarked job by a user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_jobs')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='saved_by')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-saved_at']
        # Prevent duplicate saves
        unique_together = ['user', 'job']

    def __str__(self):
        return f"{self.user.username} saved {self.job.title}"
