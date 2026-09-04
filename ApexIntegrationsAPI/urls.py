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
from django.conf import settings
from django.urls import re_path
from django.views.static import serve as static_serve
from AccountsAdmin import dev_views, team_views
from AccountsAdmin.views import (
    portal_index, DealArchiveView, DealDocumentsView, DealDocumentDetailView, DealDocumentSendView, DealStateView, DealActivityView, ContractDefaultsView, DealDraftsView, DealDraftDetailView,
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
    path('api/deals/<int:pk>/documents/send/', DealDocumentSendView.as_view(), name='deal-document-send'),
    path('api/deals/<int:pk>/documents/<int:doc_id>/', DealDocumentDetailView.as_view(), name='deal-document-detail'),
    path('api/deals/<int:pk>/state/', DealStateView.as_view(), name='deal-state'),
    path('api/deals/<int:pk>/activity/', DealActivityView.as_view(), name='deal-activity'),
    path('api/drafts/', DealDraftsView.as_view(), name='drafts'),
    path('api/drafts/<uuid:pk>/', DealDraftDetailView.as_view(), name='draft-detail'),

    path('api/mls/listing/<str:mls_number>/', MLSListingProxyView.as_view(), name='mls_listing'),
    path('api/mls/search/', MLSAddressSearchView.as_view(), name='mls_search'),

    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Team-admin portal API (role admin; scoped to the admin's own team).
    path('api/defaults/', ContractDefaultsView.as_view(), name='contract-defaults'),
    path('api/team/', team_views.TeamView.as_view(), name='team'),
    path('api/team/defaults/', team_views.TeamDefaultsView.as_view(), name='team-defaults'),
    path('api/team/members/', team_views.TeamMembersView.as_view(), name='team-members'),
    path('api/team/members/<uuid:pk>/', team_views.TeamMemberDetailView.as_view(), name='team-member-detail'),

    # Developer / super-admin portal API (superuser only).
    path('api/dev/settings/', dev_views.DevSettingsView.as_view(), name='dev-settings'),
    path('api/dev/docusign/test/', dev_views.DevDocuSignTestView.as_view(), name='dev-docusign-test'),
    path('api/dev/teams/', dev_views.DevTeamsView.as_view(), name='dev-teams'),
    path('api/dev/teams/<uuid:pk>/', dev_views.DevTeamDetailView.as_view(), name='dev-team-detail'),
    path('api/dev/users/', dev_views.DevUsersView.as_view(), name='dev-users'),
    path('api/dev/users/<uuid:pk>/', dev_views.DevUserDetailView.as_view(), name='dev-user-detail'),
    path('api/dev/test-deals/', dev_views.DevTestDealsView.as_view(), name='dev-test-deals'),
    path('api/dev/test-deals/purge/', dev_views.DevTestDealsView.as_view(), name='dev-test-deals-purge'),

    # Web portal (built React app in web/dist), same origin as the API.
    re_path(r'^portal/assets/(?P<path>.*)$', static_serve, {'document_root': settings.BASE_DIR / 'web' / 'dist' / 'assets'}),
    re_path(r'^portal(?:/.*)?$', portal_index, name='portal'),
]
