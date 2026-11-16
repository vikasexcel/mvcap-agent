# ruff: noqa: C408
"""Authoring source for the MVCAP answering-service rules.

Everything here comes from the Oct 29, 2026 answering script. This file is only the
initial import: after the first push, the client edits the Supabase tables and this
file is no longer the source of truth. `build_data.py` turns it into the bundled
fallback snapshot and the seed migration.

message_source:
  "script"  - wording quoted verbatim from the script
  "drafted" - the script gives an instruction ("refer caller to AES"), so the spoken
              wording is ours; the client should review these
"""

SITE = "www.miamivalleycap.org"
HELPLINK_211 = "United Way HelpLink at 211"

EXT = "extension"
PHONE = "phone"

PRC_SITE = (
    f"Visit our website for more information and to apply. Go to {SITE}, click Programs, "
    "then click PRC. Applications are accepted only through the online portal."
)
GENERIC_PROGRAM_INFO = (
    "Each MVCAP program has unique application processes, eligibility requirements, and "
    f"documentation requirements. Please visit our website at {SITE} to learn these "
    "requirements for each of our programs."
)
OBERER = "This property is managed by Oberer Property Management. Please dial {number}."
COUNTY_PAGE = (
    "You can visit our website to learn more about the programs we offer to {county} County "
    f"Residents. Visit {SITE}, click Counties, then click {{county}} County Services. "
    "I'll transfer you to their office now."
)
SCHEDULE_STEPS = (
    f"Appointments can be scheduled on our website at {SITE}, click Programs, then click "
    "Utility Assistance, then click Montgomery County Residents, Schedule an In-Person Appointment."
)


def tgt(kind, value):
    return {"target_type": kind, "target": value}


def ext(n):
    return tgt(EXT, str(n))


def phone(digits):
    return tgt(PHONE, "+1" + "".join(c for c in digits if c.isdigit()))


KEYWORDS = []
BRANCHES = []


def kw(
    keyword,
    action,
    message=None,
    source="script",
    question=None,
    target=None,
    voicemail=False,
    notes=None,
):
    row = dict(
        keyword=keyword,
        alias_of=None,
        action=action,
        message=message,
        message_source=source,
        question=question,
        target_type=None,
        target=None,
        voicemail_note=voicemail,
        notes=notes,
    )
    if target:
        row.update(target)
    KEYWORDS.append(row)


def alias(keyword, of, notes=None):
    KEYWORDS.append(
        dict(
            keyword=keyword,
            alias_of=of,
            action="alias",
            message=None,
            message_source="script",
            question=None,
            target_type=None,
            target=None,
            voicemail_note=False,
            notes=notes,
        )
    )


def aliases(of, *names):
    for n in names:
        alias(n, of)


def br(
    keyword,
    answer,
    action,
    message=None,
    source="script",
    target=None,
    goto=None,
    voicemail=False,
    notes=None,
):
    row = dict(
        keyword=keyword,
        answer=answer,
        action=action,
        message=message,
        message_source=source,
        target_type=None,
        target=None,
        goto_keyword=goto,
        voicemail_note=voicemail,
        notes=notes,
    )
    if target:
        row.update(target)
    BRANCHES.append(row)


# ---------------------------------------------------------------- simple transfers
kw(
    "Accounts Payable",
    "transfer",
    target=ext(187),
    voicemail=True,
    notes="Vendor calling about a bill/invoice issued to MVCAP or a check issued by MVCAP -> Caseam Pleasant",
)
kw(
    "Attorney",
    "transfer",
    target=ext(157),
    voicemail=True,
    notes="Attorney or legal representative",
)
aliases("Attorney", "Lawyer", "Legal Matter")
kw(
    "Elected Official",
    "transfer",
    target=ext(157),
    voicemail=True,
    notes="Local, state, or federal elected officials",
)
kw(
    "Emergency Responders",
    "transfer",
    target=ext(157),
    voicemail=True,
    notes="Police, law enforcement, emergency responders",
)
aliases("Emergency Responders", "Law Enforcement", "Police")
kw("Leadership Team", "transfer", target=ext(157), voicemail=True)
kw("Finance", "transfer", target=ext(157), notes="CFO or a financial request")
alias("Fiscal", "Finance")
kw(
    "Clothing Bank",
    "transfer",
    target=ext(601),
    notes="Darke County Clothing Bank is closed (status update 9/1/2026)",
)
kw("Housing and Financial Counseling", "transfer", target=ext(172))
aliases(
    "Housing and Financial Counseling",
    "Credit Counseling",
    "Down Payment Assistance",
    "Financial Counseling",
    "Generational Wealth",
    "Housing Counseling",
    "Mortgage Counseling",
)
kw("Furnace", "transfer", target=ext(226), notes="Weatherization and Housing Services")
alias("Refrigerator Requests", "Furnace")
kw(
    "Donnellan Shelter",
    "transfer",
    target=phone("937-376-3111"),
    notes="Rings all case managers at the shelter",
)
alias("Harding Place", "Donnellan Shelter")
kw(
    "Domestic Violence",
    "transfer",
    target=phone("937-456-6891"),
    notes="SAFETY-CRITICAL. Domestic Violence Services hotline",
)
kw(
    "Monitoring",
    "transfer",
    target=ext(171),
    notes="Funder/grantmaker about an upcoming monitoring visit -> Kevin Reeves",
)

# ---------------------------------------------------------------- say, then transfer
kw(
    "Weatherization",
    "say_transfer",
    "Please allow me to transfer you to the Weatherization and Housing Services Team.",
    target=ext(226),
)
aliases(
    "Weatherization",
    "Electric Partnership Program",
    "EPP",
    "Energy Audit",
    "Home Repair",
    "Lead Abatement",
    "Lead Hazard",
    "Subcontractors",
)
kw("Darke County", "say_transfer", COUNTY_PAGE.format(county="Darke"), target=ext(601))
kw(
    "Greene County",
    "say_transfer",
    COUNTY_PAGE.format(county="Greene"),
    target=ext(601),
    notes="CONFIRM WITH CLIENT: script says x601, which is a Darke County extension",
)
kw(
    "Preble County",
    "say_transfer",
    COUNTY_PAGE.format(county="Preble"),
    target=ext(501),
)
kw(
    "Darke County MHA",
    "say_transfer",
    "MVCAP administers the MHA program in Darke County through a management agreement with "
    "the Darke County MHA Board of Commissioners.",
    target=ext(601),
)
kw(
    "Preble MHA",
    "say_transfer",
    "MVCAP administers the MHA program in Preble County through a management agreement with "
    "the Preble MHA Board of Commissioners.",
    target=ext(501),
)

# ---------------------------------------------------------------- say, then end
kw(
    "AES",
    "refer",
    "For that request, please call AES directly at 800-433-8500.",
    source="drafted",
    notes="Script: refer caller directly to AES",
)
kw(
    "National Fuel",
    "refer",
    "For that request, please call National Fuel directly at 800-838-0933.",
    source="drafted",
    notes="Script: refer caller directly to National Fuel",
)
alias("CenterPoint Energy", "National Fuel")
kw(
    "Appeals",
    "say_end",
    "Each MVCAP program has unique appeals processes for denied applications. Please visit our "
    f"website at {SITE} to learn these processes and timelines for each of our programs. If you "
    "need to speak with someone, please email appeals at mvcap dot com.",
    notes="Script says to give appeals@mvcap.com only if they insist. Internal escalation "
    "contact is never shared or transferred to.",
)
kw(
    "Board of Trustees",
    "say_end",
    f"MVCAP's Board of Trustees information is listed on our website at {SITE}. Click About Us, "
    "then click Board of Trustees. You can mail correspondence to Miami Valley Community Action "
    "Partnership, attention Board of Trustees, 719 South Main Street, Dayton, Ohio 45402.",
)
kw(
    "Camden Commons",
    "refer",
    OBERER.format(number="937-456-3241"),
    source="drafted",
    notes="Script: managed by Oberer Property Management; direct caller to dial 937-456-3241",
)
alias("Eagles Nest", "Camden Commons")
kw("Fox Run", "refer", OBERER.format(number="937-316-8025"), source="drafted")
alias(
    "Willow Place",
    "Fox Run",
    notes="Script words this as 'direct external line is 937-316-8025'",
)
kw(
    "Employment Inquiries",
    "say_end",
    f"MVCAP's current job openings are posted on our website, {SITE}. Click Support Us, then "
    "Careers, then Click Here for Available Job Openings. Applications are accepted through our "
    "online portal.",
    notes="Internal escalation contact (never shared, never transferred to) is in the script",
)
alias("Jobs", "Employment Inquiries")
kw(
    "Human Resources",
    "say_end",
    "Please email your request to H R at mvcap dot com.",
    source="drafted",
    notes="Script: unless they ask for an HR team member by name, ask them to email HR@mvcap.com. "
    "Name requests go through the directory.",
)
kw(
    "News",
    "say_end",
    "Please email your request to news at mvcap dot com.",
    source="drafted",
    notes="Reporter, journalist, or news outlet",
)
aliases("News", "Press", "Quote")
kw(
    "Workforce Development",
    "say_end",
    f"MVCAP is not offering workforce development programs at this time. Please call {HELPLINK_211} "
    "for additional resources.",
    source="drafted",
    notes="Script: refer all callers to United Way HelpLink 211",
)
kw(
    "Micro Enterprise Program",
    "followup",
    f"MVCAP no longer offers this program. Please call {HELPLINK_211} for additional resources.",
    notes="Script: then ask the caller additional questions",
)
kw(
    "Driver's License Reinstatement",
    "followup",
    "MVCAP's Drivers License Reinstatement program is currently paused. Please visit our website "
    "for additional information.",
    notes="Script: then ask the caller additional questions",
)
alias("Legal Clinic", "Driver's License Reinstatement")

# ---------------------------------------------------------------- general information
kw(
    "Application",
    "followup",
    GENERIC_PROGRAM_INFO,
    notes="Script: then ask additional questions and match other keywords",
)
aliases("Application", "Documentation", "Eligibility")
kw(
    "Community Services Block Grant",
    "followup",
    "Could you tell me a little more about what you're looking for?",
    source="drafted",
    notes="Script: ask additional questions and match other keywords",
)
alias("CSBG", "Community Services Block Grant")
kw(
    "Montgomery County",
    "followup",
    "Could you tell me a little more about what you need help with?",
    source="drafted",
    notes="Script: ask about the nature of the request and match other keywords",
)

# ---------------------------------------------------------------- questions with branches
kw(
    "Grants",
    "ask",
    question="Are you a funder or grantmaker calling about a grant you've given MVCAP, or are you "
    "asking about grants MVCAP offers?",
    source="drafted",
    notes="Script: a client asking if we offer grants -> ask more questions; a funder/grantmaker "
    "about a grant given to MVCAP -> Kevin Reeves x171",
)
br("Grants", "funder", "transfer", target=ext(171))
br(
    "Grants",
    "seeking_help",
    "followup",
    "Could you tell me more about what you need help with?",
    source="drafted",
)

kw(
    "Affordable Housing",
    "ask",
    question="MVCAP offers affordable housing in Darke and Preble Counties. Which of the following "
    "departments would you like me to transfer you to: Darke County MHA, Preble MHA, "
    "Camden Commons, Eagles Nest, Fox Run, or Willow Place?",
    notes="Question wording is the script's; the department list is added so the caller hears the options",
)
alias("Low Income Housing", "Affordable Housing")
for dept in (
    "Darke County MHA",
    "Preble MHA",
    "Camden Commons",
    "Eagles Nest",
    "Fox Run",
    "Willow Place",
):
    br("Affordable Housing", dept, "goto", goto=dept)

kw(
    "Metropolitan Housing Authority",
    "ask",
    question="MVCAP administers the MHA programs in Darke and Preble Counties through management "
    "agreements with those MHA Boards of Commissioners. Which county are you calling about?",
    notes="Question is the script's statement plus a county question (drafted)",
    source="drafted",
)
aliases(
    "Metropolitan Housing Authority",
    "MHA",
    "Housing Choice Voucher",
    "Section 8 Voucher",
    "VASH Voucher",
    "Veteran Housing",
)
br("Metropolitan Housing Authority", "Darke", "goto", goto="Darke County MHA")
br("Metropolitan Housing Authority", "Preble", "goto", goto="Preble MHA")
br(
    "Metropolitan Housing Authority",
    "other",
    "say_end",
    f"MVCAP administers the MHA programs in Darke and Preble Counties only. Please visit our website "
    f"at {SITE}, or call {HELPLINK_211}.",
    source="drafted",
)

COUNTY = "Which county do you live in?"

kw("Food", "ask", question=COUNTY, notes="Script: ask what county they live in")
alias("Food Pantry", "Food")
for c in ("Montgomery", "Greene"):
    br(
        "Food",
        c,
        "refer",
        f"MVCAP does not provide food assistance in {c} County. Please call {HELPLINK_211}.",
        source="drafted",
    )
br("Food", "Darke", "transfer", target=ext(601))
br("Food", "Preble", "transfer", target=ext(501))
br(
    "Food",
    "other",
    "refer",
    f"MVCAP provides food assistance in Darke and Preble Counties. Please call {HELPLINK_211}.",
    source="drafted",
    notes="County not covered by the script; drafted referral to 211",
)

kw("Clothing Assistance", "ask", question=COUNTY)
br("Clothing Assistance", "Darke", "transfer", target=ext(601))
for c in ("Montgomery", "Greene", "Preble", "other"):
    br(
        "Clothing Assistance",
        c,
        "refer",
        f"Please call {HELPLINK_211}.",
        source="drafted",
    )

kw("Transportation", "ask", question=COUNTY)
br("Transportation", "Preble", "transfer", target=ext(501))
for c in ("Montgomery", "Darke", "Greene", "other"):
    br(
        "Transportation",
        c,
        "refer",
        "MVCAP provides transportation services only for Preble County residents. "
        f"Please call {HELPLINK_211}.",
        source="drafted",
    )

kw(
    "Homeless",
    "ask",
    question=COUNTY,
    notes="SAFETY-CRITICAL. Script: ask what county they live in",
)
aliases(
    "Homeless",
    "Emergency Shelter",
    "Emergency Housing",
    "Transitional Shelter",
    "Transitional Housing",
)
br(
    "Homeless",
    "Montgomery",
    "refer",
    "MVCAP does not offer emergency housing in Montgomery County. Men can call Homefull at "
    "937-293-1945. Women and families can call St. Vincent de Paul at 937-222-5555.",
    source="drafted",
    notes="Script splits men -> Homefull, women/families -> St. Vincent de Paul",
)
br("Homeless", "Greene", "transfer", target=phone("937-376-3111"))
br(
    "Homeless",
    "Darke",
    "transfer",
    target=phone("937-456-6891"),
    notes="Script: transfer to the Domestic Violence Services hotline",
)
br(
    "Homeless",
    "Preble",
    "refer",
    "Please call Home is the Foundation at 937-472-0500.",
    source="drafted",
)
br(
    "Homeless",
    "other",
    "refer",
    f"Please call {HELPLINK_211}.",
    source="drafted",
    notes="County not covered by the script",
)

kw(
    "Prevention, Retention and Contingency",
    "ask",
    question=COUNTY,
    notes="Script: ask what county they live in",
)
aliases(
    "Prevention, Retention and Contingency",
    "PRC",
    "Car Repairs",
    "Property Taxes",
    "Student Enrollment Incentive",
)
br(
    "Prevention, Retention and Contingency",
    "Montgomery",
    "say_end",
    "MVCAP offers the PRC program on behalf of the Montgomery County Department of Job and Family "
    f"Services. {PRC_SITE}",
)
for c, num in (
    ("Darke", "937-548-4132"),
    ("Greene", "937-562-6000"),
    ("Preble", "937-456-6205"),
):
    br(
        "Prevention, Retention and Contingency",
        c,
        "refer",
        f"Please call your local Job and Family Services office at {num}.",
        source="drafted",
    )
br(
    "Prevention, Retention and Contingency",
    "other",
    "refer",
    f"Please call {HELPLINK_211}.",
    source="drafted",
    notes="Script: for counties not listed, refer to HelpLink 211",
)

for name, what in (("Rental Assistance", "rent"), ("Mortgage Assistance", "mortgage")):
    kw(
        name,
        "ask",
        question=COUNTY,
        notes="CONFIRM WITH CLIENT: script only defines Montgomery County. Other counties use the "
        "PRC county referrals (drafted).",
    )
    br(
        name,
        "Montgomery",
        "say_end",
        f"MVCAP can help with {what} payments in limited situations through the PRC Program. {PRC_SITE}",
    )
    for c, num in (
        ("Darke", "937-548-4132"),
        ("Greene", "937-562-6000"),
        ("Preble", "937-456-6205"),
    ):
        br(
            name,
            c,
            "refer",
            f"Please call your local Job and Family Services office at {num}.",
            source="drafted",
        )
    br(name, "other", "refer", f"Please call {HELPLINK_211}.", source="drafted")
alias("Eviction", "Rental Assistance")

kw(
    "Utility Assistance",
    "ask",
    question="Is your gas or electric service currently disconnected, or have you received a "
    "disconnection notice?",
    notes="PIPP uses these prompts; appointments are NOT required for PIPP",
)
aliases(
    "Utility Assistance",
    "Disconnection",
    "HEAP",
    "Home Energy Assistance Program",
    "LIHEAP",
    "PIPP",
    "Percentage of Income Payment Plan",
)
br(
    "Utility Assistance",
    "yes",
    "say_transfer",
    "If you haven't already submitted an application, please apply on our website at "
    f"{SITE}, click Programs, then click Utility Assistance, then click Apply Online. I'll "
    "transfer you to a member of our utility assistance team. If they are unable to answer, "
    "leave a voicemail with your name, phone number, address, and date of disconnection.",
    target=ext(821),
    notes="x821 is not in the directory; confirm with client",
)
br(
    "Utility Assistance",
    "no",
    "say_transfer",
    "We encourage you to submit an online application through our website at "
    f"{SITE}, click Programs, then click Utility Assistance, then click Apply Online.",
    target=ext(102),
)

kw(
    "Summer Crisis",
    "ask",
    question="Have you submitted an application for utility assistance since July 1, 2026?",
    notes="Goal: tell them an appointment is required. Appointments for the next three weeks are "
    "released every Friday at 4:30 p.m.",
)
aliases("Summer Crisis", "Air Conditioners", "Central Air", "Fan")
br(
    "Summer Crisis",
    "yes",
    "say_transfer",
    f"Thank you. An appointment is required for this program. {SCHEDULE_STEPS}",
    target=phone("937-514-4777"),
)
br(
    "Summer Crisis",
    "no",
    "say_transfer",
    f"We encourage you to submit an online application through our website at {SITE}, click "
    "Programs, then click Utility Assistance, then click Apply Online. An appointment is required "
    f"for this program. {SCHEDULE_STEPS}",
    target=phone("937-514-4777"),
)

kw(
    "Winter Crisis",
    "say_end",
    f"Please visit our website at {SITE} for more information.",
    source="drafted",
    notes="Script text ('will begin accepting applications Nov 1') is outdated. The current "
    "status update is spoken first. CONFIRM WITH CLIENT.",
)

# ---------------------------------------------------------------- status updates
STATUS_UPDATES = [
    dict(
        update_date="2026-10-29",
        applies_to=None,
        active=False,
        text="The Darke County Emergency Shelter Program and the Darke County Domestic Violence "
        "Services Program reopen on November 1, 2026.",
        notes="Reopening date has passed; inactive. Confirm it is no longer needed.",
    ),
    dict(
        update_date="2026-10-29",
        applies_to=["Winter Crisis"],
        active=True,
        text="The 2026-2027 Winter Crisis program is accepting applications from November 1, 2026, "
        "through March 31, 2027. An appointment is required. Appointments can be scheduled "
        f"online through {SITE} or by calling 937-514-4777.",
        notes="Spoken before the Winter Crisis message",
    ),
    dict(
        update_date="2026-09-01",
        applies_to=["Clothing Bank", "Clothing Assistance"],
        active=True,
        text="The Clothing Bank at the Darke County location is closed until further notice due to "
        "required maintenance.",
        notes="Spoken before the clothing routes. CONFIRM whether callers should still be transferred.",
    ),
    dict(
        update_date="2026-07-01",
        applies_to=None,
        active=True,
        text="Utility Assistance: the 2026-2027 Home Energy Assistance Program (HEAP) application is "
        f"open. Customers are encouraged to submit applications online through {SITE}.",
        notes="General background for the model; not spoken on its own",
    ),
]

# ---------------------------------------------------------------- settings
SETTINGS = {
    "greeting": (
        "Thank you for calling Miami Valley Community Action Partnership. How may I help you?",
        "Script greeting without the agent-name blank. CONFIRM final wording with client.",
    ),
    "voicemail_note": (
        "If they are unable to take your call, please leave a detailed voice message.",
        "Spoken before transfers that carry the voicemail note",
    ),
    "default_transfer_message": (
        "One moment while I transfer you.",
        "Spoken before a transfer that has no scripted message",
    ),
    "fallback_message": (
        "I'm sorry, I wasn't able to help with that request. Let me connect you with "
        "a team member.",
        "PENDING CLIENT: spoken when escalating to a human",
    ),
    "transfer_failed_message": (
        "I'm sorry, I wasn't able to complete that transfer. Please visit "
        f"{SITE}, or call {HELPLINK_211}.",
        "PENDING CLIENT: spoken when a transfer fails",
    ),
    "human_fallback_number": (
        None,
        "PENDING CLIENT: E.164 number that rings a human, e.g. +19375551234",
    ),
    "pbx_transfer_template": (
        None,
        "PENDING M0 TEST: how an extension is dialed, e.g. "
        "'tel:+19375551234;ext={ext}' or 'sip:{ext}@pbx.example.com'",
    ),
    "office_hours_statement": (
        "Hours of operation are Monday through Friday, 8:00 a.m. to 4:30 p.m., closed for lunch from "
        "12:00 p.m. to 1:00 p.m. Offices are closed for holidays. Visiting hours vary by location.",
        "Script wording, spoken by the model only when a caller asks about hours",
    ),
    "goodbye_message": (
        "Thank you for calling Miami Valley Community Action Partnership. Goodbye.",
        "Drafted by us (the script has none). Spoken when the caller is finished. CONFIRM with client.",
    ),
    "timezone": ("America/New_York", None),
    "office_hours": (
        {
            "days": "Mon-Fri",
            "open": "08:00",
            "close": "16:30",
            "lunch_closed": ["12:00", "13:00"],
        },
        "Closed for holidays. After-hours behavior is PENDING CLIENT.",
    ),
}
