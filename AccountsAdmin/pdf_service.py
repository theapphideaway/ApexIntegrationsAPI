import re

import fitz  # PyMuPDF
import os
from datetime import datetime
from num2words import num2words


class PDFGenerationService:
    def __init__(self, template_path):
        self.template_path = template_path

    def generate_pdf(self, form_data: dict) -> bytes:
        if not os.path.exists(self.template_path):
            raise FileNotFoundError("Could not find the blank RE-21 template in the specified path.")

        doc = fitz.open(self.template_path)
        field_map = self._build_field_map(form_data)

        for page in doc:
            widgets_to_delete = []

            # 1. Iterate specifically over form fields (widgets), not generic annotations
            for annot in page.widgets():

                # 2. Grab the actual human-readable AcroForm name
                field_name = getattr(annot, "field_name", "")
                if not field_name:
                    continue

                # Intercept Signature Fields
                is_sig = (annot.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE)
                is_labeled_sig = "signature" in field_name.lower()

                if is_sig or is_labeled_sig:
                    continue

                # Handle Standard Text Fields
                if field_name in field_map:
                    value_to_insert = str(field_map[field_name])
                    print(f"DEBUG: Inserting '{value_to_insert}' into '{field_name}'")
                    # --- TARGETED OVERRIDE FOR DOCUSIGN TEXT TAGS (\s1\, etc.) ---
                    if "\\s" in value_to_insert or "\\i" in value_to_insert:
                        rect = annot.rect
                        widgets_to_delete.append(annot)

                        # Log the coordinates so we can see if the box is 'empty'
                        print(f"DEBUG: Printing {value_to_insert} at Rect: {rect}")

                        # Use insert_text instead of insert_textbox to bypass 'fit' checks
                        # we use rect.bl (bottom-left) and nudge it up 2 pixels so it doesn't hit the line
                        page.insert_text(
                            (rect.x0, rect.y1 - 2),
                            value_to_insert,
                            fontsize=10,
                            color=(1, 1, 1)  # Keep black for this test
                        )
                        continue

                    # --- STANDARD TEXT WIDGET LOGIC ---
                    annot.field_value = value_to_insert

                    if value_to_insert == "X":
                        annot.text_quadding = 1

                    # Lock down flat (Make Read-Only)
                    annot.update()

            # 3. Clean up replaced annotations using the dedicated widget deletion method
            for annot in widgets_to_delete:
                page.delete_widget(annot)
        return doc.tobytes(garbage=4, deflate=True)

    # MARK: - The Master Field Map

    def _build_field_map(self, data: dict) -> dict:
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

        # --- DATES ---
        today_str = datetime.now().strftime("%m/%d/%Y")

        # --- CLIENT & PROPERTY ---
        buyer_name = data.get("buyerName", "")
        buyer_name_two = data.get("buyerNameTwo", "")
        seller_name = data.get("sellerName", "")
        seller_name_two = data.get("sellerNameTwo", "")

        map["1 BUYER"] = buyer_name
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

        if data.get("loanTermYears") is not None:
            map["for a period of"] = str(data.get("loanTermYears"))

        loan_rate_type = data.get("loanRateType")
        if loan_rate_type == "fixed":
            map["Fixed_Rate_checkbox_1"] = "X"
        elif loan_rate_type == "other":
            map["Other_Rate_1"] = "X"

        financing_type = data.get("financingType")
        if financing_type != "cash":
            loan_app_status = data.get("loanApplicationStatus", "has_applied")  # Fallback to has_applied if missing
            if loan_app_status == "has_applied":
                map["has_applied_checkbox"] = "X"
            elif loan_app_status == "shall_apply":
                map["shall_apply_checkbox"] = "X"
            map["LOAN APPLICATION BUYER has applied OR shall apply for such loans Within"] = "10"
            map["with interest not to exceed"] = "6.1%"

        # --- TIMELINES & AGENCIES ---
        if data.get("closingDate"):
            map["available to SELLER The closing shall be no later than Date"] = format_date(data.get("closingDate"))

        if data.get("inspectionPeriod") is not None:
            map[
                "Inspection Except for additional items or conditions specifically reserved in a Secondary Inspection below BUYER shall within"] = str(
                data.get("inspectionPeriod"))

        if data.get("titleCompany"):
            map["B TITLE COMPANY The parties agree that"] = data.get("titleCompany")
            map["Company located at"] = data.get("titleCompany")

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
            map["well_water_within_days"] = "10"

        if data.get("septicInspectionPayer", "na") != "na" or data.get("septicPumpingPayer", "na") != "na":
            map["plumbing_within_days_checkbox"] = "X"
            map["plumbing_within_days"] = "10"

        if data.get("surveyPayer", "na") != "na":
            map["survery_checkbox"] = "X"
            map["survey_checkbox"] = "X"
            map["survey_within_days"] = "10"
            map["survery_within_days"] = "10"
            map["Survey_within_days"] = "10"

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
        map["is_not_target_housing_checkbox"] = "X"
        map["buyer_does_not_wave"] = "X"

        # --- THE COST GRID (Page 6) ---
        def set_grid(payer, suffix):
            prefix_map = {
                "buyer": "BUYER ",
                "seller": "SELLER ",
                "shared": "Shared Equally ",
                "na": "NA "
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

