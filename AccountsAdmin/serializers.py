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
    # We add a custom field to format the status text exactly how Swift expects it
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Deal
        fields = [
            'id',
            'property_address',
            'buyer_names',
            'status',
            'status_display',
            'docusign_envelope_id',
            'draft_pdf_url',
            'signed_pdf_url',
            'updated_at'
        ]