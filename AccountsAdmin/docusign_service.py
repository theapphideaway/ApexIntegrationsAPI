import base64
import os
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Document, Signer, SignHere, Tabs, Recipients, \
    InitialHere, DateSigned

from AccountsAdmin.pdf_service import PDFGenerationService
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

    def send_bundle_envelope(self, bundled_data: dict, buyers: list) -> dict:
        """
        Generates all PDFs in the bundle, stitches them into a single DocuSign
        envelope, and emails it directly to the buyers for remote execution.
        """
        access_token = self._get_access_token()

        api_client = ApiClient()
        api_client.host = self.base_path
        api_client.set_default_header("Authorization", f"Bearer {access_token}")

        # 1. Generate and package all PDFs into the envelope
        docs_to_send = []
        # DocuSign requires document IDs to be unique sequential strings ("1", "2", "3")
        for idx, (doc_type, data) in enumerate(bundled_data.items(), start=1):
            service = PDFGenerationService(doc_type=doc_type)
            pdf_bytes = service.generate_pdf(data)

            doc = Document(
                document_base64=base64.b64encode(pdf_bytes).decode('utf-8'),
                name=f"{doc_type.upper().replace('_', ' ')}",
                file_extension="pdf",
                document_id=str(idx)
            )
            docs_to_send.append(doc)

        # 2. Build Remote Signers (Omit client_user_id so DocuSign handles the emails)
        docusign_signers = []
        for index, buyer in enumerate(buyers):
            signer_id = str(index + 1)

            signer = Signer(
                email=buyer['email'],
                name=buyer['name'],
                recipient_id=signer_id,
                routing_order="1"  # Both get the email concurrently
            )

            # DocuSign scans ALL attached documents for these string patterns
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

            # Auto-stamps the signing date wherever the PDF carries \d<n>\
            # (signature-row Date columns and page-bottom "Date:" lines).
            date_signed = DateSigned(
                anchor_string=f"\\d{signer_id}\\",
                anchor_units="pixels",
                anchor_y_offset="0",
                anchor_x_offset="0"
            )

            signer.tabs = Tabs(
                sign_here_tabs=[sign_here],
                initial_here_tabs=[initial_here],
                date_signed_tabs=[date_signed]
            )
            docusign_signers.append(signer)

        # 3. Create and Send the Envelope
        envelope_definition = EnvelopeDefinition(
            email_subject="Please sign your Onboarding & Purchase Packet",
            documents=docs_to_send,
            recipients=Recipients(signers=docusign_signers),
            status="sent"  # Fires off the emails immediately
        )

        envelopes_api = EnvelopesApi(api_client)
        envelope_summary = envelopes_api.create_envelope(
            account_id=self.account_id,
            envelope_definition=envelope_definition
        )

        # 4. Return the status and unique ID back to your view layer
        return {
            "status": "sent",
            "envelope_id": envelope_summary.envelope_id
        }




