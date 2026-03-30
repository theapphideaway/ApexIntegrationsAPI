import base64
import os

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from docusign_esign import EnvelopesApi, ApiClient
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .docusign_service import DocuSignService
from .pdf_service import PDFGenerationService
# Create your views here.

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Organization, CustomUser, OTPCode
from .serializers import OrganizationSerializer, CustomUserSerializer
from django.core.mail import send_mail
from django.conf import settings


@api_view(['GET', 'POST'])
def organization_list(request):
    """
    List all organizations, or create a new organization.
    """
    if request.method == 'GET':
        organizations = Organization.objects.all()
        serializer = OrganizationSerializer(organizations, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = OrganizationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
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
        # We still return 200 for security, but now you'll see why it didn't send.
        pass
    except Exception as e:
        print(f"---> SMTP/SYSTEM ERROR: {e}")  # DEBUG
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {"message": "Verification code has been sent to your email."},
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
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
def verify_otp(request):
    email = request.data.get('email', '').strip()
    code = request.data.get('code', '').strip()

    print(f"---> Verification attempt: Email='{email}', Code='{code}'")

    try:
        # 1. Check User
        user = CustomUser.objects.get(email__iexact=email)
        print(f"---> User found: {user.id}")

        # 2. Check for the OTP
        # We look for the most recent UNUSED code for this specific user
        otp_instance = OTPCode.objects.filter(
            user=user,
            code=code,
            is_used=False
        ).latest('created_at')

        print(f"---> OTP found in DB. Created at: {otp_instance.created_at}")

        # 3. Check Validity
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
                'user_id': user.id
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
    def post(self, request, *args, **kwargs):
        form_data = request.data
        template_path = os.path.join(settings.BASE_DIR, 'static', 'pdfs', 're21_2026.pdf')
        try:
            pdf_service = PDFGenerationService(template_path)
            pdf_bytes = pdf_service.generate_pdf(form_data)

            # Split the names
            raw_buyer_name = form_data.get("buyerName", "Test Buyer")
            buyer_names = [n.strip() for n in raw_buyer_name.split(" and ")]
            signer_email = form_data.get("buyerEmail", "test@example.com")

            buyers_list = []
            for name in buyer_names:
                buyers_list.append({"name": name, "email": signer_email})

            # Get the dictionary of URLs
            ds_service = DocuSignService()
            # Note: Renamed function call to plural 'links'
            signing_urls = ds_service.create_embedded_signature_links(
                pdf_bytes=pdf_bytes,
                buyers=buyers_list
            )

            # This will return { "buyer1_signing_url": "...", "buyer2_signing_url": "..." }
            # If there's no Buyer 2, the buyer2_signing_url will be an empty string
            return Response(signing_urls, status=200)

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
