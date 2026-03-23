from rest_framework import serializers
from .models import Organization, CustomUser


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

