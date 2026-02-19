# users/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('csrf/', views.get_csrf_token, name='api_csrf'),
    path('login/', views.login_view, name='api_login'),
    path('logout/', views.logout_view, name='api_logout'),
    path('me/', views.user_info_view, name='api_user_info'),
]