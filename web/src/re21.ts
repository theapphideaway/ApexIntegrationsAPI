// Port of iOS RE21FormData (+ RE14/Agency payloads, PacketPayloadBuilder,
// SectionIdentifier validation). Keys are the JSON keys the Django mappers read.
import type { Listing } from './mls'

export type RE21 = Record<string, unknown>

/** Baseline defaults — identical to the Swift struct's property defaults. */
export function defaultRE21(): RE21 {
  return {
    financingType: 'conventional', inspectionPeriod: 10,
    appraisalFeePayer: 'buyer', closingEscrowFeePayer: 'shared', titleInsurancePayer: 'seller', lenderInspectionsPayer: 'buyer',
    appraisalReInspectionFeePayer: 'buyer', lenderDocPrepFeePayer: 'buyer', taxServiceFeePayer: 'buyer', floodCertFeePayer: 'buyer',
    attorneyFeePayer: 'na', titleExtendedPayer: 'buyer', additionalTitlePayer: 'buyer',
    wellPotabilityPayer: 'buyer', wellProductivityPayer: 'buyer', septicInspectionPayer: 'buyer', septicPumpingPayer: 'buyer', surveyPayer: 'buyer',
    wellPotabilityOrderer: 'buyer', wellProductivityOrderer: 'buyer', septicInspectionOrderer: 'buyer', septicPumpingOrderer: 'buyer', surveyOrderer: 'buyer',
    buyerReviewedHOADocs: 'yes', hoaDuesFrequency: 'monthly', hoaSetupFeePayer: 'buyer', hoaTransferFeePayer: 'buyer',
    intendsToOccupy: true, intends1031Exchange: false, isBuiltBefore1979: false, isContingentOnSale: false,
    buyerAgency: 'agent', sellerAgency: 'agent', buyerReceivedDisclosure: 'na', prorationType: 'closing', buyerReimburseFuel: 'na', isAssignable: true,
    titleCommitmentFurnishedBy: 'seller', titleCommitmentDays: 6, titleObjectionDays: 2, titleSellerCureDays: 2, titleSellerTerminateDays: 2,
    earnestMoneyHolder: 'closing_agency',
    contingencies: [] as { type: string; description: string }[],
  }
}

/** MLSListing.prefill(into:) */
export function prefillFromListing(form: RE21, l: Listing): RE21 {
  const f = { ...form }
  f.propertyAddress = l.unparsedAddress; f.propertyCity = l.city; f.propertyState = l.stateOrProvince; f.propertyZip = l.postalCode
  if (l.countyOrParish) f.propertyCounty = l.countyOrParish
  if (l.parcelNumber) f.parcelNumber = l.parcelNumber
  if (l.legalDescription) f.legalDescription = l.legalDescription
  if (f.offerPrice == null && l.listPrice != null) f.offerPrice = l.listPrice
  if ((l.yearBuilt ?? Infinity) < 1978) f.isBuiltBefore1979 = true
  if (l.hasHOA === true || (l.hoaFee ?? 0) > 0) {
    if ((l.hoaFee ?? 0) > 0) f.hoaDues = l.hoaFee
    const s = (l.hoaFeeFrequency || '').toLowerCase()
    if (s.includes('month')) f.hoaDuesFrequency = 'monthly'
    else if (s.includes('year') || s.includes('annual')) f.hoaDuesFrequency = 'annually'
  }
  return f
}

/** RE21FormData.applyingLoanTypePresets() */
export function applyLoanTypePresets(form: RE21): RE21 {
  const f = { ...form }
  if (f.financingType === 'cash') {
    Object.assign(f, { appraisalFeePayer: 'na', appraisalReInspectionFeePayer: 'na', lenderInspectionsPayer: 'na', lenderDocPrepFeePayer: 'na', taxServiceFeePayer: 'na', floodCertFeePayer: 'na' })
  } else if (f.financingType === 'va') {
    Object.assign(f, { lenderDocPrepFeePayer: 'seller', taxServiceFeePayer: 'seller', attorneyFeePayer: 'seller' })
  }
  return f
}

// ---- option lists (raw values = Swift enum rawValues) ----
export const PAYER = [['buyer', 'Buyer'], ['seller', 'Seller'], ['shared', 'Shared'], ['na', 'N/A']]
export const PAYER_BS = [['buyer', 'Buyer'], ['seller', 'Seller']]
export const YNA = [['yes', 'Yes'], ['no', 'No'], ['na', 'N/A']]
export const FINANCING = [['cash', 'Cash'], ['conventional', 'Conventional'], ['fha', 'FHA'], ['va', 'VA'], ['other', 'Other']]
export const AGENCY = [['agent', 'Agent'], ['limitedDual', 'Limited Dual'], ['limitedDualAssigned', 'Limited Dual (Assigned)'], ['nonagent', 'Nonagent']]
export const HOA_FREQ = [['monthly', 'Monthly'], ['annually', 'Annually']]
export const PRORATION = [['closing', 'Date of closing'], ['date', 'Specific date']]
export const CONTINGENCY_TYPES = [['inspection', 'Inspection'], ['financing', 'Financing'], ['appraisal', 'Appraisal'], ['saleOfProperty', 'Sale of property'], ['other', 'Other']]

export type FieldType = 'text' | 'textarea' | 'money' | 'int' | 'date' | 'select' | 'toggle' | 'email' | 'phone'
export type Field = { key: string; label: string; type: FieldType; options?: string[][]; required?: boolean; group?: string }
export type Section = { id: string; title: string; fields: Field[] }

const t = (key: string, label: string, extra: Partial<Field> = {}): Field => ({ key, label, type: 'text', ...extra })
const sel = (key: string, label: string, options: string[][], extra: Partial<Field> = {}): Field => ({ key, label, type: 'select', options, ...extra })

/** Same sections, order, labels and required fields as the iOS ValidationView. */
export const SECTIONS: Section[] = [
  { id: 'propertyInformation', title: 'Property Information', fields: [
    t('propertyAddress', 'Property Address', { required: true }), t('propertyCity', 'City'), t('propertyCounty', 'County'), t('propertyState', 'State'), t('propertyZip', 'Zip'),
    t('parcelNumber', 'Parcel Number (APN)'), t('legalDescription', 'Legal Description', { type: 'textarea' }),
  ]},
  { id: 'buyerSeller', title: 'Buyer & Seller', fields: [
    t('buyerName', 'Name', { required: true, group: 'Buyer 1 Contact' }), t('buyerPhone', 'Phone', { type: 'phone', required: true, group: 'Buyer 1 Contact' }), t('buyerEmail', 'Email', { type: 'email', required: true, group: 'Buyer 1 Contact' }),
    t('buyerNameTwo', 'Name', { group: 'Buyer 2 Contact (optional)' }), t('buyerPhoneTwo', 'Phone', { type: 'phone', group: 'Buyer 2 Contact (optional)' }), t('buyerEmailTwo', 'Email', { type: 'email', group: 'Buyer 2 Contact (optional)' }),
    t('sellerName', 'Seller Name', { required: true, group: 'Seller Contact' }),
    sel('buyerAgency', 'Buyer Agency', AGENCY), sel('sellerAgency', 'Seller Agency', AGENCY), t('responsibleBroker', 'Responsible Broker'),
  ]},
  { id: 'financialTerms', title: 'Financial Terms', fields: [
    t('offerPrice', 'Offer Price', { type: 'money', required: true }), t('earnestMoney', 'Earnest Money', { type: 'money' }),
    sel('financingType', 'Financing Type', FINANCING),
    sel('loanApplicationStatus', 'Application Status', [['has_applied', 'Has applied'], ['shall_apply', 'Shall apply']], { group: 'Loan Details' }),
    t('firstLoanAmount', 'First Loan Amount', { type: 'money', group: 'Loan Details' }), t('secondLoanAmount', 'Second Loan Amount', { type: 'money', group: 'Loan Details' }),
    t('loanTermYears', 'Loan Term (Years)', { type: 'int', group: 'Loan Details' }), sel('loanRateType', 'Loan Rate Type', [['fixed', 'Fixed'], ['adjustable', 'Adjustable'], ['other', 'Other']], { group: 'Loan Details' }),
    t('loanInterestRate', 'Interest Rate (%)', { group: 'Loan Details' }),
    t('sellerConcessionAmount', 'Seller Concession', { type: 'money' }),
  ]},
  { id: 'earnestMoneyLogistics', title: 'Earnest Money Logistics', fields: [
    sel('earnestMoneyForm', 'Form', [['cash', 'Cash'], ['personal_check', 'Personal check'], ['cashiers_check', "Cashier's check"], ['wire_transfer', 'Wire transfer']]),
    sel('earnestMoneyHolder', 'Held By', [['listing_broker', 'Listing broker'], ['selling_broker', 'Selling broker'], ['closing_agency', 'Closing agency'], ['brokerage', 'Brokerage'], ['title_company', 'Title company']]),
    sel('earnestMoneyDelivered', 'Delivered', [['with_offer', 'With offer'], ['within_days', 'Within N days'], ['section_5', 'Per Section 5']]),
    t('earnestMoneyDeliveredDays', 'Delivered Within (Days)', { type: 'int' }),
    sel('earnestMoneyDeposited', 'Deposited', [['upon_receipt_acceptance', 'Upon receipt of acceptance'], ['upon_receipt_regardless', 'Upon receipt regardless'], ['section_5', 'Per Section 5']]),
  ]},
  { id: 'timelineCompanies', title: 'Timeline & Companies', fields: [
    t('closingDate', 'Closing Date', { type: 'date', required: true }), t('inspectionPeriod', 'Inspection Period (days)', { type: 'int' }),
    t('inspectionSellerResponseDays', 'Days for Seller to Respond', { type: 'int' }), t('inspectionBuyerNegotiationDays', 'Days for Buyer to Negotiate', { type: 'int' }),
    t('offerExpirationDate', 'Offer Expiration Date', { type: 'date' }), t('offerExpirationTime', 'Offer Expiration Time'),
    t('titleCompany', 'Title Company'), t('titleCompanyLocation', 'Title Company Address'), t('closingAgency', 'Closing Agency'),
    sel('titleCommitmentFurnishedBy', 'Furnished By', PAYER_BS, { group: 'Title Insurance (Section 11)' }), t('titleCommitmentDays', 'Days to Furnish', { type: 'int', group: 'Title Insurance (Section 11)' }),
    t('titleObjectionDays', 'Days to Object', { type: 'int', group: 'Title Insurance (Section 11)' }), t('titleSellerCureDays', 'Days for Seller to Cure', { type: 'int', group: 'Title Insurance (Section 11)' }),
    t('titleSellerTerminateDays', 'Days for Seller to Terminate', { type: 'int', group: 'Title Insurance (Section 11)' }),
    sel('prorationType', 'Prorated On', PRORATION, { group: 'Prorations (Section 43)' }), t('prorationDate', 'Proration Date', { type: 'date', group: 'Prorations (Section 43)' }),
    sel('buyerReimburseFuel', 'Reimburse Fuel in Tank', YNA, { group: 'Prorations (Section 43)' }),
  ]},
  { id: 'conditionsDisclosures', title: 'Conditions & Disclosures', fields: [
    t('intendsToOccupy', 'Intends to Occupy', { type: 'toggle' }), t('intends1031Exchange', '1031 Exchange', { type: 'toggle' }), t('isContingentOnSale', 'Contingent on Sale', { type: 'toggle' }),
    t('isBuiltBefore1979', 'Property Built Before 1979 (Lead Paint)', { type: 'toggle' }), sel('buyerReceivedDisclosure', 'Buyer Received Disclosure', YNA),
  ]},
  { id: 'hoa', title: 'Homeowners Association (HOA)', fields: [
    sel('buyerReviewedHOADocs', 'Reviewed Docs', YNA), t('hoaDues', 'HOA Dues', { type: 'money' }), sel('hoaDuesFrequency', 'Dues Frequency', HOA_FREQ),
    t('hoaSetupFee', 'Setup Fee', { type: 'money', group: 'Setup Fee' }), sel('hoaSetupFeePayer', 'Who Pays Setup Fee', PAYER, { group: 'Setup Fee' }),
    t('hoaTransferFee', 'Transfer Fee', { type: 'money', group: 'Transfer Fee' }), sel('hoaTransferFeePayer', 'Who Pays Transfer Fee', PAYER, { group: 'Transfer Fee' }),
  ]},
  { id: 'closingCosts', title: 'Closing Costs (Who Pays)', fields: [
    sel('appraisalFeePayer', 'Appraisal Fee', PAYER), sel('appraisalReInspectionFeePayer', 'Appraisal Re-Inspection', PAYER), sel('closingEscrowFeePayer', 'Closing/Escrow Fee', PAYER),
    sel('lenderDocPrepFeePayer', 'Lender Doc Prep', PAYER), sel('taxServiceFeePayer', 'Tax Service Fee', PAYER), sel('floodCertFeePayer', 'Flood Cert Fee', PAYER),
    sel('lenderInspectionsPayer', 'Lender Inspections', PAYER), sel('attorneyFeePayer', 'Attorney Fee', PAYER), sel('titleInsurancePayer', 'Title Ins. (Standard)', PAYER),
    sel('titleExtendedPayer', 'Title Ins. (Extended)', PAYER), sel('additionalTitlePayer', 'Additional Title', PAYER),
  ]},
  { id: 'propertyTests', title: 'Property Tests', fields: [
    sel('wellPotabilityPayer', 'Pays', PAYER, { group: 'Well Potability' }), sel('wellPotabilityOrderer', 'Orders', PAYER, { group: 'Well Potability' }), t('wellWaterInspectionDays', 'Days to Complete', { type: 'int', group: 'Well Potability' }),
    sel('wellProductivityPayer', 'Pays', PAYER, { group: 'Well Productivity' }), sel('wellProductivityOrderer', 'Orders', PAYER, { group: 'Well Productivity' }),
    sel('septicInspectionPayer', 'Pays', PAYER, { group: 'Septic Inspection' }), sel('septicInspectionOrderer', 'Orders', PAYER, { group: 'Septic Inspection' }), t('septicInspectionDays', 'Days to Complete', { type: 'int', group: 'Septic Inspection' }),
    sel('septicPumpingPayer', 'Pays', PAYER, { group: 'Septic Pumping' }), sel('septicPumpingOrderer', 'Orders', PAYER, { group: 'Septic Pumping' }),
    sel('surveyPayer', 'Pays', PAYER, { group: 'Survey' }), sel('surveyOrderer', 'Orders', PAYER, { group: 'Survey' }), t('surveyInspectionDays', 'Days to Complete', { type: 'int', group: 'Survey' }),
  ]},
  { id: 'contingenciesExclusions', title: 'Contingencies & Exclusions', fields: [
    t('additionalTerms', 'Additional Terms', { type: 'textarea', group: 'Free Text Terms' }), t('excludedItems', 'Excluded Items', { type: 'textarea', group: 'Free Text Terms' }),
    t('isAssignable', 'Agreement may be assigned/sold', { type: 'toggle', group: 'Assignment' }),
  ]},
]

export const RE14_FIELDS: Field[] = [
  sel('propertyType', 'Property Type', [['residential', 'Residential'], ['income', 'Income'], ['commercial', 'Commercial'], ['land', 'Land'], ['build', 'To be built'], ['other', 'Other']]),
  t('searchCity', 'Search City'), t('searchCounty', 'Search County'), t('searchState', 'Search State'), t('searchDescription', 'Search Description', { type: 'textarea' }),
  t('startDate', 'Term Start', { type: 'date' }), t('endDate', 'Term Expiration', { type: 'date' }),
  t('compensationPercentage', 'Compensation (%)'), t('compensationFlatFee', 'Transaction Fee ($)'), t('cancellationPercentage', 'Cancellation Fee'),
  sel('agencyType', 'Agency Type', [['dual', 'Dual'], ['single', 'Single']]), t('otherTerms', 'Other Terms', { type: 'textarea' }),
]
export const defaultRE14 = () => ({ propertyType: 'residential', searchCity: '', searchCounty: '', searchState: 'Idaho', searchDescription: '', startDate: '', endDate: '', compensationPercentage: '3', compensationFlatFee: '500', cancellationPercentage: '$1,000', otherTerms: '', agencyType: 'dual' })

export const AGENCY_FIELDS: Field[] = [t('brokerageName', 'Brokerage Name'), t('designatedBroker', 'Designated Broker'), t('brokeragePhone', 'Brokerage Phone', { type: 'phone' })]
export const defaultAgency = () => ({ brokerageName: '', designatedBroker: '', brokeragePhone: '' })

/** Missing required fields per section (SectionIdentifier.requiredFields). */
export function missingRequired(form: RE21): { section: string; label: string; key: string }[] {
  const out: { section: string; label: string; key: string }[] = []
  for (const s of SECTIONS) for (const f of s.fields) {
    if (!f.required) continue
    const v = form[f.key]
    if (v === undefined || v === null || v === '' || (typeof v === 'number' && isNaN(v))) out.push({ section: s.title, label: f.label, key: f.key })
  }
  return out
}

/** Swift encodes Date as ISO-8601; a date input gives YYYY-MM-DD → local noon → ISO. */
const isoDate = (v: unknown) => (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)) ? new Date(`${v}T12:00:00`).toISOString() : v
const DATE_KEYS = new Set(['closingDate', 'offerExpirationDate', 'prorationDate'])

function encodeRE21(form: RE21): RE21 {
  const out: RE21 = {}
  for (const [k, v] of Object.entries(form)) {
    if (v === undefined || v === null || v === '') continue  // Swift omits nil optionals
    out[k] = DATE_KEYS.has(k) ? isoDate(v) : v
  }
  out.extractionTimestamp = new Date().toISOString()
  out.confidenceScores = out.confidenceScores || {}
  return out
}

export type Forms = { re21: boolean; re14: boolean; agency: boolean }

/** PacketPayloadBuilder.body — one key per SELECTED form; specific fields overlay the RE-21, blanks dropped. */
export function buildPacket(form: RE21, re14: Record<string, string>, agency: Record<string, string>, forms: Forms) {
  const base = encodeRE21(form)
  const merged = (specific: Record<string, string>) => {
    const r: RE21 = { ...base }
    for (const [k, v] of Object.entries(specific)) { if (v === '') continue; r[k] = (k === 'startDate' || k === 'endDate') ? isoDate(v) : v }
    return r
  }
  const buyers = [{ name: String(form.buyerName || ''), email: String(form.buyerEmail || '') }]
  if (form.buyerNameTwo && form.buyerEmailTwo) buyers.push({ name: String(form.buyerNameTwo), email: String(form.buyerEmailTwo) })
  const root: Record<string, unknown> = { buyers }
  if (forms.re21) root.re21 = base
  if (forms.re14) root.re14 = merged(re14)
  if (forms.agency) root.agencyDisclosure = merged(agency)
  return root
}
