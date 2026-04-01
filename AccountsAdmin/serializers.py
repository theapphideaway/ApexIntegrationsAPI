from django.core.files.storage import default_storage
from rest_framework import serializers
from .models import Organization, CustomUser, Deal


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = '__all__' # For testing, we'll expose all fields


class CustomUserSerializer(serializers.ModelSerializer):
    # We use PrimaryKeyRelatedField so Postman can just send the Organization UUID string
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())

    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number', 'role', 'organization']


class DealSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    # We turn these into "Method Fields" so we can run custom Python code on them
    draft_pdf_url = serializers.SerializerMethodField()
    signed_pdf_url = serializers.SerializerMethodField()

    agent_id = serializers.SerializerMethodField()

    class Meta:
        model = Deal
        fields = [
            'id',
            'agent_id',
            'property_address',
            'buyer_names',
            'status',
            'status_display',
            'docusign_envelope_id',
            'draft_pdf_url',
            'signed_pdf_url',
            'updated_at'
        ]

    def get_agent_id(self, obj):
        # Assuming your Deal model has an 'agent' ForeignKey, Django automatically
        # creates an 'agent_id' property. We check if it exists and is not None.
        if hasattr(obj, 'agent_id') and obj.agent_id:
            return str(obj.agent_id)

        # Fallback to your Admin ID if no agent is assigned
        return "60d8ba89-e169-4f97-86d8-9b45d317e149"

    def get_draft_pdf_url(self, obj):
        if not obj.draft_pdf_url:
            return None

        # Safety fallback for your old test data that already has the massive URL saved
        if obj.draft_pdf_url.startswith('http'):
            return obj.draft_pdf_url

        # For all new data: Generate a fresh 5-minute link right now
        return default_storage.url(obj.draft_pdf_url)

    def get_signed_pdf_url(self, obj):
        if not obj.signed_pdf_url:
            return None

        if obj.signed_pdf_url.startswith('http'):
            return obj.signed_pdf_url

        return default_storage.url(obj.signed_pdf_url)