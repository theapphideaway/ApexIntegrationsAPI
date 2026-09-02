// Port of iOS MLSListing/RESORecord: normalize a RESO Property record.
export type Listing = {
  mlsNumber: string; listingKey?: string; standardStatus?: string
  unparsedAddress: string; city: string; stateOrProvince: string; postalCode: string; countyOrParish?: string
  listPrice?: number; bedroomsTotal?: number; bathroomsTotal?: number; livingArea?: number; yearBuilt?: number
  parcelNumber?: string; legalDescription?: string; publicRemarks?: string
  hasHOA?: boolean; hoaFee?: number; hoaFeeFrequency?: string
  listAgentFullName?: string; listAgentEmail?: string; listAgentPhone?: string; listOfficeName?: string
  thumbnailURL?: string
}

const num = (v: unknown): number | undefined => (v === null || v === undefined || v === '') ? undefined : Number(v)
const str = (v: unknown): string | undefined => (v === null || v === undefined) ? undefined : String(v)

export function toListing(r: Record<string, unknown>): Listing {
  const media = (Array.isArray(r.Media) ? r.Media : []) as { MediaURL?: string; MediaCategory?: string; Order?: number }[]
  const photo = media.filter((m) => !m.MediaCategory || m.MediaCategory === 'Photo')
    .sort((a, b) => (a.Order ?? 1e9) - (b.Order ?? 1e9)).find((m) => m.MediaURL)?.MediaURL
  return {
    mlsNumber: str(r.ListingId) || str(r.ListingKey) || 'UNKNOWN', listingKey: str(r.ListingKey), standardStatus: str(r.StandardStatus),
    unparsedAddress: str(r.UnparsedAddress) || '', city: str(r.City) || '', stateOrProvince: str(r.StateOrProvince) || '', postalCode: str(r.PostalCode) || '',
    countyOrParish: str(r.CountyOrParish), listPrice: num(r.ListPrice), bedroomsTotal: num(r.BedroomsTotal),
    bathroomsTotal: num(r.BathroomsTotalDecimal) ?? num(r.BathroomsTotalInteger), livingArea: num(r.LivingArea), yearBuilt: num(r.YearBuilt),
    parcelNumber: str(r.ParcelNumber), legalDescription: str(r.TaxLegalDescription), publicRemarks: str(r.PublicRemarks),
    hasHOA: typeof r.AssociationYN === 'boolean' ? r.AssociationYN : undefined, hoaFee: num(r.AssociationFee), hoaFeeFrequency: str(r.AssociationFeeFrequency),
    listAgentFullName: str(r.ListAgentFullName), listAgentEmail: str(r.ListAgentEmail),
    listAgentPhone: str(r.ListAgentPreferredPhone) || str(r.ListAgentDirectPhone), listOfficeName: str(r.ListOfficeName), thumbnailURL: photo,
  }
}

export const money = (n?: number) => n === undefined ? '' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
