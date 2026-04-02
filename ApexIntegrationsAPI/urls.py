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

from AccountsAdmin.views import RE21PreviewEndpoint, RE21CreateSignatureLinkEndpoint, docusign_webhook, \
    RE21ContractStatusEndpoint, AgentDealsListView, DealDeleteEndpoint, landing_page

urlpatterns = [
    path('admin/', admin.site.urls),

    # This acts as a gateway. It catches anything starting with 'api/auth/'
    # and passes the rest of the URL to your accounts app.
    # Note: Replace 'accounts.urls' if your app folder is named something else
    # (like 'AccountsAdmin.urls')
    path('', landing_page, name='landing_page'),
    path('api/auth/', include('AccountsAdmin.urls')),
    path('api/contracts/preview-re21/', RE21PreviewEndpoint.as_view(), name='preview_re21'),
    path('api/contracts/create-signing-link/', RE21CreateSignatureLinkEndpoint.as_view(), name='create_signing_link'),
    path('api/contracts/webhook/', docusign_webhook, name='docusign_webhook'),
    path('api/contracts/status/<str:envelope_id>/', RE21ContractStatusEndpoint.as_view(), name='contract_status'),
    path('api/deals/', AgentDealsListView.as_view(), name='agent_deals'),
    path('api/deals/<int:pk>/', DealDeleteEndpoint.as_view(), name='delete_deal'),
]
