"""Contract defaults: baseline ← agent's own ← TEAM (team wins and locks).

Keys are the RE-21 JSON field names plus a few extras:
  re14: compensationPercentage, compensationFlatFee, cancellationPercentage, agencyType
  contacts: titleCompanyName, titleEmail, titlePhone, lenderCompanyName, lenderEmail, lenderPhone
Every document payload gets empty fields filled from the effective defaults
server-side, so web and phone can never diverge on what "default" means."""

CONTACT_KEYS = ("titleCompanyName", "titleEmail", "titlePhone", "lenderCompanyName", "lenderEmail", "lenderPhone")
RE14_KEYS = ("compensationPercentage", "compensationFlatFee", "cancellationPercentage", "agencyType",
             "propertyType", "searchState")
# Never a "default": deal-specific facts.
NEVER_DEFAULT = {"propertyAddress", "propertyCity", "propertyCounty", "propertyState", "propertyZip", "parcelNumber",
                 "legalDescription", "buyerName", "buyerPhone", "buyerEmail", "buyerNameTwo", "buyerPhoneTwo",
                 "buyerEmailTwo", "sellerName", "offerPrice", "earnestMoney", "closingDate", "offerExpirationDate",
                 "firstLoanAmount", "secondLoanAmount", "extractionTimestamp", "confidenceScores", "contingencies",
                 "hoaDues", "hoaSetupFee", "hoaTransferFee", "sellerConcessionAmount", "prorationDate"}


def _clean(d):
    return {k: v for k, v in (d or {}).items() if k not in NEVER_DEFAULT and v not in (None, "", [], {})}


def team_defaults(user):
    org = getattr(user, "organization", None)
    return _clean(org.defaults) if org is not None else {}


def my_defaults(user):
    return _clean(getattr(user, "defaults", None))


def effective_defaults(user):
    eff = dict(my_defaults(user))
    eff.update(team_defaults(user))
    return eff


def locked_keys(user):
    return sorted(team_defaults(user).keys())


def bundle(user):
    return {"team": team_defaults(user), "mine": my_defaults(user), "effective": effective_defaults(user),
            "locked": locked_keys(user)}


def apply_defaults(doc_payload: dict, user) -> dict:
    """Fill EMPTY fields of a document payload from the effective defaults.
    Values the agent typed (or the MLS supplied) always win — except locked
    team keys, which are enforced."""
    if not isinstance(doc_payload, dict):
        return doc_payload
    team = team_defaults(user)
    for k, v in effective_defaults(user).items():
        if k in CONTACT_KEYS:
            continue
        current = doc_payload.get(k)
        if k in team or current in (None, "", [], {}):
            doc_payload[k] = v
    # Contacts map onto the RE-21's title company field when it is blank.
    contacts = {k: v for k, v in effective_defaults(user).items() if k in CONTACT_KEYS}
    if contacts.get("titleCompanyName") and not doc_payload.get("titleCompany"):
        doc_payload["titleCompany"] = contacts["titleCompanyName"]
    if contacts.get("titleCompanyName") and not doc_payload.get("closingAgency"):
        doc_payload["closingAgency"] = contacts["titleCompanyName"]
    return doc_payload
