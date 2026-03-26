import base64
import os
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Document, Signer, SignHere, Tabs, Recipients, \
    RecipientViewRequest


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

        with open(self.private_key_path, "rb") as key_file:
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

    def create_embedded_signature_link(self, pdf_bytes: bytes, signer_name: str, signer_email: str) -> str:
        """Sends the PDF to DocuSign and generates a unique, interactive signing URL."""
        access_token = self._get_access_token()

        # Setup the authenticated API client
        api_client = ApiClient()
        api_client.host = self.base_path
        api_client.set_default_header("Authorization", f"Bearer {access_token}")

        # 1. Package the PDF Document
        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        document = Document(
            document_base64=b64_pdf,
            name="RE-21 Purchase Agreement",
            file_extension="pdf",
            document_id="1"
        )

        # 2. Configure the Signer and the AutoPlace Anchor Tag
        # client_user_id is REQUIRED. It tells DocuSign this user signs via your embedded app.
        signer = Signer(
            email=signer_email,
            name=signer_name,
            recipient_id="1",
            routing_order="1",
            client_user_id="1001"
        )

        # Instruct DocuSign to drop the interactive signature box exactly on top of \s1\
        sign_here = SignHere(
            anchor_string="\\s1\\",
            anchor_units="pixels",
            anchor_y_offset="0",
            anchor_x_offset="0"
        )

        signer.tabs = Tabs(sign_here_tabs=[sign_here])

        # 3. Build and Send the Envelope
        envelope_definition = EnvelopeDefinition(
            email_subject="Please sign your RE-21 Purchase Agreement",
            documents=[document],
            recipients=Recipients(signers=[signer]),
            status="sent"  # "sent" makes it actionable immediately
        )

        envelopes_api = EnvelopesApi(api_client)
        envelope_summary = envelopes_api.create_envelope(
            account_id=self.account_id,
            envelope_definition=envelope_definition
        )

        # 4. Request the Embedded Signing View URL
        view_request = RecipientViewRequest(
            authentication_method="none",
            client_user_id="1001",
            recipient_id="1",
            return_url="https://www.apexintegrations.ai/success",  # DocuSign redirects here when finished
            user_name=signer_name,
            email=signer_email
        )

        results = envelopes_api.create_recipient_view(
            account_id=self.account_id,
            envelope_id=envelope_summary.envelope_id,
            recipient_view_request=view_request
        )

        return results.url