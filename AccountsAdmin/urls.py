from django.urls import path
from . import views
from .views import FUBAuthCallbackView, FUBSendDocumentView, FUBConnectURLView, FUBStatusView, FUBBackfillView, FUBWebhookView, FUBWebhooksRegisterView, \
    DocumentPreviewEndpoint, DistributeExecutedPacketEndpoint, SendOnboardingBundleEndpoint

urlpatterns = [
    path('organizations/', views.organization_list, name='organization-list'),
    path('users/', views.user_list, name='user-list'),
    path('request-otp/', views.request_otp, name='request-otp'),
    path('add-user/', views.add_user, name='add-user'),
    path('add-organization/', views.add_organization, name='add-organization'),
    path('verify-otp/', views.verify_otp, name='verify-otp'),
    path('delete-user/<uuid:user_id>/', views.delete_user, name='delete-user'),
    path('users/me/', views.current_user, name='current_user'),
    path('fub/callback/', FUBAuthCallbackView.as_view(), name='fub_auth_callback'),
    path('fub/connect-url/', FUBConnectURLView.as_view(), name='fub_connect_url'),
    path('fub/status/', FUBStatusView.as_view(), name='fub_status'),
    path('fub/backfill/', FUBBackfillView.as_view(), name='fub_backfill'),
    path('fub/webhooks/', FUBWebhooksRegisterView.as_view(), name='fub_webhooks'),
    path('fub/webhook/<str:token>/', FUBWebhookView.as_view(), name='fub_webhook'),
    path('fub/send/', FUBSendDocumentView.as_view(), name='fub_send_document'),
    path('documents/preview/<str:doc_type>/', DocumentPreviewEndpoint.as_view(), name='document_preview'),
    path('documents/send/<str:doc_type>/', SendOnboardingBundleEndpoint.as_view(), name='document_send'),
    path('api/documents/distribute/', DistributeExecutedPacketEndpoint.as_view(), name='distribute_packet'),
]
