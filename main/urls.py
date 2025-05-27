# main/urls.py (app urls)
from django.urls import path
from . import views

app_name = 'main'

urlpatterns = [
    path('', views.home, name='home'),
    path('toggle-theme/', views.toggle_theme, name='toggle_theme'),
    path('contact/', views.contact, name='contact'),
    path('subscribe/', views.subscribe, name='subscribe'),
    
    # Authentication URLs
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Project URLs
    path('projects/', views.project_list, name='project_list'),
    path('projects/create/', views.create_project, name='create_project'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('projects/<int:project_id>/update/', views.update_project, name='update_project'),
    path('projects/<int:project_id>/activities/create/', views.create_activity, name='create_activity'),
    path('projects/<int:project_id>/activities/<int:activity_id>/update/', views.update_activity, name='update_activity'),
    path('projects/<int:project_id>/activities/<int:activity_id>/tasks/<int:task_id>/toggle/', views.toggle_task, name='toggle_task'),
]