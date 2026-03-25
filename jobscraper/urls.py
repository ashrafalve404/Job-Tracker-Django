from django.urls import path
from . import views

app_name = 'jobscraper'

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    
    # Jobs
    path('jobs/', views.job_list, name='jobs'),
    path('jobs/<int:job_id>/', views.job_detail, name='job_detail'),
    
    # Saved Jobs
    path('saved-jobs/', views.saved_jobs, name='saved_jobs'),
    path('save-job/<int:job_id>/', views.save_job, name='save_job'),
    path('remove-saved-job/<int:job_id>/', views.remove_saved_job, name='remove_saved_job'),
    
    # Authentication
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]