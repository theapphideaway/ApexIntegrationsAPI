import re
import textwrap

import fitz  # PyMuPDF
import os
from datetime import datetime
from num2words import num2words
from django.conf import settings


class DocumentType:
    RE_21 = "re_21"
    RE_10 = "re_10"
    RE_11 = "re_11"
    RE_13 = "re_13"
    RE_14 = "re_14"
    AGENCY_DISCLOSURE = "agency_disclosure"
    LEAD_PAINT = "lead_based_paint"


class PDFGenerationService:
    # 2. Update the initialization to take doc_type instead of a hardcoded path
    def __init__(self, doc_type: str):
        self.doc_type = doc_type
        self.template_path = self._get_template_path(doc_type)

    # 3. Add the internal router that matches the type to the correct file
    def _get_template_path(self, doc_type: str) -> str:
        """Routes the requested document type to the correct blank PDF template."""
        templates = {
            DocumentType.RE_21: 're21_2026.pdf',
            DocumentType.RE_10: 'RE-10_Inspection_Contingency_Notice_all_fields.pdf',
            DocumentType.RE_11: 'RE-11_Addendum_full_fields.pdf',
            DocumentType.RE_13: 'RE-13_Counter_Offer_all_fields.pdf',
            DocumentType.RE_14: 'RE-14_Buyer_Representation_Agreement_all_fields.pdf',
            DocumentType.AGENCY_DISCLOSURE: 'Agency_Disclosure_Brochure_All_Fields.pdf',
            DocumentType.LEAD_PAINT: 'Lead_Based_Paint_Disclosure_All_Fields.pdf',
        }

        file_name = templates.get(doc_type)
        if not file_name:
            raise ValueError(f"Unknown document type requested: {doc_type}")

        return os.path.join(settings.BASE_DIR, 'static', 'pdfs', file_name)

    def generate_pdf(self, form_data: dict) -> bytes:
        # Load the blank template we determined in __init__
        doc = fitz.open(self.template_path)

        # 1. ROUTE TO THE CORRECT MAPPING FUNCTION
        if self.doc_type == DocumentType.RE_21:
            field_map = self._map_re21(form_data)
        elif self.doc_type == DocumentType.RE_10:
            field_map = self._map_re10(form_data)
        elif self.doc_type == DocumentType.RE_11:
            field_map = self._map_re11(form_data)
        elif self.doc_type == DocumentType.RE_13:
            field_map = self._map_re13(form_data)
        elif self.doc_type == DocumentType.RE_14:
            field_map = self._map_re14(form_data)
        elif self.doc_type == DocumentType.AGENCY_DISCLOSURE:
            field_map = self._map_agency_disclosure(form_data)
        elif self.doc_type == DocumentType.LEAD_PAINT:
            field_map = self._map_lead_based_paint(form_data)
        else:
            raise ValueError(f"No mapping function defined for {self.doc_type}")

        # 2. POPULATE THE PDF (Your existing logic)
        for page in doc:
            for annot in page.widgets():
                field_name = getattr(annot, "field_name", "")
                if field_name in field_map:
                    value_to_insert = str(field_map[field_name])

                    # If it's a true Checkbox/Radio button
                    if annot.field_type == fitz.PDF_WIDGET_TYPE_BUTTON:
                        if value_to_insert.lower() in ["true", "x", "yes", "on"]:
                            annot.field_value = "Yes"
                        else:
                            annot.field_value = "Off"

                    # If it's a Text Field
                    elif annot.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
                        annot.field_value = value_to_insert
                        if value_to_insert == "X":
                            annot.text_quadding = 1

                    annot.update()

        # Optional: Flatten all pages
        for page in doc:
            page.clean_contents()

        return doc.tobytes(garbage=4, deflate=True)

    # MARK: - The Master Field Map

    def _map_re21(self, data: dict) -> dict:
        map = {}

        # --- FORMATTERS ---
        def format_currency(val):
            try:
                return f"${int(float(val)):,}"
            except (ValueError, TypeError):
                return ""

        def spell_out_currency(val):
            try:
                # Converts 450000 to "four hundred fifty thousand" and capitalizes it
                return num2words(float(val)).title()
            except (ValueError, TypeError):
                return ""

        def format_date(date_str):
            if not date_str:
                return ""
            try:
                # Handle ISO formatting from Swift JSON encoding
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%m/%d/%Y")
            except ValueError:
                return date_str  # Return raw if already formatted

        # --- HARDCODED AGENT DEFAULTS ---
        map["SELLING BROKERAGE"] = "Keller Williams Realty"
        map["Selling Agent"] = "Ian Schoenrock"

        responsible_broker = data.get("responsibleBroker")
        if responsible_broker:
            map["Responsible_Broker"] = responsible_broker

        # --- DATES ---
        today_str = datetime.now().strftime("%m/%d/%Y")

        # --- CLIENT & PROPERTY ---
        buyer_name = data.get("buyerName", "")
        buyer_name_two = data.get("buyerNameTwo", "")
        seller_name = data.get("sellerName", "")
        seller_name_two = data.get("sellerNameTwo", "")

        map["1 BUYER"] = buyer_name + " and " + buyer_name_two
        map["BUYER Print Name"] = buyer_name
        map["BUYER Print Name_2"] = buyer_name_two
        map["SELLER Print Name"] = seller_name
        map["SELLER Print Name_2"] = seller_name_two

        # map["Phone_3"] = data.get("buyerPhone", "")
        # map["EMail_3"] = data.get("buyerEmail", "")

        address = data.get("propertyAddress", "")
        city = data.get("propertyCity", "")
        state = data.get("propertyState", "")
        zip_code = data.get("propertyZip", "")

        map["PROPERTY COMMONLY KNOWN AS"] = address
        map["City"] = city
        map["County"] = data.get("propertyCounty", "")
        map["Zip"] = zip_code
        map["ID Zip"] = zip_code

        # Full Address for page headers
        full_address_parts = [address, city, state, zip_code]
        full_address = ", ".join([p for p in full_address_parts if p])
        map["PROPERTY ADDRESS"] = full_address
        for i in range(2, 10):
            map[f"PROPERTY ADDRESS_{i}"] = full_address

        if data.get("legalDescription"):
            map["legally described as"] = data.get("legalDescription")
            map["OR Legal Description Attached as exhibit"] = data.get("parcelNumber", "")

        # --- FINANCIALS ---
        if data.get("offerPrice") is not None:
            map["2"] = format_currency(data.get("offerPrice"))
            map["PURCHASE PRICE"] = spell_out_currency(data.get("offerPrice"))

        if data.get("earnestMoney") is not None:
            map["A"] = format_currency(data.get("earnestMoney"))
            map["EARNEST MONEY"] = spell_out_currency(data.get("earnestMoney"))

        concessions = data.get("sellerConcessionAmount")
        if concessions is not None:
            concessions_val = float(concessions)
            if concessions_val <= 100:
                map["seller_agrees_purchase_price_percent"] = "X"
                map["Upon closing SELLER agrees to pay"] = str(concessions_val)
            else:
                map["seller_agrees_purchase_price_amount"] = "X"
                map["of the purchase price OR"] = format_currency(concessions_val)

        # --- LENDER REQUIRED REPAIRS ---
        #map["SELLER agrees to pay up to"] = format_currency(500)  # Default for testing

        # --- EARNEST MONEY DELIVERY & DEPOSIT ---
        em_delivered = data.get("earnestMoneyDelivered")
        if em_delivered == "with_offer":
            map["Earnest_Money_Delivered_Offer"] = "X"
        elif em_delivered == "within_days":
            map["Earnest_Money_Delivered_Days"] = "X"
            days = data.get("earnestMoneyDeliveredDays")
            if days is not None:
                map["within"] = str(days)
                map["Within"] = str(days)
        elif em_delivered == "section_5":
            map["Earnest_Money_Delivered_Section_5"] = "X"

        em_deposited = data.get("earnestMoneyDeposited")
        if em_deposited == "upon_receipt_acceptance":
            map["Earnest_Money_Deposited_Receipt_And_Acceptance"] = "X"
        elif em_deposited == "upon_receipt_regardless":
            map["Earnest_Money_Deposited_Recepted_Regardless"] = "X"
        elif em_deposited == "section_5":
            map["Earnest_Money_Deposited_Section_5"] = "X"

        # --- NEW LOAN PROCEEDS (SECTION 3C) ---
        first_loan = float(data.get("firstLoanAmount", 0))
        second_loan = float(data.get("secondLoanAmount", 0)) if data.get("secondLoanAmount") else 0
        total_proceeds = first_loan + second_loan

        if total_proceeds > 0:
            map["C"] = format_currency(total_proceeds)

        if data.get("firstLoanAmount") is not None:
            map["FIRST LOAN of"] = format_currency(data.get("firstLoanAmount"))

        if data.get("secondLoanAmount") is not None:
            map["SECOND LOAN of"] = format_currency(data.get("secondLoanAmount"))

        offer_price = float(data.get("offerPrice", 0)) if data.get("offerPrice") else 0
        earnest_money = float(data.get("earnestMoney", 0)) if data.get("earnestMoney") else 0

        funds_due = offer_price - earnest_money - total_proceeds

        if funds_due > 0:
            # Note: You may need to verify in Acrobat if this field is named "D" or something wild like "Approximate_Funds_Due"
            map["D"] = format_currency(funds_due)

        if data.get("loanTermYears") is not None:
            map["for a period of"] = str(data.get("loanTermYears"))

        loan_rate_type = data.get("loanRateType")
        if loan_rate_type == "fixed":
            map["Fixed_Rate_checkbox_1"] = "X"
        elif loan_rate_type == "other":
            map["Other_Rate_1"] = "X"

        financing_type = data.get("financingType")
        if financing_type != "cash":
            loan_app_status = data.get("loanApplicationStatus", "has_applied")
            if loan_app_status == "has_applied":
                map["has_applied_checkbox"] = "X"
            elif loan_app_status == "shall_apply":
                map["shall_apply_checkbox"] = "X"
            map["LOAN APPLICATION BUYER has applied OR shall apply for such loans Within"] = "10"
            rate = data.get("loanInterestRate", "")
            if rate:
                map["with interest not to exceed"] = f"{rate}%"
            else:
                map["with interest not to exceed"] = ""

        # --- TIMELINES & AGENCIES ---
        if data.get("closingDate"):
            map["available to SELLER The closing shall be no later than Date"] = format_date(data.get("closingDate"))

        if data.get("inspectionPeriod") is not None:
            map[
                "Inspection Except for additional items or conditions specifically reserved in a Secondary Inspection below BUYER shall within"] = str(
                data.get("inspectionPeriod"))

        if data.get("inspectionSellerResponseDays") is not None:
            map["applicable Upon receipt of written notice SELLER shall have"] = str(
                data.get("inspectionSellerResponseDays"))

        if data.get("inspectionBuyerNegotiationDays") is not None:
            map[
                "4 If SELLER does not agree to correct BUYERS disapproved itemsconditions within the strict time period specified then within"] = str(
                data.get("inspectionBuyerNegotiationDays"))

        if data.get("titleCompany"):
            map["B TITLE COMPANY The parties agree that"] = data.get("titleCompany")
            map["Company located at"] = data.get("titleCompanyLocation", "")

        # --- SECTION 11: TITLE INSURANCE TIMELINES ---
        furnisher = data.get("titleCommitmentFurnishedBy")
        if furnisher == "seller":
            map["Title_seller_checkbox"] = "X"
        elif furnisher == "buyer":
            map["Title_buyer_checkbox"] = "X"

        if data.get("titleCommitmentDays") is not None:
            map["title_within_days"] = str(data.get("titleCommitmentDays"))

        if data.get("titleObjectionDays") is not None:
            map["buyer_within_days_title_after_receipt"] = str(data.get("titleObjectionDays"))

        if data.get("titleSellerCureDays") is not None:
            map["seller_within_days_title"] = str(data.get("titleSellerCureDays"))

        if data.get("titleSellerTerminateDays") is not None:
            map["seller_termination_within_days"] = str(data.get("titleSellerTerminateDays"))

        # --- SECTION 40 CLOSING ---
        if data.get("closingAgency"):
            map["COMPANY for this transaction shall be"] = data.get("closingAgency")
            map["located at"] = "123 Title Way, Idaho Falls, ID"
        map["term escrow holder shall be"] = "N/A"

        # --- SECTION 42 POSSESSION ---
        is_testing_possession = False
        if is_testing_possession:
            map["key_upon_date"] = "X"
            map["42 POSSESSION BUYER shall be entitled to possession and keys upon closing or date"] = today_str
            map["time"] = "12:00"
            map["pm_posession"] = "X"
        else:
            map["key_upon_closing"] = "X"

        exp_time = data.get("offerExpirationTime")
        if exp_time:
            upper_time = exp_time.upper()
            if "PM" in upper_time:
                map["acceptance_pm"] = "X"
            elif "AM" in upper_time:
                map["acceptance_am"] = "X"

            clean_time = upper_time.replace("PM", "").replace("AM", "").strip()
            map["at Local Time in which PROPERTY is located"] = clean_time

        exp_date = data.get("offerExpirationDate")
        if exp_date:
            # Note: Replace "Offer_Expiration_Date" with the exact field name from Acrobat!
            map["Date_16"] = format_date(exp_date)

        # --- SECTION 43 PRORATIONS ---
        proration_type = data.get("prorationType")
        if proration_type == "closing":
            map["prorated_on_closing"] = "X"
        elif proration_type == "date":
            map["prorated_on_date"] = "X"
            if data.get("prorationDate"):
                map["42 POSSESSION BUYER shall be entitled to possession and keys upon closing or date"] = format_date(
                    data.get("prorationDate"))

        fuel = data.get("buyerReimburseFuel")
        if fuel == "yes":
            map["buyer_reimburse_seller_for_fuel_tank_yes"] = "X"
        elif fuel == "no":
            map["buyer_reimburse_seller_for_fuel_tank_no"] = "X"
        elif fuel == "na":
            map["buyer_reimburse_seller_for_fuel_tank_n_a"] = "X"

        if data.get("isAssignable", True):
            map["interests_may_be_sold"] = "X"
        else:
            map["interests_may_not_be_sold"] = "X"

        # --- MANUAL CHECKBOXES ---
        if data.get("isContingentOnSale", False):
            map["Contingent_Sale_Checkbox_Yes"] = "X"
        else:
            map["Contingent_Sale_Checkbox_No"] = "X"

        em_form = data.get("earnestMoneyForm")
        if em_form == "cash":
            map["Earnest_Money_Evidence_Cash"] = "X"
        elif em_form == "personal_check":
            map["Earnest_Money_Evidence_Check"] = "X"
        elif em_form == "cashiers_check":
            map["Earnest_Money_Evidence_Cashiers_Check"] = "X"

        em_holder = data.get("earnestMoneyHolder")
        if em_holder == "listing_broker":
            map["Earnest_Money_Held_By_Broker"] = "X"
        elif em_holder == "closing_agency":
            map["Earnest_Money_Held_By_Company"] = "X"

        if financing_type != "cash":
            if financing_type == "fha":
                map["FHA_Checkbox_1"] = "X"
            elif financing_type == "va":
                map["VA_Checkbox_1"] = "X"
            elif financing_type == "conventional":
                map["Converntional_Checkbox_1"] = "X"  # Preserved original PDF typo
        else:
            map["finance_cash_yes"] = "X"

        # Inspections (Primary)
        if data.get("inspectionPeriod") is not None:
            map["yes_conduct_inspections_checkbox"] = "X"
        else:
            map["no_conduct_inspections_checkbox"] = "X"

        # Inspections (Secondary Specific Boxes)
        if data.get("wellPotabilityPayer", "na") != "na" or data.get("wellProductivityPayer", "na") != "na":
            map["well_water_within_days_checkbox"] = "X"
            map["well_water_within_days"] = str(data.get("wellWaterInspectionDays", 10))

        if data.get("septicInspectionPayer", "na") != "na" or data.get("septicPumpingPayer", "na") != "na":
            map["plumbing_within_days_checkbox"] = "X"
            map["plumbing_within_days"] = str(data.get("septicInspectionDays", 10))

        if data.get("surveyPayer", "na") != "na":
            map["survery_checkbox"] = "X"
            map["survey_checkbox"] = "X"
            map["survey_within_days"] = str(data.get("surveyInspectionDays", 10))
            map["survery_within_days"] = str(data.get("surveyInspectionDays", 10))
            map["Survey_within_days"] = str(data.get("surveyInspectionDays", 10))

        # --- ORDERED BY CHECKBOXES ---
        pot_order = data.get("wellPotabilityOrderer")
        if pot_order == "buyer":
            map["buyer_potability"] = "X"
        elif pot_order == "seller":
            map["seller_potability"] = "X"

        prod_order = data.get("wellProductivityOrderer")
        if prod_order == "buyer":
            map["buyer_productivity"] = "X"
        elif prod_order == "seller":
            map["seller_productivity"] = "X"

        sept_order = data.get("septicInspectionOrderer")
        if sept_order == "buyer":
            map["buyer_septic"] = "X"
        elif sept_order == "seller":
            map["seller_septic"] = "X"

        pump_order = data.get("septicPumpingOrderer")
        if pump_order == "buyer":
            map["buyer_septic_pumping"] = "X"
        elif pump_order == "seller":
            map["seller_septic_pumping"] = "X"

        surv_order = data.get("surveyOrderer")
        if surv_order == "buyer":
            map["buyer_survey"] = "X"
        elif surv_order == "seller":
            map["seller_survery"] = "X"  # Preserved original PDF typo

        # Occupancy Checkbox
        if data.get("intendsToOccupy", True):
            map["buyer_occupies_as_primary"] = "X"
        else:
            map["buyer_does_not_occupy_as_primary"] = "X"

        # Agency Checkboxes
        b_agency = data.get("buyerAgency")
        if b_agency == "agent":
            map["agent_for_buyers"] = "X"
        elif b_agency == "limitedDual":
            map["limited_dual_agent_for_buyers"] = "X"
        elif b_agency == "limitedDualAssigned":
            map["limited_dual_agent_with_assigned_agent_for_buyers"] = "X"
        elif b_agency == "nonagent":
            map["nonagent_for_buyers"] = "X"

        s_agency = data.get("sellerAgency")
        if s_agency == "agent":
            map["agent_for_sellers"] = "X"
        elif s_agency == "limitedDual":
            map["limited_duel_agent_for_sellers"] = "X"  # Preserved original PDF typo
        elif s_agency == "limitedDualAssigned":
            map["limited_dual_agent_with_assigned_agent_for_sellers"] = "X"
        elif s_agency == "nonagent":
            map["nonagent_for_sellers"] = "X"

        # Section 17 & 18
        disclosure = data.get("buyerReceivedDisclosure")
        if disclosure == "yes":
            map["buyer_received_disclosure_yes"] = "X"
        elif disclosure == "no":
            map["buyer_received_disclosure_no"] = "X"
        elif disclosure == "na":
            map["buyer_received_disclosure_n_a"] = "X"

        hoa_docs = data.get("buyerReviewedHOADocs")
        if hoa_docs == "yes":
            map["hoa_docs_yes"] = "X"
        elif hoa_docs == "no":
            map["hoa_docs_no"] = "X"
        elif hoa_docs == "na":
            map["hoa_docs_n_a"] = "X"

        if data.get("hoaDues") is not None:
            map["Homeowners Association Documents Yes No NA Association dues are"] = format_currency(
                data.get("hoaDues"))

            freq = data.get("hoaDuesFrequency", "monthly")
            if freq == "annually":
                map["per"] = "year"
            else:
                map["per"] = "month"

        if data.get("hoaSetupFee") is not None:
            map["BUYER SELLER Shared Equally NA to pay Association SET UP FEE of"] = format_currency(
                data.get("hoaSetupFee"))

        setup_fee_payer = data.get("hoaSetupFeePayer")
        if setup_fee_payer == "buyer":
            map["buyer_setup_fee_checkbox"] = "X"
        elif setup_fee_payer == "seller":
            map["seller_setup_fee_checkbox"] = "X"
        elif setup_fee_payer == "shared":
            map["setup_fee_shared"] = "X"
        elif setup_fee_payer == "na":
            map["n_a_setup_fees"] = "X"

        if data.get("hoaTransferFee") is not None:
            map["BUYER SELLER Shared Equally NA to pay Association PROPERTY TRANSFER FEES of"] = format_currency(
                data.get("hoaTransferFee"))

        transfer_fee_payer = data.get("hoaTransferFeePayer")
        if transfer_fee_payer == "buyer":
            map["buyer_transfer_fee"] = "X"
        elif transfer_fee_payer == "seller":
            map["seller_transfer_fee"] = "X"
        elif transfer_fee_payer == "shared":
            map["Transfer_fees_shared_equally_check"] = "X"
        elif transfer_fee_payer == "na":
            map["n_a_transfer_fees"] = "X"

        # --- SECTION 20: SELLING BROKERAGE COMPENSATION ---
        is_testing_brokerage_comp = True
        if is_testing_brokerage_comp:
            map["seller_payer_selling_brokerage"] = "X"
            map["SELLER agrees to pay Selling Brokerage compensation of an amount equal to"] = "3"
            map["of the final sales price OR other"] = format_currency(5000)
        else:
            map["selling_brokerage_does_not_need_to_be_addressed"] = "X"

        # --- SECTION 22 & 24 ---
        if data.get("intends1031Exchange", False):
            map["does_tax_deferred_checkbox"] = "X"
        else:
            map["does_not_tax_deferred_checkbox"] = "X"

        map[
            "the PROPERTY NOT AS A CONTINGENCY OF THE SALE but for the following stated purposes first walkthrough shall be within"] = "3"
        map[
            "BUYER that any repairs agreed to in writing by BUYER and SELLER have been completed The second walkthrough shall be within"] = "3"
        is_built_before_1979 = data.get("isBuiltBefore1979", False)

        if is_built_before_1979:
            # Note: Double check Acrobat to make sure this is the exact name of the "Yes" box!
            map["is_target_housing_checkbox"] = "X"
        else:
            map["is_not_target_housing_checkbox"] = "X"
        map["buyer_does_not_wave"] = "X"

        # --- THE COST GRID (Page 6) ---
        def set_grid(payer, suffix):
            prefix_map = {
                "buyer": "BUYER",
                "seller": "SELLER",
                "shared": "Shared Equally",
                "na": "NA"
            }
            prefix = prefix_map.get(payer, "NA ")
            map[prefix + suffix] = "X"

        set_grid(data.get("appraisalFeePayer", "na"), "Appraisal Fee")
        set_grid(data.get("appraisalReInspectionFeePayer", "na"), "Appraisal ReInspection Fee")
        set_grid(data.get("closingEscrowFeePayer", "na"), "Closing Escrow Fee")
        set_grid(data.get("lenderDocPrepFeePayer", "na"), "Lender DocumentProcessing Fee")
        set_grid(data.get("taxServiceFeePayer", "na"), "Lender Tax Service Fee")
        set_grid(data.get("floodCertFeePayer", "na"), "Flood CertificationTracking Fee")
        set_grid(data.get("lenderInspectionsPayer", "na"), "Lender Required Inspections")
        set_grid(data.get("attorneyFeePayer", "na"), "Attorney Contract Preparation or Review Fee")
        set_grid(data.get("additionalTitlePayer", "na"), "Additional Title Coverage")
        set_grid(data.get("titleExtendedPayer", "na"), "Title Ins Extended Coverage Lenders Policy  Mortgagee Policy")
        set_grid(data.get("titleInsurancePayer", "na"), "Title Ins Standard Coverage Owners Policy")
        set_grid(data.get("wellPotabilityPayer", "na"),
                 "Domestic Well Water Potability Test Shall be ordered by BUYER SELLER")
        set_grid(data.get("wellProductivityPayer", "na"),
                 "Domestic Well Water Productivity Test Shall be ordered by BUYER SELLER")
        set_grid(data.get("septicInspectionPayer", "na"), "Septic Inspections Shall be ordered by BUYER SELLER")
        set_grid(data.get("septicPumpingPayer", "na"), "Septic Pumping Shall be ordered by BUYER SELLER")
        set_grid(data.get("surveyPayer", "na"), "Survey Shall be ordered by BUYER SELLER")
        set_grid("na", "Water RightsShares Transfer Fee")

        set_grid("na", "Attorney Contract Preparation or Review FeeRow1")
        set_grid("na", "Attorney Contract Preparation or Review FeeRow2")
        set_grid("na", "Attorney Contract Preparation or Review FeeRow3")
        set_grid("na", "Water RightsShares Transfer FeeRow1")
        set_grid("na", "Water RightsShares Transfer FeeRow2")

        # --- MULTI-LINE TEXT BOXES ---
        contingencies = data.get("contingencies", [])
        if contingencies:
            list_str = "\n".join(
                [f"- {c.get('type', '').capitalize()}: {c.get('description', '')}" for c in contingencies])
            map["Other_Terms"] = list_str
        else:
            map["Other_Terms"] = ""

        additional = data.get("additionalTerms", "")
        map["Additional_Items"] = additional
        map["Additional_Terms"] = additional

        excluded = data.get("excludedItems", "")
        map["Items_Excluded"] = excluded
        map["Excluded_Terms"] = excluded

        # Buyer 1 Mapping Specifics
        buyer_name = data.get("buyerName", "").strip()
        buyer_name_two = data.get("buyerNameTwo", "").strip()
        has_second_buyer = bool(buyer_name_two)

        # Buyer 1 Mapping
        map["BUYER Print Name"] = buyer_name
        map["DocuSignHere_1"] = "\\s1\\"

        # DocuSign Initial Tags (Offsets)
        initial_offsets = [1, 5, 9, 13, 17, 21, 25, 29, 33]

        for num in initial_offsets:
            # Buyer 1 Initial
            map[f"DocuSignSignHere_{num}"] = "\\i1\\"

            # Buyer 2 Initial (Only tag if they exist)
            if has_second_buyer:
                map[f"DocuSignSignHere_{num + 1}"] = "\\i2\\"

            # Seller 1 & 2 Initials (Pre-Tagging for the listing agent)
            map[f"DocuSignSignHere_{num + 2}"] = "\\i3\\"
            map[f"DocuSignSignHere_{num + 3}"] = "\\i4\\"

        # Buyer 2 Mapping Specifics
        if has_second_buyer:
            map["BUYER Print Name_2"] = buyer_name_two
            map["DocuSignHere_2"] = "\\s2\\"
            print(f"DEBUG: Mapping Buyer 2 ({buyer_name_two}) to DocuSignHere_2")
        else:
            map["BUYER Print Name_2"] = ""
            map["DocuSignHere_2"] = "\\s2\\"
            print("DEBUG: Only one buyer detected.")
        # Seller Signatures (Note: check your Acrobat case-sensitivity for 'DocuSign' vs 'Docusign')
        map["DocuSignHere3"] = "\\s3\\"
        map["DocuSignHere4"] = "\\s4\\"

        return map


    def _map_re10(self, data: dict) -> dict:
        """The master map for the RE-10 Inspection Contingency Notice."""
        map = {}

        def format_currency(val):
            try:
                return f"${int(float(val)):,}"
            except (ValueError, TypeError):
                return ""

        today_str = datetime.now().strftime("%m/%d/%Y")

        # --- HEADER INFO ---
        map['This NOTICE dated'] = today_str
        map['3 This NOTICE pertains to the Purchase and Sale Agreement Dated'] = data.get("psaDate", "")
        map['5 ADDRESS'] = data.get("propertyAddress", "")
        map['PROPERTY ADDRESS'] = data.get("propertyAddress", "")  # Page 2 header
        map['1 BUYER'] = data.get("buyerName", "")
        map['9 SELLER'] = data.get("sellerName", "")

        # Default to Buyer sending to Seller (Standard TC workflow)
        map['Buyer_notice_to_seller'] = "X"

        # --- CONTINGENCY TYPE ---
        inspection_type = data.get("inspectionType", "primary")
        if inspection_type == "primary":
            map['Primary_inspection_contingency'] = "X"
        elif inspection_type == "secondary":
            map['Secondary_inspection_contingency'] = "X"

            # Sub-types for Secondary
            sec_type = data.get("secondaryType", "")
            if sec_type == "well":
                map['domestic_well'] = "X"
            elif sec_type == "septic":
                map['septic_instepction'] = "X"
            elif sec_type == "survey":
                map['survey'] = "X"

        # --- THE DECISION (REMOVAL vs ADDRESS vs TERMINATE) ---
        decision = data.get("re10Decision", "address")  # remove, address, terminate

        if decision == "remove":
            map['removal_of_inspection'] = "X"

        elif decision == "terminate":
            map['termination_provision'] = "X"

        elif decision == "address":
            map['items_to_be_addressed'] = "X"

            # Credits
            credit = data.get("sellerCredit")
            if credit:
                map['seller_will_credit_buyer'] = "X"
                map['38  SELLER will credit BUYER'] = format_currency(credit)

            # Price Reduction
            new_price = data.get("newPurchasePrice")
            if new_price:
                map['purchase_price_checkbox'] = "X"
                map['39 D Purchase Price to be'] = format_currency(new_price)

            # Repairs
            repairs_text = data.get("repairRequests", "")
            if repairs_text:
                map['seller_will_service'] = "X"

                # The exact line fields from the PDF discovery
                repair_line_fields = [
                    '42', '45', '46', '47', '48', '49', '50', '51', '52', '53',
                    '54', '55', '56', '57', '58', '59', '60', '62', '64', '66',
                    '68', '69', '71', '72', '73', '76', '77', '80'
                ]

                # Wrap text to ~85 characters per line to fit the PDF boundaries safely
                wrapped_lines = textwrap.wrap(repairs_text, width=85)

                # Map the wrapped text to the sequential PDF line fields
                for i, line_text in enumerate(wrapped_lines):
                    if i < len(repair_line_fields):
                        field_key = repair_line_fields[i]
                        map[field_key] = line_text

        # --- DOCUSIGN TAGS ---
        # Page 1 Initials
        map['buyer_initial_one_page_one'] = "\\i1\\"
        if data.get("hasSecondBuyer", False):
            map['buyer_initial_two_page_one'] = "\\i2\\"

        # Page 2 Signatures
        map['95 BUYER'] = "\\s1\\"
        if data.get("hasSecondBuyer", False):
            map['97 BUYER'] = "\\s2\\"

        return map


    def _map_re11(self, data: dict) -> dict:
        """The master map for the RE-11 Addendum."""
        map = {}

        today_str = datetime.now().strftime("%m/%d/%Y")

        # --- HEADER INFO ---
        map['ADDENDUM'] = str(data.get("addendumNumber", "1"))
        map['Todays Date'] = today_str
        map['7 AGREEMENT DATED'] = data.get("psaDate", "")
        map['9 ADDRESS'] = data.get("propertyAddress", "")
        map['11 BUYERS'] = data.get("buyerName", "")
        map['13 SELLERS'] = data.get("sellerName", "")

        # Default to modifying the main Purchase and Sale Agreement
        map['Purchase_and_sale_agreement'] = "X"

        # --- ADDENDUM BODY TEXT ---
        body_text = data.get("addendumText", "")
        if body_text:
            # The exact line fields from the PDF discovery (16 through 46)
            body_line_fields = [str(i) for i in range(16, 47)]

            # Wrap text to ~85 characters per line to fit the PDF boundaries safely
            wrapped_lines = textwrap.wrap(body_text, width=85)

            # Map the wrapped text to the sequential PDF line fields
            for i, line_text in enumerate(wrapped_lines):
                if i < len(body_line_fields):
                    field_key = body_line_fields[i]
                    map[field_key] = line_text

        # --- DOCUSIGN TAGS ---
        # Buyer Signatures
        map['53 BUYER'] = "\\s1\\"
        if data.get("hasSecondBuyer", False):
            map['55 BUYER'] = "\\s2\\"

        # Seller Signatures (Pre-tagged for the listing agent's clients)
        map['57 SELLER'] = "\\s3\\"
        if data.get("hasSecondSeller", False):
            map['59 SELLER'] = "\\s4\\"

        return map

    def _map_re13(self, data: dict) -> dict:
        """The master map for the RE-13 Counter Offer."""
        map = {}

        def format_date(date_str):
            if not date_str: return ""
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%m/%d/%Y")
            except ValueError:
                return date_str

        today_str = datetime.now().strftime("%m/%d/%Y")

        # --- HEADER INFO ---
        map['RE13 COUNTER OFFER'] = str(data.get("counterOfferNumber", "1"))
        map['Todays Date'] = today_str
        map['3 This is a COUNTER OFFER to the Purchase and Sale Agreement Dated'] = format_date(data.get("psaDate", ""))
        map['5 ADDRESS'] = data.get("propertyAddress", "")
        map['7 BUYER'] = data.get("buyerName", "")
        map['9 SELLER'] = data.get("sellerName", "")

        # --- ORIGINATOR ---
        # Determines which box is checked at the top
        is_seller_counter = data.get("isSellerCounter", True)
        if is_seller_counter:
            map['seller_counter_offer'] = "X"
        else:
            map['buyer_counter_offer'] = "X"

        # --- ATTACHMENTS ---
        attached_addendums = data.get("attachedAddendums", "")
        if attached_addendums:
            map['counter_offer_includes_addendum'] = "X"
            map['17 COUNTEROFFER INCLUDES ATTACHED ADDENDUMS'] = attached_addendums

        attached_exhibits = data.get("attachedExhibits", "")
        if attached_exhibits:
            map['counter_offer_includes_exhibit'] = "X"
            map['18 COUNTEROFFER INCLUDES ATTACHED EXHIBITS'] = attached_exhibits

        # --- COUNTER OFFER BODY TEXT ---
        body_text = data.get("counterOfferText", "")
        if body_text:
            # The exact line fields from the PDF discovery (19 through 40)
            body_line_fields = [str(i) for i in range(19, 41)]

            # Wrap text to ~85 characters per line to fit the PDF boundaries safely
            wrapped_lines = textwrap.wrap(body_text, width=85)

            # Map the wrapped text to the sequential PDF line fields
            for i, line_text in enumerate(wrapped_lines):
                if i < len(body_line_fields):
                    field_key = body_line_fields[i]
                    map[field_key] = line_text

        # --- EXPIRATION DEADLINE ---
        exp_date = data.get("offerExpirationDate", "")
        if exp_date:
            map['51 before date'] = format_date(exp_date)

        exp_time = data.get("offerExpirationTime", "")
        if exp_time:
            upper_time = exp_time.upper()
            if "AM" in upper_time:
                map['Before_date_am'] = "X"
            elif "PM" in upper_time:
                map['Before_date_pm'] = "X"

            clean_time = upper_time.replace("AM", "").replace("PM", "").strip()
            map['at'] = clean_time

        # --- DOCUSIGN TAGS ---
        # Sellers (Top block in signature area)
        map['56 SELLER'] = "\\s3\\"
        if data.get("hasSecondSeller", False):
            map['58 SELLER'] = "\\s4\\"

        # Buyers (Bottom block in signature area)
        map['60 BUYER'] = "\\s1\\"
        if data.get("hasSecondBuyer", False):
            map['62 BUYER'] = "\\s2\\"

        return map


    def _map_re14(self, data: dict) -> dict:
        """The master map for the RE-14 Buyer Representation Agreement."""
        map = {}

        def format_date(date_str):
            if not date_str: return ""
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%m/%d/%Y")
            except ValueError:
                return date_str

        today_str = datetime.now().strftime("%m/%d/%Y")

        buyer_1 = data.get("buyerName", "")
        buyer_2 = data.get("buyerNameTwo", "")
        both_buyers = f"{buyer_1} and {buyer_2}" if buyer_2 else buyer_1

        # --- HEADER INFO ---
        map['buyer_name'] = both_buyers
        map['3 1 BUYER'] = both_buyers
        map['BUYERS NAMES'] = both_buyers  # Page 2 header
        map['BUYERS NAMES_2'] = both_buyers  # Page 3 header
        map['Broker of'] = both_buyers

        map['Acting as Agent for the Broker'] = data.get("agentName", "Ian Schoenrock")

        # --- PROPERTY CRITERIA ---
        prop_type = data.get("propertyType", "residential")  # residential, income, commercial, land, build, other
        if prop_type == "residential":
            map['residential'] = "X"
        elif prop_type == "income":
            map['residential_income'] = "X"
        elif prop_type == "commercial":
            map['commercial'] = "X"
        elif prop_type == "land":
            map['vacant_land'] = "X"
        elif prop_type == "build":
            map['custom_build_land'] = "X"
        else:
            map['Other'] = "X"

        map['19 Applicable Citys'] = data.get("searchCity", "")
        map[' Idaho'] = data.get("searchState", "Idaho")
        map['20 Applicable Countys'] = data.get("searchCounty", "")
        map['21 Other Description ie geographical area price etc'] = data.get("searchDescription", "")

        # --- TERM ---
        map[
            '23 2 TERM OF AGREEMENT This BUYER REPRESENTATION AGREEMENT herein after referred to as Agreement is in force from'] = format_date(
            data.get("startDate", today_str))
        map['and will expire at 11 59 pm on date'] = format_date(data.get("endDate", ""))

        # --- COMPENSATION ---
        comp_type = data.get("compensationType", "percentage")
        if comp_type == "percentage":
            map['Percentage_of_sales'] = "X"
            # Maps to the __% line
            map[
                'Buyer instructs the Broker to seek to obtain this fee through the transaction paid by the seller or'] = str(
                data.get("compensationPercentage", "3"))

            flat_fee = data.get("compensationFlatFee")
            if flat_fee:
                # Maps to the $___ flat fee line
                map[
                    '41 the listing brokerage If the fee cannot be obtained through the seller or the listing brokerage the BUYER will be responsible for the fee'] = str(
                    flat_fee)

        # --- CANCELLATION FEE ---
        map[
            '65 and as a special condition of this agreement BUYER shall be liable to Broker for a cancellation fee equal to'] = str(
            data.get("cancellationPercentage", "3"))

        # --- OTHER TERMS ---
        map['171 16 OTHER TERMS AND CONDITIONS'] = data.get("otherTerms", "")

        # --- AGENCY ELECTION (PAGE 3) ---
        agency_type = data.get("agencyType", "dual")  # 'dual' or 'single'

        if agency_type == "dual":
            map['buyer_one_dual_agency'] = "\\i1\\"
            if buyer_2:
                map['buyer_two_dual_agency'] = "\\i2\\"
        else:
            map['buyer_one_single_agency'] = "\\i1\\"
            if buyer_2:
                map['buyer_two_single_agency'] = "\\i2\\"

        # --- BOTTOM OF PAGE INITIALS ---
        # DocuSign will automatically drop initials wherever it finds these tags
        map['undefined_2'] = "\\i1\\"  # Page 1 bottom
        map['undefined_3'] = "\\i1\\"  # Page 2 bottom
        map['undefined_4'] = "\\i1\\"  # Page 3 bottom

        # --- SIGNATURES (PAGE 4) ---
        # Since standard signature fields can block PyMuPDF, we drop the invisible
        # \s1\ anchors into the nearby text fields (like Date and Phone).

        map['Date_4'] = "\\s1\\"  # Buyer 1 Signature Anchor
        map['211 Phone'] = data.get("buyerPhone", "")
        map['Email'] = data.get("buyerEmail", "")

        if buyer_2:
            map['Date_6'] = "\\s2\\"  # Buyer 2 Signature Anchor
            map['217 Phone'] = data.get("buyerTwoPhone", "")
            map['Email_3'] = data.get("buyerTwoEmail", "")

        map['Date_5'] = "\\s3\\"  # Agent Signature Anchor
        map['Agent Phone'] = data.get("agentPhone", "")
        map['Email_4'] = data.get("agentEmail", "")

        return map

    def _map_agency_disclosure(self, data: dict) -> dict:
        """The master map for the Idaho Agency Disclosure Brochure."""
        map = {}

        # --- BROKERAGE INFO (PAGE 2) ---
        # ⚠️ NOTE: Replace these keys with the exact field names from your discovery script!
        map['BROKERAGE'] = data.get("brokerageName", "Top Notch Real Estate")
        map['DESIGNATED BROKER'] = data.get("designatedBroker", "")
        map['PHONE NUMBER'] = data.get("brokeragePhone", "")

        # --- DOCUSIGN TAGS (PAGE 2) ---
        # We will use DocuSign anchor tags for the signatures.
        # ⚠️ NOTE: Replace 'Signature_1' and 'Signature_2' with the actual PDF field names.
        map['Signature_1'] = "\\s1\\"

        if data.get("hasSecondBuyer", False):
            map['Signature_2'] = "\\s2\\"

        return map

    def _map_lead_based_paint(self, data: dict) -> dict:
        """The master map for the Lead-Based Paint Disclosure."""
        map = {}

        # --- HEADER INFO ---
        map['Address'] = data.get("propertyAddress", "")

        has_second_buyer = data.get("hasSecondBuyer", False)

        # --- BUYER INITIALS (SECTIONS C, D, E) ---
        # DocuSign will prompt the buyer to initial everywhere we drop \i1\

        # (c) Purchaser has received copies of records OR no records
        received_records = data.get("receivedRecords", False)
        if received_records:
            map['c Purchaser has initial i or ii below'] = "\\i1\\"
        else:
            map['based paint hazards in the housing listed above'] = "\\i1\\"

        # (d) Purchaser has received the pamphlet
        map['hazards in the housing'] = "\\i1\\"

        # (e) 10-day inspection window OR waived inspection
        waived_inspection = data.get("waivedInspection", True)
        if waived_inspection:
            map['or inspection for the presence of leadbased paint andor lead based paint hazards or'] = "\\i1\\"
        else:
            map['e Purchaser has initial i or ii below'] = "\\i1\\"

        # --- AGENT INITIALS (SECTION G) ---
        map['hisher responsibility to ensure compliance'] = "\\i3\\"  # Agent initials

        # --- SIGNATURES ---
        # Since 'Seller' and 'Seller_2' were captured by your script, they are likely
        # the first two signature lines. We will drop the invisible tags there.
        # Ensure you double check these in Acrobat if the signatures don't align perfectly!
        map['Seller'] = "\\s1\\"
        if has_second_buyer:
            map['Seller_2'] = "\\s2\\"

        map['have provided is true and accurate'] = "\\s3\\"  # Agent Signature

        return map

