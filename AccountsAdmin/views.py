import base64
import os
import urllib
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from docusign_esign import EnvelopesApi, ApiClient
from rest_framework.generics import ListAPIView, DestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
import requests
from django.shortcuts import redirect

from .docusign_service import DocuSignService
from .pdf_service import PDFGenerationService
# Create your views here.

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Organization, CustomUser, OTPCode, Deal
from .serializers import OrganizationSerializer, CustomUserSerializer, DealSerializer
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse


def landing_page(request):
    return render(request, 'landing_page.html')


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
@permission_classes([IsAuthenticated])
def organization_list(request):
    """
    List all organizations
    """
    organizations = Organization.objects.all()
    serializer = OrganizationSerializer(organizations, many=True)
    return Response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
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
    if email.lower() == 'ianschoenrock@gmail.com':
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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
    if email.lower() == 'ianschoenrock@gmail.com' and code == '000000':
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
@permission_classes([IsAuthenticated])
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


class RE21PreviewEndpoint(APIView):
    def post(self, request, *args, **kwargs):
        # 1. Grab the JSON payload sent from iOS
        form_data = request.data

        # 2. Define where the blank template lives on your server
        # Make sure you put re21_2026.pdf in your static or media folder
        template_path = os.path.join(settings.BASE_DIR, 'static', 'pdfs', 're21_2026.pdf')
        try:
            # 3. Initialize the service and generate the binary PDF data
            pdf_service = PDFGenerationService(template_path)
            pdf_bytes = pdf_service.generate_pdf(form_data)

            # 4. Return the file directly to the iOS app
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="RE21_Preview.pdf"'
            return response

        except FileNotFoundError as e:
            return Response({"error": str(e)}, status=404)
        except Exception as e:
            return Response({"error": f"Failed to generate PDF: {str(e)}"}, status=500)


class RE21CreateSignatureLinkEndpoint(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        form_data = request.data
        template_path = os.path.join(settings.BASE_DIR, 'static', 'pdfs', 're21_2026.pdf')

        try:
            # 1. Generate the PDF
            pdf_service = PDFGenerationService(template_path)
            pdf_bytes = pdf_service.generate_pdf(form_data)

            # 2. Extract Data for the Database
            raw_buyer_name = form_data.get("buyerName", "Test Buyer")
            buyer_names = [n.strip() for n in raw_buyer_name.split(" and ")]
            primary_email = form_data.get("buyerEmail", "test@example.com")
            property_address = form_data.get("propertyAddress", "Unknown Address")

            # 3. Upload Draft to AWS S3
            # We use a short UUID so if you do 10 offers for "123 Main St", they don't overwrite each other
            file_id = uuid.uuid4().hex[:8]
            s3_filename = f"drafts/re21_{file_id}.pdf"

            # This pushes the bytes to S3 and returns the clean path: "drafts/re21_1234.pdf"
            saved_path = default_storage.save(s3_filename, ContentFile(pdf_bytes))

            # 4. Create the Deal in Postgres
            deal = Deal.objects.create(
                agent=request.user,
                property_address=property_address,
                buyer_names=raw_buyer_name,
                status='out_for_signature',
                draft_pdf_url=saved_path
            )

            # 5. Send to DocuSign
            buyers_list = [{"name": name, "email": primary_email} for name in buyer_names]
            ds_service = DocuSignService()
            result = ds_service.send_envelope(
                pdf_bytes=pdf_bytes,
                buyers=buyers_list
            )

            # 6. Update the Deal with the Envelope ID
            deal.docusign_envelope_id = result.get("envelope_id")
            deal.save()

            # Return success to Swift, including the S3 URL for your debugging
            return Response({
                "status": "sent",
                "envelope_id": deal.docusign_envelope_id,
                "deal_id": deal.id,
                "draft_url": saved_path
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])  # DocuSign needs to hit this without a login
def docusign_webhook(request):
    data = request.data

    # 1. Check the status
    event = data.get("event")
    if event == "envelope-completed":
        envelope_id = data.get("data", {}).get("envelopeId")
        print(f"DEBUG: Envelope {envelope_id} is FULLY SIGNED!")

        # 2. Extract the signed PDF
        # DocuSign Connect can be configured to include the document as a base64 string
        documents = data.get("data", {}).get("envelopeSummary", {}).get("documents", [])

        if documents:
            signed_pdf_b64 = documents[0].get("PDFBytes")
            pdf_bytes = base64.b64decode(signed_pdf_b64)

            # 3. Save the file locally for now
            file_name = f"signed_re21_{envelope_id}.pdf"
            file_path = os.path.join('media', 'signed_contracts', file_name)

            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(pdf_bytes)

            print(f"DEBUG: Successfully saved signed contract to {file_path}")

            # TODO: Trigger an email to the agent or a push notification to iOS

    return Response({"status": "received"}, status=200)


class RE21ContractStatusEndpoint(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, envelope_id, *args, **kwargs):
        """
        GET /api/contracts/status/<envelope_id>/
        Checks if the contract is signed and returns the status.
        """
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


class AgentDealsListView(ListAPIView):
    serializer_class = DealSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # 👇 Add these debug prints
        print(f"\n=== DEALS LIST DEBUG ===")
        print(f"Request User Email: {user.email}")
        print(f"Request User ID: {user.id}")

        if user.email.lower() == 'ianschoenrock@gmail.com':
            deals = Deal.objects.filter(
                Q(agent=user) | Q(agent__isnull=True)
            ).order_by('-updated_at')

            print(f"Admin Route Triggered. Found {deals.count()} deals.")
            print(f"========================\n")
            return deals

        deals = Deal.objects.filter(agent=user).order_by('-updated_at')
        print(f"Normal Agent Route Triggered. Found {deals.count()} deals.")
        print(f"========================\n")
        return deals


class DealDeleteEndpoint(DestroyAPIView):
    # Ensure only logged-in users can trigger a deletion
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # SECURITY: This ensures an agent can only delete their OWN deals.
        # If they guess the ID of another agent's deal, Django will return a 404.
        return Deal.objects.filter(agent=self.request.user)

    def perform_destroy(self, instance):
        # 1. Delete the Draft PDF from AWS S3
        if instance.draft_pdf_url:
            try:
                default_storage.delete(instance.draft_pdf_url)
            except Exception as e:
                print(f"Failed to delete draft from S3: {e}")

        # 2. Delete the Signed PDF from AWS S3 (if it exists)
        if instance.signed_pdf_url:
            try:
                default_storage.delete(instance.signed_pdf_url)
            except Exception as e:
                print(f"Failed to delete signed doc from S3: {e}")

        # 3. Finally, delete the record from Postgres
        instance.delete()


User = get_user_model()


class FUBAuthCallbackView(APIView):
    permission_classes = []

    def custom_redirect(self, url):
        response = HttpResponse(status=302)
        response['Location'] = url
        return response

    def get(self, request, *args, **kwargs):
        import uuid
        req_id = str(uuid.uuid4())[:6]
        print(f"\n=== [DJANGO OAUTH {req_id}] CALLBACK HIT ===")

        try:
            code = request.GET.get('code')
            state_user_id = request.GET.get('state')

            if not code or not state_user_id:
                return self.custom_redirect('apexapp://fub-callback?status=error&message=missing_params')

            token_url = "https://app.followupboss.com/oauth/token"

            # 👇 THE MISSING PARAMETER REVEALED
            # Follow Up Boss uniquely requires the 'state' parameter to be
            # echoed BACK in the POST payload. Almost no other API does this!
            payload = {
                "grant_type": "authorization_code",
                "code": code.strip(),
                "redirect_uri": "https://www.apexintegrations.ai/api/auth/fub/callback/",
                "state": state_user_id.strip()  # <--- THIS IS THE FIX!
            }

            client_id = settings.FUB_CLIENT_ID.strip()
            client_secret = settings.FUB_CLIENT_SECRET.strip()

            print("Sending POST request to FUB...")

            # The requests library natively handles the Base64 Auth header
            response = requests.post(
                token_url,
                data=payload,
                auth=(client_id, client_secret)
            )

            print(f"FUB Status Code: {response.status_code}")

            if response.status_code == 200:
                print("✅ Token Exchange Successful!")
                data = response.json()
                access_token = data.get("access_token")

                user = User.objects.filter(id=state_user_id).first()
                if user:
                    user.fub_access_token = access_token
                    user.save()
                    return self.custom_redirect('apexapp://fub-callback?status=success')
                else:
                    return self.custom_redirect('apexapp://fub-callback?status=error&message=user_not_found')
            else:
                print(f"❌ FUB Rejected: {response.text}")
                error_msg = urllib.parse.quote(response.text)
                return self.custom_redirect(
                    f'apexapp://fub-callback?status=error&message=fub_rejected&details={error_msg}')

        except Exception as e:
            print(f"🚨 Python Crash: {str(e)}")
            error_msg = urllib.parse.quote(str(e))
            return self.custom_redirect(f'apexapp://fub-callback?status=error&message=python_crash&details={error_msg}')
        finally:
            print(f"=== [DJANGO OAUTH {req_id}] END ===\n")


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
            search_res = requests.get(search_url, headers=headers)
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

            create_res = requests.post(create_url, json=payload, headers=headers)
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

        note_res = requests.post(note_url, json=note_payload, headers=headers)

        if note_res.status_code in [200, 201]:
            return Response({"status": "success", "personId": person_id})
        else:
            return Response({"error": "Failed to add note to FUB", "details": note_res.text}, status=400)
