import base64
import os
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Envelope, Document, Signer, SignHere, Tabs, \
    Recipients, InitialHere, DateSigned

from AccountsAdmin.pdf_service import PDFGenerationService
from ApexIntegrationsAPI import settings


class DocuSignService:
    @staticmethod
    def env_config(env: str) -> dict:
        """Credential set for an environment. Demo = the DOCUSIGN_* vars we
        have used all along; production = DOCUSIGN_PROD_* (its own integration
        key, impersonated user, account, account-specific base URL and key)."""
        if env == "production":
            return {
                "env": "production",
                "client_id": os.environ.get("DOCUSIGN_PROD_CLIENT_ID"),
                "user_id": os.environ.get("DOCUSIGN_PROD_USER_ID"),
                "account_id": os.environ.get("DOCUSIGN_PROD_ACCOUNT_ID"),
                "auth_server": "account.docusign.com",
                "base_path": os.environ.get("DOCUSIGN_PROD_BASE_PATH", "https://na4.docusign.net/restapi"),
                "private_key_path": os.path.join(settings.BASE_DIR, os.environ.get("DOCUSIGN_PROD_PRIVATE_KEY", "private_key_prod.pem")),
            }
        return {
            "env": "demo",
            "client_id": os.environ.get("DOCUSIGN_CLIENT_ID"),
            "user_id": os.environ.get("DOCUSIGN_USER_ID"),
            "account_id": os.environ.get("DOCUSIGN_ACCOUNT_ID"),
            "auth_server": "account-d.docusign.com",  # '-d' = developer sandbox
            "base_path": "https://demo.docusign.net/restapi",
            "private_key_path": os.path.join(settings.BASE_DIR, "private_key.pem"),
        }

    @staticmethod
    def current_env() -> str:
        """Production MASTER switch (dev portal). 'demo' = everyone on the sandbox."""
        from .settings_service import get_setting
        return get_setting("docusign_env", "demo") or "demo"

    @classmethod
    def production_configured(cls) -> bool:
        cfg = cls.env_config("production")
        return all([cfg["client_id"], cfg["user_id"], cfg["account_id"], os.path.exists(cfg["private_key_path"])])

    @classmethod
    def env_for_user(cls, user) -> str:
        """Effective environment for envelopes created for this user:
        production only if the master switch is on, the user is flagged for
        production, and production credentials exist — otherwise demo."""
        if cls.current_env() == "production" and getattr(user, "docusign_production", False) and cls.production_configured():
            return "production"
        return "demo"

    def __init__(self, env: str = None):
        cfg = self.env_config(env or self.current_env())
        self.env = cfg["env"]
        self.client_id = cfg["client_id"]
        self.user_id = cfg["user_id"]
        self.account_id = cfg["account_id"]
        self.private_key_path = cfg["private_key_path"]
        self.auth_server = cfg["auth_server"]
        self.base_path = cfg["base_path"]

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

    def test_connection(self) -> dict:
        """Dev-portal check: JWT auth + userinfo for the selected environment."""
        access_token = self._get_access_token()
        api_client = ApiClient()
        api_client.set_base_path(self.auth_server)
        info = api_client.get_user_info(access_token)
        accounts = [{
            "account_id": a.account_id, "name": a.account_name, "base_uri": a.base_uri, "is_default": a.is_default,
        } for a in (info.accounts or [])]
        return {
            "env": self.env, "auth_server": self.auth_server, "base_path": self.base_path,
            "user": info.name, "email": info.email, "accounts": accounts,
            "configured_account_matches": any(a["account_id"] == self.account_id for a in accounts),
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

    def void_envelope(self, envelope_id: str, reason: str = "Revised offer sent") -> None:
        """Voids an in-flight envelope so recipients can no longer sign it.
        Used when a deal is deleted/revised while out for signature."""
        access_token = self._get_access_token()

        api_client = ApiClient()
        api_client.host = self.base_path
        api_client.set_default_header("Authorization", f"Bearer {access_token}")

        envelopes_api = EnvelopesApi(api_client)
        envelopes_api.update(
            account_id=self.account_id,
            envelope_id=envelope_id,
            envelope=Envelope(status="voided", voided_reason=reason)
        )

    def send_bundle_envelope(self, bundled_data: dict, buyers: list,
                             email_subject: str = "Please sign your Onboarding & Purchase Packet") -> dict:
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
        document_bytes = []  # (doc_type, pdf_bytes) — for the caller's draft copy
        # DocuSign requires document IDs to be unique sequential strings ("1", "2", "3")
        for idx, (doc_type, data) in enumerate(bundled_data.items(), start=1):
            service = PDFGenerationService(doc_type=doc_type)
            pdf_bytes = service.generate_pdf(data)
            document_bytes.append((doc_type, pdf_bytes))

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
            email_subject=email_subject,
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
            "document_bytes": document_bytes,
            "envelope_id": envelope_summary.envelope_id
        }




