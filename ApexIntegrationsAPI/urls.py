"""
URL configuration for ApexIntegrationsAPI project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # This acts as a gateway. It catches anything starting with 'api/auth/'
    # and passes the rest of the URL to your accounts app.
    # Note: Replace 'accounts.urls' if your app folder is named something else
    # (like 'AccountsAdmin.urls')
    path('api/auth/', include('AccountsAdmin.urls')),
]
