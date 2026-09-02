import base64
import logging
import os
import traceback
import urllib
import pusher

import pymupdf
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from docusign_esign import EnvelopesApi, ApiClient
from rest_framework.generics import ListCreateAPIView, RetrieveDestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
import requests

from .docusign_service import DocuSignService
from . import fub_service
from .pdf_service import PDFGenerationService, DocumentType
# Create your views here.

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Organization, CustomUser, OTPCode, Deal, DealDocument
from .serializers import OrganizationSerializer, CustomUserSerializer, DealSerializer, DealDocumentSerializer
from django.core.mail import send_mail, EmailMessage
from django.conf import settings

pusher_client = pusher.Pusher(
    app_id=settings.PUSHER_APP_ID,
    key=settings.PUSHER_KEY,
    secret=settings.PUSHER_SECRET,
    cluster=settings.PUSHER_CLUSTER,
    ssl=True
)

def landing_page(request):
    return render(request, 'landing_page.html')


def is_team_role(user) -> bool:
    """TCs and team admins work every deal on their team."""
    return getattr(user, "role", "") in ("tc", "admin")


def deals_for(user):
    """Role-based deal visibility: agents see their own deals; TCs and team
    admins see every deal whose agent is on their team."""
    if is_team_role(user) and getattr(user, "organization_id", None):
        return Deal.objects.filter(agent__organization_id=user.organization_id)
    return Deal.objects.filter(agent=user)


class IsAdminRole(IsAuthenticated):
    """Admin-only endpoints: user management, organizations. Agents never
    need these — every agent-facing endpoint scopes to request.user."""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        return getattr(user, "role", "") == "admin" or user.is_staff


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """
    Returns the profile data for the currently authenticated user.
    """
    # request.user is securely guaranteed by the IsAuthenticated lock
    serializer = CustomUserSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminRole])
def organization_list(request):
    """
    List all organizations
    """
    organizations = Organization.objects.all()
    serializer = OrganizationSerializer(organizations, many=True)
    return Response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminRole])
def user_list(request):
    """
    List all users, or create a new user.
    """
    if request.method == 'GET':
        users = CustomUser.objects.all()
        serializer = CustomUserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = CustomUserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def request_otp(request):
    email = request.data.get('email')
    print(f"---> API Request received for: {email}")  # DEBUG

    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    # ---------------------------------------------------------
    # 0. THE DEV & APP STORE REVIEW BYPASS
    # ---------------------------------------------------------
    if settings.OTP_DEV_BYPASS and email.lower() == 'ianschoenrock@gmail.com':
        print("---> BYPASS TRIGGERED: Skipping email generation for admin test account.")
        # Return a fake success message so the iOS app proceeds to the verification screen
        return Response(
            {"message": "Verification code has been sent to your email."},
            status=status.HTTP_200_OK
        )

    # ---------------------------------------------------------
    # 1. NORMAL OTP FLOW
    # ---------------------------------------------------------
    try:
        user = CustomUser.objects.get(email__iexact=email)
        print(f"---> User found: {user.first_name}")  # DEBUG

        otp_instance = OTPCode.generate_for_user(user)
        print(f"---> OTP Generated: {otp_instance.code}")  # DEBUG

        subject = f"Your Login Code: {otp_instance.code}"
        message = f"Hello {user.first_name},\n\nCode: {otp_instance.code}"

        print("---> Attempting to send email...")  # DEBUG
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,  # This MUST be False to see the error
        )
        print("---> Email sent successfully!")  # DEBUG

    except CustomUser.DoesNotExist:
        print("---> ERROR: User does not exist in the database!")  # DEBUG
        # We still return 200 for security, so bad actors can't use this endpoint to fish for valid emails.
        pass
    except Exception as e:
        print(f"---> SMTP/SYSTEM ERROR: {e}")  # DEBUG
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {"message": "Verification code has been sent to your email."},
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([IsAdminRole])
def add_user(request):
    """
    Endpoint for a Brokerage/Admin to add a new agent.
    Automatically sends an invite email with a link to download the app.
    """
    serializer = CustomUserSerializer(data=request.data)

    if serializer.is_valid():
        # 1. Create the user using our custom manager
        user = CustomUser.objects.create_user(
            email=serializer.validated_data['email'],
            organization=serializer.validated_data['organization'],
            first_name=serializer.validated_data.get('first_name', ''),
            last_name=serializer.validated_data.get('last_name', ''),
            phone_number=serializer.validated_data.get('phone_number', ''),
            role=serializer.validated_data.get('role', 'agent')
        )

        # 2. Prepare the Invitation Email
        org_name = user.organization.name
        app_link = "https://example.com/download-real-estate-ai"  # Your dummy link

        subject = f"Invitation to join {org_name} on Real Estate AI"
        message = (
            f"Real Estate AI Invite link:\n\n"
            f"You've been invited to download the Real Estate AI app by {org_name}.\n"
            f"Download the app here: {app_link}\n\n"
            f"Once installed, log in using your email: {user.email}"
        )

        # 3. Send the Email
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            print(f"---> Invite sent to {user.email} for {org_name}")
        except Exception as e:
            print(f"---> Failed to send invite: {e}")
            # We still return 201 because the user was created successfully

        return Response(CustomUserSerializer(user).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminRole])
def add_organization(request):
    """
    Endpoint for a Super Admin to explicitly add a new Organization (Brokerage).
    """
    serializer = OrganizationSerializer(data=request.data)

    if serializer.is_valid():
        # 1. Save the new Organization to the database
        organization = serializer.save()

        # 2. (Optional Future Logic)
        # You can add logic here to notify your team, trigger a webhook,
        # or send a welcome email to the new Brokerage owner.
        print(f"---> New Organization created: {organization.name} (Plan: {organization.plan_type})")

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def verify_otp(request):
    email = request.data.get('email', '').strip()
    code = request.data.get('code', '').strip()

    print(f"---> Verification attempt: Email='{email}', Code='{code}'")

    # ---------------------------------------------------------
    # 0. THE DEV & APP STORE REVIEW BYPASS
    # ---------------------------------------------------------
    if settings.OTP_DEV_BYPASS and email.lower() == 'ianschoenrock@gmail.com' and code == '000000':
        print("---> BYPASS TRIGGERED for admin test account.")
        try:
            user = CustomUser.objects.get(email__iexact=email)

            # Update last login just like the normal flow
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])

            refresh = RefreshToken.for_user(user)
            print("---> Success! Tokens generated via bypass.")

            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': str(user.id)  # Cast to string to ensure Swift parses it cleanly
            }, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            print("---> ERROR: Admin bypass user not found in DB.")
            return Response({"error": "Admin user not found."}, status=status.HTTP_404_NOT_FOUND)

    # ---------------------------------------------------------
    # 1. NORMAL OTP FLOW
    # ---------------------------------------------------------
    try:
        # Check User
        user = CustomUser.objects.get(email__iexact=email)
        print(f"---> User found: {user.id}")

        # Check for the OTP
        # We look for the most recent UNUSED code for this specific user
        otp_instance = OTPCode.objects.filter(
            user=user,
            code=code,
            is_used=False
        ).latest('created_at')

        print(f"---> OTP found in DB. Created at: {otp_instance.created_at}")

        # Check Validity
        if otp_instance.is_valid():
            otp_instance.is_used = True
            otp_instance.save()

            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])

            refresh = RefreshToken.for_user(user)
            print("---> Success! Tokens generated.")

            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user_id': str(user.id)
            }, status=status.HTTP_200_OK)

        else:
            print("---> ERROR: OTP exists but is expired.")
            return Response({"error": "Expired code."}, status=status.HTTP_401_UNAUTHORIZED)

    except CustomUser.DoesNotExist:
        print(f"---> ERROR: No user found with email {email}")
        return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
    except OTPCode.DoesNotExist:
        print(f"---> ERROR: No unused OTP found matching this code for this user.")
        return Response({"error": "Invalid or already used code."}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['DELETE'])
@permission_classes([IsAdminRole])
def delete_user(request, user_id):
    """
    Deletes a user from the system based on their UUID.
    """
    try:
        user = CustomUser.objects.get(id=user_id)
        user_email = user.email  # Save for the success message
        user.delete()

        print(f"---> Successfully deleted user: {user_email}")
        return Response(
            {"message": f"User {user_email} has been deleted."},
            status=status.HTTP_204_NO_CONTENT
        )

    except CustomUser.DoesNotExist:
        print(f"---> ERROR: Attempted to delete non-existent user ID: {user_id}")
        return Response(
            {"error": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )


def apply_agent_identity(data, user):
    """Stamp the authenticated agent + their brokerage onto RE-21 form data from
    the database (CustomUser + its Organization), unless the form already
    specified them. The DB is the source of truth; settings.DEFAULT_SELLING_*
    remain a fallback inside the PDF mapper for unauthenticated previews."""
    if not isinstance(data, dict) or not getattr(user, "is_authenticated", False):
        return data
    full_name = f"{user.first_name} {user.last_name}".strip()
    if full_name and not data.get("sellingAgent"):
        data["sellingAgent"] = full_name
    if getattr(user, "phone_number", None) and not data.get("sellingAgentPhone"):
        data["sellingAgentPhone"] = user.phone_number
    org = getattr(user, "organization", None)
    if org and getattr(org, "name", None) and not data.get("sellingBrokerage"):
        data["sellingBrokerage"] = org.name
    return data


class DocumentPreviewEndpoint(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, doc_type, *args, **kwargs):
        # 1. Grab the JSON payload sent from iOS
        form_data = request.data
        # Stamp the agent/brokerage from the DB when a valid token is present.
        apply_agent_identity(form_data, request.user)

        try:
            # 2. Initialize the service with the specific document type
            # The PDFGenerationService now handles finding the correct template internally
            pdf_service = PDFGenerationService(doc_type=doc_type)
            pdf_bytes = pdf_service.generate_pdf(form_data)

            # 3. Return the file directly to the iOS app with a dynamic name
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{doc_type}_Preview.pdf"'
            return response

        except FileNotFoundError as e:
            return Response({"error": str(e)}, status=404)
        except ValueError as e:
            return Response({"error": str(e)}, status=400) # Catches invalid doc_types
        except Exception as e:
            return Response({"error": f"Failed to generate PDF: {str(e)}"}, status=500)


class OnboardingBundlePreviewEndpoint(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        payload = request.data or {}

        # 🚀 1. DEBUG LOG: Print incoming keys to see exact structure from Swift
        print("\n=== 📦 BUNDLE PREVIEW PAYLOAD DEBUG ===")
        print(f"Raw Request Data: {payload}")
        print(f"Payload Keys Received: {list(payload.keys()) if isinstance(payload, dict) else type(payload)}")
        print("=======================================\n")

        if not isinstance(payload, dict):
            return Response({"error": "Invalid payload format. Expected a JSON dictionary."}, status=400)

        # 🚀 2. HELPER: Look for keys in both camelCase and snake_case
        def extract_form_data(keys):
            for k in keys:
                if k in payload and isinstance(payload[k], dict):
                    return payload[k]
            return None

        agency_data = extract_form_data(["agencyDisclosure", "agency_disclosure", "agency"])
        re14_data = extract_form_data(["re14", "re_14"])
        re21_data = extract_form_data(["re21", "re_21"])

        # If re21 wasn't nested under a key, check if payload ITSELF is the RE21 dictionary
        if agency_data is None and re14_data is None and re21_data is None:
            print("💡 [BUNDLE PREVIEW] Flat payload detected! Generating Agency, RE-14, and RE-21 from flat data.")
            agency_data = payload
            re14_data = payload
            re21_data = payload

        # 4. Build document list based on populated data
        documents_to_generate = []
        if agency_data is not None:
            documents_to_generate.append((DocumentType.AGENCY_DISCLOSURE, agency_data))
        if re14_data is not None:
            documents_to_generate.append((DocumentType.RE_14, re14_data))
        if re21_data is not None:
            documents_to_generate.append((DocumentType.RE_21, re21_data))

        # 🚀 5. FALLBACK: If no keys matched, default to generating all 3 forms with whatever data exists
        if not documents_to_generate:
            print("⚠️ No matching document keys found in payload. Defaulting to all 3 forms.")
            documents_to_generate = [
                (DocumentType.AGENCY_DISCLOSURE, agency_data or {}),
                (DocumentType.RE_14, re14_data or {}),
                (DocumentType.RE_21, re21_data or payload),
            ]

        try:
            merged_pdf = pymupdf.open()

            for doc_type, data in documents_to_generate:
                apply_agent_identity(data, request.user)
                pdf_service = PDFGenerationService(doc_type=doc_type)
                pdf_bytes = pdf_service.generate_pdf(data)

                if not pdf_bytes:
                    continue

                temp_doc = pymupdf.open("pdf", pdf_bytes)

                # Flatten widgets before inserting to prevent AcroForm collisions
                for page in temp_doc:
                    if hasattr(page, "bake"):
                        page.bake()

                merged_pdf.insert_pdf(temp_doc)
                temp_doc.close()

            # 🚀 6. SAFEGUARD: Ensure pages exist before calling tobytes()
            if merged_pdf.page_count == 0:
                merged_pdf.close()
                return Response({"error": "No pages were generated for the bundle preview."}, status=400)

            final_bytes = merged_pdf.tobytes(garbage=4, deflate=True)
            merged_pdf.close()

            response = HttpResponse(final_bytes, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="Onboarding_Preview.pdf"'
            return response

        except Exception as e:
            print(f"🚨 Bundle generation error: {str(e)}")
            return Response({"error": f"Failed to generate bundle: {str(e)}"}, status=500)


# 🟢 NEW BUNDLE SIGNATURE ENDPOINT
class SendOnboardingBundleEndpoint(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        payload = request.data

        # 1. Extract buyers list from request
        raw_buyers = payload.get("buyers", [])
        if not raw_buyers:
            return Response({"error": "At least one buyer is required."}, status=400)

        # 2. Extract form payloads — only the documents whose key is PRESENT are
        # generated, so the app's form-selection pills control the packet.
        bundled_data = {}
        for doc_type, key in ((DocumentType.AGENCY_DISCLOSURE, "agencyDisclosure"),
                              (DocumentType.RE_14, "re14"),
                              (DocumentType.RE_21, "re21")):
            if isinstance(payload.get(key), dict):
                bundled_data[doc_type] = payload[key]

        # Legacy flat payload (no keyed documents): full packet from the flat data,
        # mirroring the preview endpoint's flat fallback.
        if not bundled_data:
            bundled_data = {
                DocumentType.AGENCY_DISCLOSURE: payload,
                DocumentType.RE_14: payload,
                DocumentType.RE_21: payload,
            }

        # Who owns this deal? The sender — unless a TC/team admin is sending on
        # behalf of an agent on their team (`agent_id`). Identity stamped on
        # the contracts is always the OWNER's, never the TC's.
        owner = request.user
        for_agent_id = payload.get("agent_id")
        if for_agent_id and str(for_agent_id) != str(request.user.id):
            if not is_team_role(request.user):
                return Response({"error": "Only a TC or team admin can send on another agent's behalf."}, status=403)
            owner = CustomUser.objects.filter(
                id=for_agent_id, organization_id=request.user.organization_id
            ).first()
            if owner is None:
                return Response({"error": "That agent isn't on your team."}, status=400)

        for doc_payload in bundled_data.values():
            apply_agent_identity(doc_payload, owner)

        try:
            # 3. Call your multi-document bundle method
            ds_service = DocuSignService()
            result = ds_service.send_bundle_envelope(
                bundled_data=bundled_data,
                buyers=raw_buyers
            )

            envelope_id = result.get("envelope_id")
            # Every doc payload carries the same form data, so any included doc
            # can supply the address if the RE-21 was deselected.
            re21_data = bundled_data.get(DocumentType.RE_21) \
                or next(iter(bundled_data.values()), {})
            property_address = re21_data.get("propertyAddress", "Unknown Address")
            buyer_names = ", ".join([b.get("name", "") for b in raw_buyers])
            primary_buyer = raw_buyers[0]

            # 4. Store the unsigned packet on S3 so the deal has a draft copy
            # (and the CRM note below has something to link to).
            draft_path = None
            try:
                merged = pymupdf.open()
                for _doc_type, pdf_bytes in result.get("document_bytes", []):
                    part = pymupdf.open("pdf", pdf_bytes)
                    merged.insert_pdf(part)
                    part.close()
                if merged.page_count:
                    draft_path = default_storage.save(
                        f"drafts/packet_{envelope_id}.pdf",
                        ContentFile(merged.tobytes(garbage=4, deflate=True))
                    )
                merged.close()
            except Exception as e:
                print(f"Draft packet S3 save failed (non-fatal): {e}")

            # 5. Save/Update Deal in Postgres
            deal = Deal.objects.create(
                agent=owner,
                docusign_envelope_id=envelope_id,
                property_address=property_address,
                buyer_names=buyer_names,
                buyer_email=primary_buyer.get("email") or None,
                draft_pdf_url=draft_path,
                form_snapshot=re21_data,   # server-side copy → any device can revise
                status='out_for_signature'
            )

            # 6. CRM sync — the packet appears on the buyer's FUB timeline.
            # Never blocks the send: sync_document swallows its own failures.
            doc_list = ", ".join(
                dt.upper().replace("_", "-") for dt, _ in result.get("document_bytes", [])
            )
            link_html = ""
            if draft_path:
                try:
                    link_html = f'<p>📄 <a href="{default_storage.url(draft_path)}" target="_blank">View the packet</a></p>'
                except Exception:
                    pass
            if fub_service.sync_document(
                owner,
                buyer_name=primary_buyer.get("name", buyer_names),
                buyer_email=primary_buyer.get("email", ""),
                subject=f"Offer packet sent for signature — {property_address}",
                body_html=(
                    f"<p><strong>Apex Integrations AI</strong>: offer packet sent to "
                    f"{buyer_names} for signature.</p>"
                    f"<p>Property: {property_address}<br>Documents: {doc_list}</p>{link_html}"
                ),
            ):
                deal.fub_synced = True
                deal.save(update_fields=["fub_synced"])

            return Response({
                "status": "sent",
                "envelope_id": envelope_id,
                "deal_id": deal.id
            }, status=200)

        except Exception as e:
            return Response({"error": f"Failed to send bundle: {str(e)}"}, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def docusign_webhook(request):
    print("\n================ 📡 WEBHOOK HIT ================")

    try:
        data = request.data
        event = data.get("event")
        print(f"📊 [TRACE 1] Received Webhook Event: '{event}'")

        if event == "envelope-completed":
            envelope_id = data.get("data", {}).get("envelopeId")
            print(f"📂 [TRACE 2] Envelope {envelope_id} is FULLY SIGNED!")

            documents = data.get("data", {}).get("envelopeSummary", {}).get("envelopeDocuments", [])
            print(f"📊 [TRACE 3] Found {len(documents)} document(s) in payload.")

            if not documents:
                print("⚠️ [TRACE 3a] No documents array found in DocuSign payload!")
                return Response({"status": "error", "message": "No documents provided"}, status=400)

            # Merge EVERY signed document in the envelope (agency disclosure,
            # RE-14, RE-21, …) into one PDF — taking only documents[0] dropped
            # all but the first form from the stored packet. DocuSign's
            # certificate-of-completion summary doc is skipped.
            merged_pdf = pymupdf.open()
            merged_count = 0
            try:
                for doc_info in documents:
                    if str(doc_info.get("documentId", "")).lower() == "certificate" \
                            or str(doc_info.get("type", "")).lower() == "summary":
                        continue
                    doc_b64 = doc_info.get("PDFBytes")
                    if not doc_b64:
                        continue
                    part = pymupdf.open("pdf", base64.b64decode(doc_b64))
                    merged_pdf.insert_pdf(part)
                    part.close()
                    merged_count += 1

                # 💡 THE HIDDEN CRASH TRAP:
                # If "Include Document PDFs" is not checked in DocuSign Connect, PDFBytes is None!
                if merged_count == 0:
                    print("🚨 [CRASH CAUGHT] No PDFBytes on any document! DocuSign Connect is not sending file bytes.")
                    print("👉 Fix: In DocuSign Admin -> Connect, make sure 'Include Document PDFs' is CHECKED.")
                    return Response({"status": "error", "message": "Missing PDFBytes"}, status=400)

                pdf_bytes = merged_pdf.tobytes(garbage=4, deflate=True)
            finally:
                merged_pdf.close()
            print(f"📊 [TRACE 4-5] Merged {merged_count} signed document(s) into one PDF (Size: {len(pdf_bytes)} bytes)")

            # S3 File Upload
            s3_filename = f"signed_contracts/signed_re21_{envelope_id}.pdf"
            print(f"📊 [TRACE 6] Attempting S3 storage save to path: '{s3_filename}'")

            try:
                saved_path = default_storage.save(s3_filename, ContentFile(pdf_bytes))
                print(f"💾 [TRACE 7] S3 Upload successful! File saved at: '{saved_path}'")
            except Exception as s3_err:
                print("🚨 [CRASH CAUGHT] AWS S3 Upload failed! Check your AWS credentials or bucket permissions.")
                raise s3_err

            # Postgres Database Lookup
            print(f"📊 [TRACE 8] Querying Postgres for Deal with envelope_id: '{envelope_id}'")
            try:
                deal = Deal.objects.get(docusign_envelope_id=envelope_id)
                print(f"📊 [TRACE 9] Match found! Deal ID: {deal.id}. Address: {deal.property_address}")
                deal.status = 'fully_executed'
                deal.signed_pdf_url = saved_path
                if deal.acceptance_date is None:
                    deal.acceptance_date = timezone.now()
                deal.save()
                print("✅ [TRACE 10] Postgres database update successful!")

                # CRM sync — the fully executed packet lands on the buyer's
                # FUB timeline. Non-fatal by design.
                try:
                    signed_link = default_storage.url(saved_path)
                except Exception:
                    signed_link = None
                link_html = (
                    f'<p>📄 <a href="{signed_link}" target="_blank">View the executed packet</a></p>'
                    if signed_link else ""
                )
                if fub_service.sync_document(
                    deal.agent,
                    buyer_name=deal.buyer_names,
                    buyer_email=deal.buyer_email or "",
                    subject=f"Contract fully executed — {deal.property_address}",
                    body_html=(
                        f"<p><strong>Apex Integrations AI</strong>: all parties have signed.</p>"
                        f"<p>Property: {deal.property_address}<br>Buyer(s): {deal.buyer_names}</p>{link_html}"
                    ),
                ):
                    deal.fub_synced = True
                    deal.save(update_fields=["fub_synced"])

            except Deal.DoesNotExist:
                # Not the packet — maybe a DealDocument's envelope (counter,
                # RE-10…): store its signed file and mark it signed.
                doc = DealDocument.objects.filter(docusign_envelope_id=envelope_id).first()
                if doc is not None:
                    doc.signed_pdf_key = saved_path
                    doc.status = 'signed'
                    doc.save(update_fields=['signed_pdf_key', 'status'])
                    print(f"✅ DealDocument {doc.id} ('{doc.title}') signed for deal {doc.deal_id}")
                    return Response({"status": "received"}, status=200)
                print(f"⚠️ [TRACE 9-WARN] No matching Deal row in database has docusign_envelope_id='{envelope_id}'")
                print(
                    "💡 Pro Tip: If you sent this via the DocuSign web dashboard instead of the iOS app, no DB row will match!")
                return Response({"status": "received_no_db_match"}, status=200)

            # Pusher Live Sync
            channel_name = f"deal_{deal.id}"
            print(f"📊 [TRACE 11] Attempting Pusher broadcast to channel '{channel_name}'...")

            try:
                pusher_client.trigger(
                    channel_name,
                    're-21_signed',
                    {
                        'envelope_id': envelope_id,
                        'status': 'fully_executed',
                        'signed_pdf_url': saved_path
                    }
                )
                print("📡 [TRACE 12] Pusher notification successfully broadcasted!")
            except Exception as push_err:
                print("🚨 [CRASH CAUGHT] Pusher broadcast failed! Check your keys or connection limits.")
                raise push_err

        else:
            print(f"ℹ️ [INFO] Ignoring non-completed event type: '{event}'")

        print("================ 📡 WEBHOOK SUCCESS ================ \n")
        return Response({"status": "received"}, status=200)

    except Exception as e:
        # 🚨 THE ULTIMATE SAFETY NET: Print exactly what and where the code crashed!
        print("\n❌❌❌❌ [WEBHOOK CRITICAL RUNTIME CRASH] ❌❌❌❌")
        print(f"Error Message: {str(e)}")
        print("---------------- Traceback Details ----------------")
        traceback.print_exc()  # Prints the exact line of code that failed
        print("---------------------------------------------------\n")
        return Response({"status": "error", "message": str(e)}, status=500)


class RE21ContractStatusEndpoint(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, envelope_id, *args, **kwargs):
        """
        GET /api/contracts/status/<envelope_id>/
        Checks if the contract is signed and returns the status.
        """
        # Only envelopes on deals this user can see (own, or team for TC/admin).
        if not deals_for(request.user).filter(docusign_envelope_id=envelope_id).exists():
            return Response({"error": "Not found."}, status=404)
        try:
            ds_service = DocuSignService()

            # 1. Fetch Envelope Details from DocuSign
            # We'll use the SDK's built-in call to check status
            access_token = ds_service._get_access_token()
            api_client = ApiClient()
            api_client.host = ds_service.base_path
            api_client.set_default_header("Authorization", f"Bearer {access_token}")

            envelopes_api = EnvelopesApi(api_client)
            envelope = envelopes_api.get_envelope(
                account_id=ds_service.account_id,
                envelope_id=envelope_id
            )

            current_status = envelope.status  # e.g., 'sent', 'delivered', 'completed'

            # 2. If completed, make sure we have the file
            if current_status == "completed":
                # Check if we already have it in media/
                file_name = f"signed_re21_{envelope_id}.pdf"
                file_path = os.path.join('media', 'signed_contracts', file_name)

                if not os.path.exists(file_path):
                    # Manual Pull Triggered
                    pdf_bytes = ds_service.download_envelope_document(envelope_id)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, "wb") as f:
                        f.write(pdf_bytes)

            return Response({
                "envelope_id": envelope_id,
                "status": current_status,
                "is_completed": current_status == "completed",
                "pdf_url": f"/media/signed_contracts/signed_re21_{envelope_id}.pdf" if current_status == "completed" else None
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)


class AgentDealsListCreateView(ListCreateAPIView):
    serializer_class = DealSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Role-based: agents see their own deals; TCs/team admins see the team's.
        return deals_for(self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        """
        When the app sends a POST to this endpoint, automatically
        tie the new Deal to the currently authenticated Agent.
        """
        serializer.save(agent=self.request.user)


class DealDocumentsView(APIView):
    """GET  /api/deals/<pk>/documents/   — the deal's document trail.
    POST /api/deals/<pk>/documents/   — attach a file (multipart: file,
    doc_type, title?, direction?). Counters (doc_type re_13) auto-number."""
    permission_classes = [IsAuthenticated]

    def get_deal(self, request, pk):
        return deals_for(request.user).filter(pk=pk).first()

    def get(self, request, pk):
        deal = self.get_deal(request, pk)
        if deal is None:
            return Response({"error": "Not found."}, status=404)
        docs = deal.documents.order_by('-created_at')
        return Response(DealDocumentSerializer(docs, many=True).data)

    def post(self, request, pk):
        deal = self.get_deal(request, pk)
        if deal is None:
            return Response({"error": "Not found."}, status=404)
        upload = request.FILES.get('file')
        if upload is None:
            return Response({"error": "Missing file."}, status=400)
        if upload.size > 25 * 1024 * 1024:
            return Response({"error": "File too large (25 MB max)."}, status=400)

        doc_type = (request.data.get('doc_type') or 'other').strip()
        direction = (request.data.get('direction') or 'received').strip()
        sequence = deal.documents.filter(doc_type=doc_type).count() + 1
        default_title = f"Counter Offer #{sequence}" if doc_type == 're_13' else (upload.name or "Document")
        title = (request.data.get('title') or default_title).strip()

        import uuid as _uuid
        safe_name = (upload.name or 'document.pdf').replace('/', '_')
        key = default_storage.save(f"deal_documents/{deal.id}/{_uuid.uuid4().hex[:8]}_{safe_name}",
                                   ContentFile(upload.read()))
        doc = DealDocument.objects.create(
            deal=deal, doc_type=doc_type, title=title, direction=direction,
            sequence=sequence, status='received', pdf_key=key,
        )
        return Response(DealDocumentSerializer(doc).data, status=201)


class DealStateView(APIView):
    """GET   /api/deals/<pk>/state/  → {checklist_state, form_snapshot, acceptance_date}
    PATCH /api/deals/<pk>/state/  with any subset. `checklist_state` MERGES by
    task key so the agent's phone and the TC portal never clobber each other."""
    permission_classes = [IsAuthenticated]

    def _deal(self, request, pk):
        return deals_for(request.user).filter(pk=pk).first()

    def _payload(self, deal):
        return {
            "checklist_state": deal.checklist_state or {},
            "form_snapshot": deal.form_snapshot,
            "acceptance_date": deal.acceptance_date,
        }

    def get(self, request, pk):
        deal = self._deal(request, pk)
        if deal is None:
            return Response({"error": "Not found."}, status=404)
        return Response(self._payload(deal))

    def patch(self, request, pk):
        deal = self._deal(request, pk)
        if deal is None:
            return Response({"error": "Not found."}, status=404)
        fields = []
        if isinstance(request.data.get("checklist_state"), dict):
            merged = dict(deal.checklist_state or {})
            merged.update({str(k): str(v) for k, v in request.data["checklist_state"].items()})
            deal.checklist_state = merged
            fields.append("checklist_state")
        if "form_snapshot" in request.data and isinstance(request.data["form_snapshot"], dict):
            deal.form_snapshot = request.data["form_snapshot"]
            fields.append("form_snapshot")
        if "acceptance_date" in request.data and request.data["acceptance_date"]:
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(str(request.data["acceptance_date"]))
            if parsed is not None:
                deal.acceptance_date = parsed
                fields.append("acceptance_date")
        if fields:
            deal.save(update_fields=fields)
        return Response(self._payload(deal))


class DealArchiveView(APIView):
    """POST /api/deals/<pk>/archive/ with {"archived": true|false}.
    Archived deals leave the active pipeline; delete stays a separate,
    deliberate second step (and still voids in-flight envelopes)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        deal = deals_for(request.user).filter(pk=pk).first()
        if deal is None:
            return Response({"error": "Not found."}, status=404)
        deal.is_archived = bool(request.data.get("archived", True))
        deal.save(update_fields=["is_archived"])
        return Response({"id": deal.id, "is_archived": deal.is_archived})


class DealDetailEndpoint(RetrieveDestroyAPIView):
    """
    GET    /api/deals/<id>/  — fetch a single deal's full state.
    DELETE /api/deals/<id>/  — delete the deal and its S3 files.
    """
    serializer_class = DealSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # SECURITY: own deals for agents; the team's deals for TCs/admins.
        return deals_for(self.request.user)

    def perform_destroy(self, instance):
        # Capture what cleanup needs, then delete the ROW FIRST — the DocuSign
        # void takes seconds, and while it ran the deal used to still exist,
        # so a concurrent pipeline refresh would resurrect it in the UI.
        envelope_id = instance.docusign_envelope_id
        deal_status = instance.status
        deal_id = instance.id
        file_keys = [k for k in (instance.draft_pdf_url, instance.signed_pdf_url) if k]
        instance.delete()

        # Void the in-flight DocuSign envelope so nobody can sign the
        # outdated version. Never let a DocuSign hiccup fail the deletion —
        # the row is already gone.
        if envelope_id and deal_status in ('out_for_signature', 'signed_by_buyers'):
            try:
                DocuSignService().void_envelope(envelope_id)
                print(f"Voided envelope {envelope_id} for deleted deal {deal_id}")
            except Exception as e:
                print(f"Failed to void envelope {envelope_id}: {e}")

        # Clean up the draft + signed PDFs from S3.
        for key in file_keys:
            try:
                default_storage.delete(key)
            except Exception as e:
                print(f"Failed to delete {key} from S3: {e}")


User = get_user_model()


class FUBConnectURLView(APIView):
    """GET /api/auth/fub/connect-url/ — returns the FUB authorize URL with a
    signed state bound to the requesting agent. The app opens it in Safari."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"url": fub_service.make_connect_url(request.user)})


class FUBStatusView(APIView):
    """GET    /api/auth/fub/status/ — is this agent's FUB connected (server truth)?
    DELETE /api/auth/fub/status/ — disconnect: clear the stored tokens."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"connected": bool(request.user.fub_access_token)})

    def delete(self, request):
        user = request.user
        user.fub_access_token = None
        user.fub_refresh_token = None
        user.save(update_fields=["fub_access_token", "fub_refresh_token"])
        return Response({"connected": False})


class FUBBackfillView(APIView):
    """POST /api/auth/fub/backfill/ — sync any of the agent's not-yet-synced
    deals to FUB. The connect flow runs this automatically; this endpoint
    exists for manual catch-ups."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.fub_access_token:
            return Response({"error": "Follow Up Boss is not connected."}, status=400)
        count = fub_service.backfill_deals(request.user)
        return Response({"synced": count})


class FUBAuthCallbackView(APIView):
    permission_classes = []

    def custom_redirect(self, url):
        response = HttpResponse(status=302)
        response['Location'] = url
        return response

    def get(self, request, *args, **kwargs):
        try:
            code = request.GET.get('code')
            state = request.GET.get('state')

            if not code or not state:
                return self.custom_redirect('apexapp://fub-callback?status=error&message=missing_params')

            # The signed state proves which agent started this flow — a raw
            # user id here would let anyone bind their FUB account to another
            # agent's Apex account.
            from django.core import signing as dj_signing
            try:
                user_id = fub_service.user_id_from_state(state)
            except dj_signing.BadSignature:
                return self.custom_redirect('apexapp://fub-callback?status=error&message=bad_state')

            data = fub_service.exchange_code(code, state)

            user = User.objects.filter(id=user_id).first()
            if not user:
                return self.custom_redirect('apexapp://fub-callback?status=error&message=user_not_found')

            user.fub_access_token = data.get("access_token")
            user.fub_refresh_token = data.get("refresh_token")
            user.save(update_fields=["fub_access_token", "fub_refresh_token"])
            print(f"✅ FUB connected for {user.email}")

            # Catch the CRM up on the agent's existing pipeline.
            count = fub_service.backfill_deals(user)
            print(f"FUB backfill: synced {count} existing deal(s) for {user.email}")

            return self.custom_redirect('apexapp://fub-callback?status=success')

        except Exception as e:
            print(f"🚨 FUB OAuth error: {str(e)}")
            error_msg = urllib.parse.quote(str(e))
            return self.custom_redirect(f'apexapp://fub-callback?status=error&message=exchange_failed&details={error_msg}')


class FUBSendDocumentView(APIView):
    # Only logged-in agents using your iOS app can hit this
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        fub_token = user.fub_access_token

        if not fub_token:
            return Response({"error": "Follow Up Boss is not connected to this account."}, status=400)

        # 1. Grab the raw data from the iOS app
        data = request.data
        email = data.get('email', '')
        name = data.get('name', 'Unknown Client')
        phone = data.get('phone', '')
        s3_url = data.get('s3Url')
        filename = data.get('filename')

        # The FUB Bearer Token Header!
        headers = {
            "Authorization": f"Bearer {fub_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-System": "Docu-Flow-AI"
        }

        person_id = None

        # STEP 1: Find Person by Email
        if email:
            search_url = f"https://api.followupboss.com/v1/people?email={urllib.parse.quote(email)}"
            search_res = requests.get(search_url, headers=headers, timeout=15)
            if search_res.status_code == 200:
                people = search_res.json().get('people', [])
                if people:
                    person_id = people[0]['id']

        # STEP 2: Create Person (if not found)
        if not person_id:
            create_url = "https://api.followupboss.com/v1/people"
            name_parts = name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            payload = {
                "firstName": first_name,
                "source": "Apex Integrations AI"
            }
            if last_name: payload["lastName"] = last_name
            if email: payload["emails"] = [{"value": email}]
            if phone: payload["phones"] = [{"value": phone}]

            create_res = requests.post(create_url, json=payload, headers=headers, timeout=15)
            if create_res.status_code in [200, 201]:
                person_id = create_res.json().get('id')
            else:
                return Response({"error": "Failed to create FUB contact", "details": create_res.text}, status=400)

        # STEP 3: Add the Document Note
        note_url = "https://api.followupboss.com/v1/notes"
        note_body = f"""
        <p><strong>Apex Integrations AI</strong> generated a new RE-21 offer.</p>
        <p>📄 <a href="{s3_url}" target="_blank">Click here to view {filename}</a></p>
        """

        note_payload = {
            "personId": person_id,
            "subject": "RE-21 Document Generated",
            "body": note_body,
            "isHtml": True
        }

        note_res = requests.post(note_url, json=note_payload, headers=headers, timeout=15)

        if note_res.status_code in [200, 201]:
            return Response({"status": "success", "personId": person_id})
        else:
            return Response({"error": "Failed to add note to FUB", "details": note_res.text}, status=400)


logger = logging.getLogger(__name__)


class DistributeExecutedPacketEndpoint(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        payload = request.data
        envelope_id = payload.get("envelope_id")
        title_email = payload.get("title_email", "").strip()
        lender_email = payload.get("lender_email", "").strip()
        property_address = payload.get("property_address", "").strip()

        if not envelope_id:
            return Response({"error": "Missing envelope_id"}, status=400)
        # Only packets from deals this user can see (own, or team for TC/admin).
        if not deals_for(request.user).filter(docusign_envelope_id=envelope_id).exists():
            return Response({"error": "Not found."}, status=404)
        if not property_address:
            return Response({"error": "Missing property_address"}, status=400)
        if not title_email and not lender_email:
            return Response({"error": "At least one destination email (Title or Lender) is required"}, status=400)

        try:
            # 1. Download the fully signed combined PDF from DocuSign
            logger.info(f"📥 Downloading executed packet for envelope {envelope_id}...")
            ds_service = DocuSignService()
            pdf_bytes = ds_service.download_envelope_document(envelope_id)

            # 2. Build the distribution email targets
            destinations = []
            if title_email: destinations.append(title_email)
            if lender_email: destinations.append(lender_email)

            # 3. Use Django's native EmailMessage to forward the file
            email = EmailMessage(
                subject="EXECUTED CONTRACT PACKET - 123 Main St",
                body=f"Hello,\n\nPlease find attached the fully executed contract packet for the purchase of {property_address}.\n\nThank you,\nApex Automated Transaction Coordinator",
                from_email="coordinator@apexintegrations.ai",
                to=destinations
            )

            # Attach the raw PDF bytes cleanly
            email.attach("Executed_Contract_Packet.pdf", pdf_bytes, "application/pdf")
            email.send(fail_silently=False)

            logger.info(f"✅ Executed packet cleanly delivered to: {', '.join(destinations)}")
            return Response({"status": "distributed", "delivered_to": destinations}, status=200)

        except Exception as e:
            logger.error(f"❌ Failed to distribute executed packet: {str(e)}")
            return Response({"error": f"Distribution failed: {str(e)}"}, status=500)


def mls_reso_query(filter_expr, top=1):
    """
    Run a RESO Property query against the company's MLS (RESO Web API) and return
    (records, error_response). On success error_response is None; on failure
    records is None and error_response is a ready DRF Response.

    The company holds ONE MLS credential (every app user is a licensed agent =
    standard back-office use); it lives here on the server, never in the app.
    Env: MLS_API_BASE_URL, MLS_API_TOKEN (rets.io authenticates via ?access_token).
    """
    base_url = (getattr(settings, 'MLS_API_BASE_URL', '') or '').strip()
    token = (getattr(settings, 'MLS_API_TOKEN', '') or '').strip()
    if not base_url or not token:
        return None, Response(
            {"detail": "MLS integration is not configured on the server."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    endpoint = f"{base_url.rstrip('/')}/Property"
    params = {
        "$filter": filter_expr,
        "$top": top,
        "access_token": token,  # rets.io (and many RESO hosts) authenticate via query param
    }
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",  # also send Bearer for hosts that expect the header
    }

    try:
        resp = requests.get(endpoint, params=params, headers=headers, timeout=15)
    except requests.exceptions.Timeout:
        return None, Response({"detail": "The MLS request timed out."},
                              status=status.HTTP_504_GATEWAY_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        logging.error("MLS request failed: %s", exc)
        return None, Response({"detail": "Could not reach the MLS."},
                              status=status.HTTP_502_BAD_GATEWAY)

    if resp.status_code in (401, 403):
        logging.error("MLS auth rejected (%s): %s", resp.status_code, resp.text[:500])
        return None, Response({"detail": "The MLS rejected the server credential.",
                               "upstream_status": resp.status_code,
                               "upstream_body": resp.text[:400]},
                              status=status.HTTP_502_BAD_GATEWAY)

    if resp.status_code != 200:
        logging.error("MLS returned %s: %s", resp.status_code, resp.text[:500])
        return None, Response({"detail": f"MLS returned status {resp.status_code}.",
                               "upstream_body": resp.text[:400]},
                              status=status.HTTP_502_BAD_GATEWAY)

    try:
        payload = resp.json()
    except ValueError:
        return None, Response({"detail": "MLS returned an unreadable response."},
                              status=status.HTTP_502_BAD_GATEWAY)

    records = payload.get("value", []) if isinstance(payload, dict) else []
    return records, None


class MLSListingProxyView(APIView):
    """
    Broker back-office MLS lookup by MLS number.
        GET /api/mls/listing/<mls_number>/
    Returns the RESO envelope { "value": [record] } for the iOS app to decode.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, mls_number):
        raw_number = (mls_number or '').strip()
        if not raw_number:
            return Response({"detail": "Missing MLS number."},
                            status=status.HTTP_400_BAD_REQUEST)

        id_field = (getattr(settings, 'MLS_LISTING_ID_FIELD', 'ListingId') or 'ListingId').strip()
        safe_number = raw_number.replace("'", "''")  # OData escapes single quotes by doubling

        records, error = mls_reso_query(f"{id_field} eq '{safe_number}'", top=1)
        if error is not None:
            return error
        if not records:
            return Response({"detail": f"No listing found for MLS #{raw_number}."},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({"value": records[:1]}, status=status.HTTP_200_OK)


class MLSAddressSearchView(APIView):
    """
    Broker back-office MLS search by street address.
        GET /api/mls/search/?address=<address>
    Case-insensitive substring match on UnparsedAddress. Returns the RESO envelope
    { "value": [records] } (possibly empty — the app shows "not listed for sale").
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address = (request.GET.get('address', '') or '').strip()
        if not address:
            return Response({"detail": "Missing address."},
                            status=status.HTTP_400_BAD_REQUEST)

        safe = address.replace("'", "''")
        # Match the street address OR the city, so "Idaho Falls" returns every
        # listing in that city (UnparsedAddress usually embeds the city, but the
        # City field is the authoritative match for city-wide searches).
        filter_expr = (
            f"contains(tolower(UnparsedAddress),tolower('{safe}')) "
            f"or contains(tolower(City),tolower('{safe}'))"
        )
        records, error = mls_reso_query(filter_expr, top=50)
        if error is not None:
            return error
        # Empty is a valid "no active listing at that address" result, not an error.
        return Response({"value": records}, status=status.HTTP_200_OK)
