import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.conf import settings
from django.utils import timezone
import random
from datetime import timedelta


class Organization(models.Model):
    """
    Represents the Account Holder (e.g., a Brokerage).
    """
    PLAN_CHOICES = (
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, default='basic')
    is_active = models.BooleanField(default=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class CustomUserManager(BaseUserManager):
    """
    Custom manager required since we are not using the default username field.
    """

    def create_user(self, email, phone_number=None, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, phone_number=phone_number, **extra_fields)
        # Even for passwordless, Django expects a hashed password state.
        # set_unusable_password() flags this user as not having a valid password.
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        return self.create_user(email, password=password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    The Agent or Admin belonging to an Organization.
    """
    # Organization == the agent TEAM (we sell to teams, not brokerages).
    # admin = team admin (may also sell), tc = transaction coordinator
    # (works every agent's deals), agent = sees own deals only.
    ROLE_CHOICES = (
        ('admin', 'Team Admin'),
        ('tc', 'Transaction Coordinator'),
        ('agent', 'Agent'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to the Account Holder (Nullable initially so superusers can exist without one)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True,
                                     related_name='users')

    # Identifiers
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True)

    # Basic Info
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='agent')

    # Django Auth Requirements
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Metadata
    date_joined = models.DateTimeField(default=timezone.now)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)  # Good for security audits
    # TextField: OAuth tokens have no fixed length (SQLite ignored the old
    # 255 cap; Postgres enforces it and rejected real FUB tokens).
    # Per-user DocuSign environment: True = production account (only effective
    # when the production master switch is on and prod creds exist); False = demo.
    docusign_production = models.BooleanField(default=False)
    fub_access_token = models.TextField(blank=True, null=True)
    fub_refresh_token = models.TextField(blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    # Required fields when creating a superuser via command line
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return f"{self.email} - {self.organization.name if self.organization else 'No Org'}"


class OTPCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        # Check if the code is unused and less than 10 minutes old
        expiration_time = self.created_at + timedelta(minutes=10)
        return not self.is_used and timezone.now() < expiration_time

    @classmethod
    def generate_for_user(cls, user):
        # Invalidate any previously active codes for this user
        cls.objects.filter(user=user, is_used=False).update(is_used=True)

        # Generate a secure 6-digit random number
        secure_random = random.SystemRandom()
        code = str(secure_random.randint(100000, 999999))

        return cls.objects.create(user=user, code=code)

    def __str__(self):
        return f"{self.user.email} - {self.code}"


class Deal(models.Model):
    # Core Info
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='deals')
    property_address = models.CharField(max_length=255)
    buyer_names = models.CharField(max_length=255)
    # Primary buyer's email — lets the DocuSign webhook attach the executed
    # packet to the right CRM contact without re-querying the envelope.
    buyer_email = models.EmailField(blank=True, null=True)
    # Listing-side contact captured from the MLS when the offer was sent —
    # where buyer-originated counters get forwarded.
    listing_agent_email = models.EmailField(blank=True, null=True)
    listing_agent_name = models.CharField(max_length=150, blank=True, default='')
    # True once this deal has been posted to the agent's CRM (Follow Up Boss),
    # so connect-time backfills never create duplicate notes.
    fub_synced = models.BooleanField(default=False)
    # Archived deals leave the active pipeline but are kept (and deletable).
    is_archived = models.BooleanField(default=False)

    # Server-side deal state so the agent's phone, the TC portal, and any
    # other device all see the same thing (this used to live in UserDefaults
    # on whichever phone sent the deal).
    checklist_state = models.JSONField(default=dict, blank=True)   # {task_key: status}
    form_snapshot = models.JSONField(null=True, blank=True)        # the RE-21 as sent
    acceptance_date = models.DateTimeField(null=True, blank=True)  # set on envelope completion

    # State Management
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('out_for_signature', 'Waiting on buyers signatures'),
        ('signed_by_buyers', 'Offer ready to send'),
        ('fully_executed', 'Fully Executed'),
        ('cancelled', 'Cancelled')
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft')

    # DocuSign Tracking
    docusign_envelope_id = models.CharField(max_length=100, blank=True, null=True)
    docusign_env = models.CharField(max_length=12, default='demo')  # 'demo' | 'production'

    # S3 keys (legacy rows hold full presigned URLs, which run past 500
    # chars — TextField so Postgres accepts the old data).
    draft_pdf_url = models.TextField(blank=True, null=True)
    # Executed RE-21 by itself (no RE-14 / agency brochure) — what title and
    # the lender should receive; the full packet stays in signed_pdf_url.
    signed_re21_url = models.TextField(blank=True, null=True)
    signed_pdf_url = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.property_address} - {self.buyer_names}"


class DealDocument(models.Model):
    """A document attached to a deal beyond the original packet: received
    counter offers, sent counters, RE-10s, addenda, invoices… Each may carry
    its own DocuSign envelope. This is the backbone for negotiation flows and
    (later) seller-side and web uploads."""
    DIRECTION_CHOICES = [('received', 'Received'), ('sent', 'Sent')]
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('out_for_signature', 'Out for signature'),
        ('signed', 'Signed'),
        ('rejected', 'Rejected'),
    ]

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=40, default='other')  # 're_13', 're_10', 'other'
    title = models.CharField(max_length=200)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='received')
    sequence = models.PositiveIntegerField(default=1)  # counter #1, #2…
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='received')
    docusign_envelope_id = models.CharField(max_length=100, blank=True, null=True)
    docusign_env = models.CharField(max_length=12, default='demo')  # 'demo' | 'production'
    pdf_key = models.CharField(max_length=500, blank=True, null=True)
    signed_pdf_key = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.deal_id})"


class AppSetting(models.Model):
    """Runtime configuration editable from the dev portal (no redeploy):
    e.g. docusign_env = "demo" | "production". Secrets never live here —
    they stay in .env; settings only choose between them."""
    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.key}={self.value}"
