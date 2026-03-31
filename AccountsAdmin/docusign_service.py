import base64
import os
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Document, Signer, SignHere, Tabs, Recipients, \
    RecipientViewRequest, InitialHere

from ApexIntegrationsAPI import settings


class DocuSignService:
    def __init__(self):
        self.client_id = os.environ.get("DOCUSIGN_CLIENT_ID")
        self.user_id = os.environ.get("DOCUSIGN_USER_ID")
        self.account_id = os.environ.get("DOCUSIGN_ACCOUNT_ID")
        self.private_key_path = os.environ.get("DOCUSIGN_PRIVATE_KEY_PATH")
        self.auth_server = 'account-d.docusign.com'  # '-d' denotes the demo/developer server
        self.base_path = 'https://demo.docusign.net/restapi'

    def _get_access_token(self):
        """Authenticates with DocuSign via JWT and returns a temporary access token."""
        api_client = ApiClient()
        api_client.set_base_path(self.auth_server)
        private_key_path = os.path.join(settings.BASE_DIR, 'private_key.pem')

        # 2. Open the file using that absolute path
        with open(private_key_path, "rb") as key_file:
            private_key_bytes = key_file.read()

        token_response = api_client.request_jwt_user_token(
            client_id=self.client_id,
            user_id=self.user_id,
            oauth_host_name=self.auth_server,
            private_key_bytes=private_key_bytes,
            expires_in=3600,
            scopes=["signature", "impersonation"]
        )
        return token_response.access_token

    def create_embedded_signature_links(self, pdf_bytes: bytes, buyers: list) -> dict:
        access_token = self._get_access_token()

        api_client = ApiClient()
        api_client.host = self.base_path
        api_client.set_default_header("Authorization", f"Bearer {access_token}")

        # 1. Package the PDF
        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        document = Document(
            document_base64=b64_pdf,
            name="RE-21 Purchase Agreement",
            file_extension="pdf",
            document_id="1"
        )

        # 2. Build the Signers
        docusign_signers = []
        for index, buyer in enumerate(buyers):
            signer_id = str(index + 1)
            client_user_id = f"100{signer_id}"

            signer = Signer(
                email=buyer['email'],
                name=buyer['name'],
                recipient_id=signer_id,
                routing_order="1",  # Both can sign at the same time
                client_user_id=client_user_id
            )

            sign_here = SignHere(
                anchor_string=f"\\s{signer_id}\\",
                anchor_units="pixels",
                anchor_y_offset="0",
                anchor_x_offset="0"
            )

            # Define the Initials Tab (Added this)
            # This will find ALL instances of \i1\ on the document
            initial_here = InitialHere(
                anchor_string=f"\\i{signer_id}\\",
                anchor_units="pixels",
                anchor_y_offset="0",
                anchor_x_offset="0"
            )

            # Add both to the signer's tabs
            signer.tabs = Tabs(
                sign_here_tabs=[sign_here],
                initial_here_tabs=[initial_here]  # Add the initials list here
            )
            docusign_signers.append(signer)

        # 3. Create the Envelope
        envelope_definition = EnvelopeDefinition(
            email_subject="Please sign your RE-21 Purchase Agreement",
            documents=[document],
            recipients=Recipients(signers=docusign_signers),
            status="sent"
        )

        envelopes_api = EnvelopesApi(api_client)
        envelope_summary = envelopes_api.create_envelope(
            account_id=self.account_id,
            envelope_definition=envelope_definition
        )

        # 4. Generate individual URLs for each buyer
        urls = {
            "buyer1_signing_url": "",
            "buyer2_signing_url": ""
        }

        for index, buyer in enumerate(buyers):
            signer_id = str(index + 1)
            client_user_id = f"100{signer_id}"

            view_request = RecipientViewRequest(
                authentication_method="none",
                client_user_id=client_user_id,
                recipient_id=signer_id,
                return_url="https://www.apexintegrations.ai/success",
                user_name=buyer['name'],
                email=buyer['email']
            )

            results = envelopes_api.create_recipient_view(
                account_id=self.account_id,
                envelope_id=envelope_summary.envelope_id,
                recipient_view_request=view_request
            )

            # Map the URL to the correct key in our dictionary
            key = f"buyer{signer_id}_signing_url"
            urls[key] = results.url

        return urls

    def send_envelope(self, pdf_bytes: bytes, buyers: list) -> dict:
        access_token = self._get_access_token()

        api_client = ApiClient()
        api_client.host = self.base_path
        api_client.set_default_header("Authorization", f"Bearer {access_token}")

        # 1. Package the PDF
        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        document = Document(
            document_base64=b64_pdf,
            name="RE-21 Purchase Agreement",
            file_extension="pdf",
            document_id="1"
        )

        # 2. Build the Signers
        docusign_signers = []
        for index, buyer in enumerate(buyers):
            signer_id = str(index + 1)

            # CRITICAL FIX: We completely removed client_user_id here.
            # This triggers DocuSign to send the email directly to the buyer.
            signer = Signer(
                email=buyer['email'],
                name=buyer['name'],
                recipient_id=signer_id,
                routing_order="1"  # Both get the email at the same time
            )

            sign_here = SignHere(
                anchor_string=f"\\s{signer_id}\\",
                anchor_units="pixels",
                anchor_y_offset="0",
                anchor_x_offset="0"
            )

            initial_here = InitialHere(
                anchor_string=f"\\i{signer_id}\\",
                anchor_units="pixels",
                anchor_y_offset="0",
                anchor_x_offset="0"
            )

            signer.tabs = Tabs(
                sign_here_tabs=[sign_here],
                initial_here_tabs=[initial_here]
            )
            docusign_signers.append(signer)

        # 3. Create and Send the Envelope
        envelope_definition = EnvelopeDefinition(
            email_subject="Please sign your RE-21 Purchase Agreement",
            documents=[document],
            recipients=Recipients(signers=docusign_signers),
            status="sent"  # "sent" immediately fires off the emails
        )

        envelopes_api = EnvelopesApi(api_client)
        envelope_summary = envelopes_api.create_envelope(
            account_id=self.account_id,
            envelope_definition=envelope_definition
        )

        # 4. Return the success status and envelope ID to Swift
        return {
            "status": "sent",
            "envelope_id": envelope_summary.envelope_id
        }

    def download_envelope_document(self, envelope_id: str) -> bytes:
        """Retrieves the fully signed PDF from DocuSign using the envelope ID."""
        access_token = self._get_access_token()

        api_client = ApiClient()
        api_client.host = self.base_path
        api_client.set_default_header("Authorization", f"Bearer {access_token}")

        envelopes_api = EnvelopesApi(api_client)

        # 'combined' retrieves all documents in the envelope merged into one PDF
        # This includes the RE-21 and the Summary/Audit trail
        temp_file_path = envelopes_api.get_document(
            account_id=self.account_id,
            document_id="combined",
            envelope_id=envelope_id
        )

        # Read the temp file into bytes and return it
        with open(temp_file_path, "rb") as f:
            pdf_bytes = f.read()

        return pdf_bytes

