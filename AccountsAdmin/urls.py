from django.urls import path
from . import views

urlpatterns = [
    path('organizations/', views.organization_list, name='organization-list'),
    path('users/', views.user_list, name='user-list'),
    path('request-otp/', views.request_otp, name='request-otp'),
    path('add-user/', views.add_user, name='add-user'),
    path('verify-otp/', views.verify_otp, name='verify-otp'),
    path('delete-user/<uuid:user_id>/', views.delete_user, name='delete-user'),
]
