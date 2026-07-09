from django.urls import path
from . import views
from .views import FUBAuthCallbackView, FUBSendDocumentView, DocumentPreviewEndpoint, \
    DocumentCreateSignatureLinkEndpoint, DistributeExecutedPacketEndpoint

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
    path('fub/send/', FUBSendDocumentView.as_view(), name='fub_send_document'),
    path('documents/preview/<str:doc_type>/', DocumentPreviewEndpoint.as_view(), name='document_preview'),
    path('documents/send/<str:doc_type>/', DocumentCreateSignatureLinkEndpoint.as_view(), name='document_send'),
    path('api/documents/distribute/', DistributeExecutedPacketEndpoint.as_view(), name='distribute_packet'),
]
