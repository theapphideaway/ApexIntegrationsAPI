"""Hourly safety net: ask DocuSign about every in-flight envelope and file the
ones that completed without the webhook (or mark voided/declined ones).
Schedule on PythonAnywhere: `python manage.py reconcile_envelopes` hourly."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from AccountsAdmin.models import Deal, DealDocument
from AccountsAdmin.views import reconcile_deal, reconcile_document


class Command(BaseCommand):
    help = "Reconcile in-flight DocuSign envelopes (deals + documents) with DocuSign."

    def add_arguments(self, parser):
        parser.add_argument("--min-age-minutes", type=int, default=10,
                            help="Skip envelopes updated more recently than this (the webhook may still be on its way).")

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(minutes=opts["min_age_minutes"])
        filed = cancelled = checked = errors = 0
        for deal in Deal.objects.filter(status__in=["out_for_signature", "signed_by_buyers"], updated_at__lt=cutoff).exclude(docusign_envelope_id__isnull=True):
            checked += 1
            try:
                info = reconcile_deal(deal)
                if info.get("action") == "filed":
                    filed += 1; self.stdout.write(f"filed deal {deal.id} ({deal.property_address})")
                elif info.get("action") in ("voided", "declined", "deleted"):
                    cancelled += 1; self.stdout.write(f"deal {deal.id} envelope {info['action']}")
            except Exception as e:
                errors += 1; self.stderr.write(f"deal {deal.id}: {e}")
        for doc in DealDocument.objects.filter(status="out_for_signature").exclude(docusign_envelope_id__isnull=True):
            checked += 1
            try:
                info = reconcile_document(doc)
                if info.get("action") == "filed":
                    filed += 1; self.stdout.write(f"filed document {doc.id} on deal {doc.deal_id}")
            except Exception as e:
                errors += 1; self.stderr.write(f"document {doc.id}: {e}")
        self.stdout.write(f"checked {checked}, filed {filed}, cancelled {cancelled}, errors {errors}")
