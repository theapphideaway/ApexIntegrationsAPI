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
from rest_framework_simplejwt.views import TokenRefreshView

# Make sure to import your new Document endpoints here
from AccountsAdmin.views import (
    DealArchiveView, DealDocumentsView, DealStateView,
    docusign_webhook,
    RE21ContractStatusEndpoint,
    AgentDealsListCreateView,
    landing_page,
    DocumentPreviewEndpoint,
    SendOnboardingBundleEndpoint,
    OnboardingBundlePreviewEndpoint, DealDetailEndpoint,
    MLSListingProxyView, MLSAddressSearchView
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', landing_page, name='landing_page'),
    path('api/auth/', include('AccountsAdmin.urls')),

    path('api/documents/preview-bundle/', OnboardingBundlePreviewEndpoint.as_view(), name='preview_bundle'),
    path('api/documents/preview/<str:doc_type>/', DocumentPreviewEndpoint.as_view(), name='document_preview'),
    path('api/documents/send/<str:doc_type>/', SendOnboardingBundleEndpoint.as_view(), name='document_send'),

    path('api/contracts/webhook/', docusign_webhook, name='docusign_webhook'),
    path('api/contracts/status/<str:envelope_id>/', RE21ContractStatusEndpoint.as_view(), name='contract_status'),
    path('api/deals/', AgentDealsListCreateView.as_view(), name='agent-deals-list-create'),
    path('api/deals/<int:pk>/', DealDetailEndpoint.as_view(), name='deal-detail'),
    path('api/deals/<int:pk>/archive/', DealArchiveView.as_view(), name='deal-archive'),
    path('api/deals/<int:pk>/documents/', DealDocumentsView.as_view(), name='deal-documents'),
    path('api/deals/<int:pk>/state/', DealStateView.as_view(), name='deal-state'),

    path('api/mls/listing/<str:mls_number>/', MLSListingProxyView.as_view(), name='mls_listing'),
    path('api/mls/search/', MLSAddressSearchView.as_view(), name='mls_search'),

    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
