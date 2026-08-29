"""Hyderabad launch catalogue master data — 6 categories, 22 pujas (English canonical).

Pricing model (real-world Hyderabad market):
  default_price  = priest dakshina + travel + personal kit (without family samagri)
  price_max      = ceiling with recommended Samagri Kit + typical premium add-ons
  Every puja has a "Complete Samagri Kit (Recommended)" add-on unless noted.

Telugu lives in catalog_hyderabad_te.py — loaded via bootstrap into puja_*_i18n tables.
"""
from __future__ import annotations

from typing import Any

# Shared content blocks -------------------------------------------------------

_GHMC_TRAVEL = (
    "Priest travel within Hyderabad city limits (GHMC) and setup before muhurtam"
)
_CORE_SAMAGRI = (
    "Core samagri with kit add-on: pasupu, kumkuma, gandham, akshatalu, agarbatti, "
    "karpuram, vattulu, panchapatra-uddharini"
)
_FLOWERS_EXCL = (
    "Fresh flowers, garlands, mango leaves (mamidi toranam) and banana stems — "
    "sourced locally on the day"
)
_NAIVEDYAM_EXCL = (
    "Maha naivedyam and prasadam cooked at home, plus milk, curd, honey and fruits"
)
_DEEPAM_EXCL = (
    "Deepam oil or ghee, family idols and photo frames, and new vastram for kalasham"
)
_DAKSHINA_EXCL = "Priest dakshina beyond the base booking fee (optional extra)"
_SPACE_REQ = (
    "Clean 6x6 ft space with a low peetam or table, floor seating for the priest, "
    "and a power point"
)

SAMAGRI_KIT_ADDON: dict[str, Any] = {
    "name": "Complete Samagri Kit (Recommended)",
    "description": (
        "Purohit brings ritual-specific dravyalu, homa materials where applicable, "
        "and the standard puja kit. Family still arranges fresh flowers, fruits and "
        "naivedyam as listed in exclusions."
    ),
}


def _kit(price: int, order: int = 0) -> dict[str, Any]:
    return {**SAMAGRI_KIT_ADDON, "price": price, "display_order": order}


def _premium(name: str, desc: str, price: int, order: int) -> dict[str, Any]:
    return {
        "name": name,
        "description": desc,
        "price": price,
        "display_order": order,
    }


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "vratams",
        "name": "Vratams",
        "description": "Observances with vow, fasting and katha",
        "display_order": 0,
    },
    {
        "slug": "griha-pravesh-vastu",
        "name": "Griha Pravesh & Vastu",
        "description": "New home entry and site energy correction",
        "display_order": 1,
    },
    {
        "slug": "sanskaras",
        "name": "Sanskaras",
        "description": "Vedic life-milestone ceremonies",
        "display_order": 2,
    },
    {
        "slug": "homams",
        "name": "Homams",
        "description": "Agni-based rituals with mantra ahuti",
        "display_order": 3,
    },
    {
        "slug": "daily-special",
        "name": "Daily & Special",
        "description": "Shorter pujas for daily and occasional needs",
        "display_order": 4,
    },
    {
        "slug": "pitru-karyam",
        "name": "Pitru Karyam",
        "description": "Ancestral rites — Taddinam, Masikam, Abdikam and Tarpanam",
        "display_order": 5,
    },
]

SEED_CATEGORY_SLUGS: frozenset[str] = frozenset(c["slug"] for c in CATEGORIES)

# ---------------------------------------------------------------------------
# Pujas
# ---------------------------------------------------------------------------

PUJAS: list[dict[str, Any]] = [
    # --- Vratams -------------------------------------------------------------
    {
        "id": "a1000001-0000-4000-8000-000000000001",
        "slug": "satyanarayana-vratam",
        "category_slug": "vratams",
        "name": "Satyanarayana Vratam",
        "tagline": "Purnima vratam for prosperity and vow fulfilment",
        "description": (
            "Performed on Purnima or after a vow, housewarming or wedding to invoke "
            "Lord Vishnu as Satyanarayana. The five-chapter katha with sthalipakam "
            "prasadam is the heart of the ritual, sought for family harmony and "
            "steady prosperity."
        ),
        "default_price": 1800,
        "price_max": 6500,
        "duration_minutes": 120,
        "is_muhurat_bound": True,
        "display_order": 0,
        "inclusions": [
            "1 senior Vedic purohit trained in the full five-adhyaya katha",
            _GHMC_TRAVEL,
            "Complete mandapam setup: kalasham, toranam stringing, deity arrangement and aarti plate",
            _CORE_SAMAGRI,
            "Sthalipaka dravyalu, navadhanyalu and printed katha booklet for the family",
        ],
        "exclusions": [_FLOWERS_EXCL, _NAIVEDYAM_EXCL, _DEEPAM_EXCL, _DAKSHINA_EXCL],
        "requirements": [
            _SPACE_REQ,
            "Sapatha bhakshyam (rava kesari with banana) ingredients kept ready for prasadam",
        ],
        "faqs": [
            {
                "q": "Can this be done on a day other than Purnima?",
                "a": (
                    "Yes. Purnima is preferred, but the vratam is also performed after a "
                    "vow is fulfilled, or following a housewarming or wedding, on any "
                    "suitable day chosen by the purohit."
                ),
            },
            {
                "q": "With or without samagri — what should I book?",
                "a": (
                    "Base booking covers the purohit and setup. Select the Complete Samagri "
                    "Kit add-on (recommended) so the purohit brings dravyalu and homa "
                    "materials. You still arrange fresh flowers, fruits and naivedyam locally."
                ),
            },
        ],
        "addons": [
            _kit(700),
            _premium(
                "Veda Parayanam (1 extra priest)",
                "Additional purohit for Vishnu Sahasranama parayanam alongside the vratam",
                2500,
                1,
            ),
            _premium(
                "Floral Mandapam Decoration",
                "Fresh flower backdrop, toranam and kalasham decoration",
                3500,
                2,
            ),
        ],
    },
    {
        "id": "a1000002-0000-4000-8000-000000000002",
        "slug": "varalakshmi-vratam",
        "category_slug": "vratams",
        "name": "Varalakshmi Vratam",
        "tagline": "Sravana masam vratam for family wellbeing",
        "description": (
            "Observed by married women on the Friday before Sravana Purnima, invoking "
            "Goddess Lakshmi through kalasha sthapana and toranam. Sought for the "
            "longevity of the husband, family health and household abundance."
        ),
        "default_price": 1900,
        "price_max": 4500,
        "duration_minutes": 90,
        "is_muhurat_bound": True,
        "display_order": 1,
        "inclusions": [
            "1 Vedic purohit experienced in Varalakshmi vratam vidhanam",
            _GHMC_TRAVEL,
            "Kalasha sthapana with mukhavarnam arrangement and toranam stringing",
            _CORE_SAMAGRI,
            "Vratam toram threads for participating women and printed vratakatha",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Saree, jewellery and mukhavarnam face for decorating the kalasham",
        ],
        "requirements": [
            _SPACE_REQ,
            "Vratam begins in the morning before noon; household ready by appointed hour",
        ],
        "faqs": [
            {
                "q": "Who is eligible to perform this vratam?",
                "a": (
                    "Traditionally observed by married women, often with female relatives "
                    "and neighbours joining. Families follow their own kula achara, and "
                    "the purohit will guide accordingly."
                ),
            },
            {
                "q": "Is fasting compulsory?",
                "a": (
                    "A light fast until the vratam concludes is customary, but adapted "
                    "for health conditions, pregnancy or age. Inform the purohit beforehand."
                ),
            },
        ],
        "addons": [
            _kit(600),
            _premium(
                "Kalasham Decoration Set",
                "Mukhavarnam, saree draping and jewellery arrangement for the kalasham",
                2200,
                1,
            ),
            _premium(
                "Floral Mandapam Decoration",
                "Fresh flower backdrop and toranam",
                3500,
                2,
            ),
        ],
    },
    {
        "id": "a1000012-0000-4000-8000-00000000000c",
        "slug": "satyanarayana-compact",
        "category_slug": "vratams",
        "name": "Satyanarayana Puja — Compact",
        "tagline": "Shorter one-priest version for apartments and weekdays",
        "description": (
            "A condensed one-hour form of the Satyanarayana Vratam with a single "
            "priest, suited to apartments and weekday schedules. Retains sankalpam, "
            "abbreviated katha and aarti while omitting the extended homam segment."
        ),
        "default_price": 1100,
        "price_max": 2500,
        "duration_minutes": 60,
        "is_muhurat_bound": False,
        "display_order": 2,
        "inclusions": [
            "1 Vedic purohit for the condensed one-hour vidhanam",
            _GHMC_TRAVEL,
            "Compact puja setup with kalasham and aarti plate, suited to apartment spaces",
            _CORE_SAMAGRI,
            "Abbreviated katha reading and printed booklet for the family",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            _DAKSHINA_EXCL,
        ],
        "requirements": [
            "Clean 4x4 ft space with a low peetam; no open flame beyond the deepam",
            "Prasadam prepared at home before the purohit arrives, as the sequence is short",
        ],
        "faqs": [
            {
                "q": "How is this different from the full vratam?",
                "a": (
                    "The compact form uses one priest, an abbreviated katha and no extended "
                    "homam segment, finishing in about an hour. The full vratam covers all "
                    "five adhyayas in detail."
                ),
            },
            {
                "q": "Can I upgrade to the full vratam?",
                "a": (
                    "Yes — select the Upgrade to Full Vratam add-on, or book the full "
                    "Satyanarayana Vratam listing if you have more time and guests."
                ),
            },
        ],
        "addons": [
            _kit(400),
            _premium(
                "Upgrade to Full Vratam",
                "Extend to the complete five-adhyaya vratam with additional time",
                900,
                1,
            ),
        ],
    },
    # --- Griha Pravesh & Vastu -----------------------------------------------
    {
        "id": "a1000003-0000-4000-8000-000000000003",
        "slug": "griha-pravesham",
        "category_slug": "griha-pravesh-vastu",
        "name": "Griha Pravesham",
        "tagline": "Auspicious first entry into a new home",
        "description": (
            "The complete first-entry ceremony for a new home — Ganapati puja, "
            "punyahavachanam, navagraha, Vastu homam and the milk-boiling ritual at "
            "the threshold. Performed at a strict muhurtam to establish protective "
            "and auspicious energy in the dwelling."
        ),
        "default_price": 4200,
        "price_max": 12000,
        "duration_minutes": 180,
        "is_muhurat_bound": True,
        "display_order": 0,
        "inclusions": [
            "2 Vedic purohits for the full sequence including Vastu homam",
            _GHMC_TRAVEL,
            "Homa gundam, complete mandapam setup, navagraha arrangement and threshold ritual",
            _CORE_SAMAGRI,
            "Homa dravyalu, samidhalu, navadhanyalu, ghee for ahuti and punyahavachanam materials",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "New milk vessel, rice and jaggery for paalu ponginchadam at the threshold",
        ],
        "requirements": [
            "Balcony, terrace or ventilated area for agni; smoke detector isolation and society NOC if apartment",
            "Security gate entry pass and lift access for early-morning muhurtam slots",
        ],
        "faqs": [
            {
                "q": "Can Griha Pravesham be done in an apartment with a fire alarm?",
                "a": (
                    "Yes, but the homam must be on a balcony or terrace with ventilation, "
                    "and the detector in that zone isolated with society knowledge. Tell us "
                    "at booking so the right setup is planned."
                ),
            },
            {
                "q": "How is the muhurtam decided?",
                "a": (
                    "Based on the family's nakshatram and the panchangam for that date, "
                    "avoiding shunya masam and inauspicious periods. Share birth details "
                    "at booking and the purohit will confirm the window."
                ),
            },
        ],
        "addons": [
            _kit(1800),
            _premium(
                "Live Sannayi Melam (Nadaswaram)",
                "Two-piece nadaswaram and dolu ensemble for muhurtam and threshold entry",
                9000,
                1,
            ),
            _premium(
                "Veda Parayanam (2 extra priests)",
                "Extended Vedic recitation through the homam by two additional purohits",
                5000,
                2,
            ),
            _premium(
                "Floral Mandapam Decoration",
                "Full flower mandapam, entrance toranam and rangoli setup",
                8500,
                3,
            ),
        ],
    },
    {
        "id": "a1000004-0000-4000-8000-000000000004",
        "slug": "vastu-shanti",
        "category_slug": "griha-pravesh-vastu",
        "name": "Vastu Shanti",
        "tagline": "Correction of directional and structural dosha",
        "description": (
            "Performed to pacify Vastu Purusha when a home or workplace shows "
            "directional defects, or before renovation and re-occupation. Combines "
            "Vastu homam with dik-shanti to reduce friction, health issues and "
            "financial blockage attributed to the space."
        ),
        "default_price": 3300,
        "price_max": 8000,
        "duration_minutes": 150,
        "is_muhurat_bound": True,
        "display_order": 1,
        "inclusions": [
            "2 Vedic purohits trained in Vastu homam and dik-shanti procedure",
            _GHMC_TRAVEL,
            "Homa gundam, Vastu Purusha mandala setup and directional kalasha placement",
            _CORE_SAMAGRI,
            "Homa dravyalu, samidhalu, navadhanyalu and Vastu shanti japam as prescribed",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Structural renovation or standalone Vastu consultancy report",
        ],
        "requirements": [
            "Balcony, terrace or ventilated area for agni; society NOC if gated apartment",
            "Access to all rooms and corners of the property for directional circumambulation",
        ],
        "faqs": [
            {
                "q": "Is this the same as Griha Pravesham?",
                "a": (
                    "No. Griha Pravesham is first entry into a new home. Vastu Shanti is "
                    "a corrective ritual for an existing property showing directional defects."
                ),
            },
            {
                "q": "Do you provide a Vastu consultation report?",
                "a": (
                    "The ritual itself does not include a structural survey. Select the "
                    "Written Vastu Consultation add-on if you need directional recommendations."
                ),
            },
        ],
        "addons": [
            _kit(1200),
            _premium(
                "Veda Parayanam (1 extra priest)",
                "Additional purohit for extended Vastu sukta recitation",
                2500,
                1,
            ),
            _premium(
                "Written Vastu Consultation",
                "Site walkthrough with written directional recommendations before the ritual",
                3000,
                2,
            ),
        ],
    },
    # --- Sanskaras -------------------------------------------------------------
    {
        "id": "a1000005-0000-4000-8000-000000000005",
        "slug": "namakaranam",
        "category_slug": "sanskaras",
        "name": "Namakaranam — Barasala",
        "tagline": "Naming ceremony on the 11th or 21st day",
        "description": (
            "The Vedic naming samskara, traditionally on the 11th or 21st day after "
            "birth. The chosen name is whispered in the child's ear after "
            "punyahavachanam and jatakarma balance, with nakshatra-based syllable "
            "guidance from the purohit."
        ),
        "default_price": 1900,
        "price_max": 4500,
        "duration_minutes": 90,
        "is_muhurat_bound": True,
        "display_order": 0,
        "inclusions": [
            "1 Vedic purohit for punyahavachanam and the naming sequence",
            _GHMC_TRAVEL,
            "Puja setup with kalasham, cradle-side arrangement and aarti plate",
            _CORE_SAMAGRI,
            "Nakshatra-based syllable guidance and written name suggestions before the date",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Cradle, new clothes for the infant, and gold or silver items for the ceremony",
        ],
        "requirements": [
            _SPACE_REQ,
            "Infant's date, time and place of birth shared at least 3 days in advance",
        ],
        "faqs": [
            {
                "q": "Must it be exactly the 11th or 21st day?",
                "a": (
                    "Those are traditional days, but families often perform it later based "
                    "on the mother's and child's health and an available muhurtam."
                ),
            },
            {
                "q": "Can we use a name we have already chosen?",
                "a": (
                    "Yes. The purohit will incorporate your chosen name and can also give "
                    "the nakshatra syllable name separately, as many families keep both."
                ),
            },
        ],
        "addons": [
            _kit(600),
            _premium(
                "Floral Cradle Decoration",
                "Fresh flower decoration for the cradle and puja area",
                2800,
                1,
            ),
            _premium(
                "Nakshatra Report (written)",
                "Written birth-star chart with name syllable options, delivered before the date",
                1200,
                2,
            ),
        ],
    },
    {
        "id": "a1000006-0000-4000-8000-000000000006",
        "slug": "annaprashana",
        "category_slug": "sanskaras",
        "name": "Annaprashana",
        "tagline": "First solid food ceremony for the infant",
        "description": (
            "The samskara marking the infant's first intake of solid food, usually in "
            "the sixth month — even months for boys, odd for girls by tradition. A "
            "brief Ganapati puja and blessing precede the first feeding of payasam by "
            "elders."
        ),
        "default_price": 1600,
        "price_max": 3500,
        "duration_minutes": 60,
        "is_muhurat_bound": True,
        "display_order": 1,
        "inclusions": [
            "1 Vedic purohit for Ganapati puja and feeding sankalpam",
            _GHMC_TRAVEL,
            "Compact puja setup with kalasham and aarti arrangement",
            _CORE_SAMAGRI,
            "Guidance on the traditional item-selection ritual placed before the child",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Silver feeding bowl or gifts for the child",
        ],
        "requirements": [
            _SPACE_REQ,
            "Payasam or annam prepared at home for the first feeding moment",
        ],
        "faqs": [
            {
                "q": "Which month is correct for annaprashana?",
                "a": (
                    "Traditionally the sixth month — even for boys, odd for girls. The "
                    "purohit will confirm based on your family achara and an auspicious day."
                ),
            },
            {
                "q": "With or without samagri?",
                "a": (
                    "Base covers the purohit. Add the Samagri Kit for dravyalu; you still "
                    "prepare payasam and arrange flowers locally."
                ),
            },
        ],
        "addons": [
            _kit(500),
            _premium(
                "Floral Decoration",
                "Fresh flower decoration for the puja area and child's seat",
                2200,
                1,
            ),
            _premium(
                "Silver Spoon & Bowl Set",
                "Traditional silver feeding set for the first annam, kept by the family",
                3500,
                2,
            ),
        ],
    },
    {
        "id": "a1000016-0000-4000-8000-000000000010",
        "slug": "seemantham",
        "category_slug": "sanskaras",
        "name": "Seemantham",
        "tagline": "Baby shower blessing for mother and child",
        "description": (
            "Traditional Telugu seemantham (valaikaappu) with punyahavachanam, "
            "Lakshmi invocation and blessings for the expectant mother and unborn "
            "child. Usually performed in the later months of pregnancy on an "
            "auspicious day chosen by the purohit."
        ),
        "default_price": 1900,
        "price_max": 4500,
        "duration_minutes": 90,
        "is_muhurat_bound": True,
        "display_order": 2,
        "inclusions": [
            "1 Vedic purohit experienced in Telugu seemantham vidhanam",
            _GHMC_TRAVEL,
            "Kalasham setup, bangles and fruit arrangement guidance for the mother",
            _CORE_SAMAGRI,
            "Lakshmi katha segment, aarti and blessings for mother and child",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Return gifts, bangle sets, saree and catering for guests",
        ],
        "requirements": [
            _SPACE_REQ,
            "Mother's comfort seating; share expected month of delivery at booking",
        ],
        "faqs": [
            {
                "q": "Which month of pregnancy is seemantham performed?",
                "a": (
                    "Most Telugu families perform it in the seventh or eighth month, on an "
                    "auspicious day. The purohit will advise based on health and panchangam."
                ),
            },
            {
                "q": "Is this the same as valaikaappu?",
                "a": (
                    "They are the same family celebration — seemantham is the Vedic "
                    "ceremony; valaikaappu refers to the bangle and blessing customs "
                    "around it. We perform the full religious portion."
                ),
            },
        ],
        "addons": [
            _kit(600),
            _premium(
                "Floral Mandapam Decoration",
                "Fresh flower backdrop and toranam for the mother's seat",
                3500,
                1,
            ),
        ],
    },
    {
        "id": "a1000007-0000-4000-8000-000000000007",
        "slug": "upanayanam",
        "category_slug": "sanskaras",
        "name": "Upanayanam",
        "tagline": "Sacred thread and Gayatri initiation",
        "description": (
            "The thread ceremony initiating a boy into Vedic study, with Gayatri "
            "upadesham given by the father or acharya. Includes yajnopaveeta dharana, "
            "Brahmopadesham and the first bhiksha, marking entry into brahmacharya."
        ),
        "default_price": 6000,
        "price_max": 18000,
        "duration_minutes": 180,
        "is_muhurat_bound": True,
        "display_order": 3,
        "inclusions": [
            "2 Vedic purohits for the full upanayanam sequence",
            _GHMC_TRAVEL,
            "Homa gundam, mandapam setup and yajnopaveeta dharana arrangement",
            _CORE_SAMAGRI,
            "Yajnopaveetam, munja grass, homam dravyalu and Gayatri upadesham",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "New dhoti, pancha, ceremonial attire and community feast (annadanam)",
        ],
        "requirements": [
            "Ventilated area for homam; large seating for family and the vatu (boy)",
            "Boy's birth details shared at booking for muhurtam calculation",
        ],
        "faqs": [
            {
                "q": "How many priests are included?",
                "a": (
                    "Base includes 2 purohits for the standard vidhanam. Add Veda Parayanam "
                    "or Sannayi Melam for larger gatherings."
                ),
            },
            {
                "q": "What age is upanayanam traditionally performed?",
                "a": (
                    "Classically between 7 and 12 years by Vedic reckoning. Families today "
                    "often perform it later; the purohit will confirm eligibility and date."
                ),
            },
        ],
        "addons": [
            _kit(2000),
            _premium(
                "Live Sannayi Melam (Nadaswaram)",
                "Two-piece nadaswaram and dolu ensemble through the samskara",
                9000,
                1,
            ),
            _premium(
                "Veda Parayanam (2 extra priests)",
                "Extended recitation and support through the homam sequence",
                5000,
                2,
            ),
            _premium(
                "Floral Mandapam Decoration",
                "Full flower mandapam and entrance toranam",
                8500,
                3,
            ),
        ],
    },
    {
        "id": "a1000015-0000-4000-8000-00000000000f",
        "slug": "shashti-poorthi",
        "category_slug": "sanskaras",
        "name": "Shashti Poorthi",
        "tagline": "60th year with Ugra Ratha Shanti",
        "description": (
            "The 60th-year milestone performed with Ugra Ratha Shanti, marking one full "
            "cycle of the Telugu samvatsara. Includes Ayushya and Mrityunjaya homam and "
            "the symbolic re-marriage of the couple, requiring both spouses to be living."
        ),
        "default_price": 12000,
        "price_max": 30000,
        "duration_minutes": 240,
        "is_muhurat_bound": True,
        "display_order": 4,
        "inclusions": [
            "3 Vedic purohits for Ugra Ratha Shanti, homam and punar-vivaham sequence",
            _GHMC_TRAVEL,
            "Homa gundam, full mandapam setup, navagraha arrangement and kalasha sthapana",
            _CORE_SAMAGRI,
            "Ayushya and Mrityunjaya homa dravyalu, samidhalu and mangalasutra thread",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "New clothes for the couple, thalambralu rice and gifts for family elders",
        ],
        "requirements": [
            "Both spouses must be living and present — the ritual is not performed otherwise",
            "Large ventilated venue or function hall; four hours of continuous seating",
        ],
        "faqs": [
            {
                "q": "Is this done on the 60th birthday exactly?",
                "a": (
                    "Performed when the person completes 60 years by the Telugu calendar, "
                    "calculated on janma nakshatram rather than the English date."
                ),
            },
            {
                "q": "How is this different from Sathabhishekam?",
                "a": (
                    "Shashti Poorthi marks 60 years. Sathabhishekam marks ~81 years. "
                    "Bhima Ratha Shanti at 70 is a separate milestone with different vidhanam."
                ),
            },
        ],
        "addons": [
            _kit(3000),
            _premium(
                "Live Sannayi Melam (Nadaswaram)",
                "Two-piece nadaswaram and dolu ensemble through the ceremony",
                9000,
                1,
            ),
            _premium(
                "Veda Parayanam (3 extra priests)",
                "Extended Vedic recitation through Ayushya and Mrityunjaya homam",
                7500,
                2,
            ),
            _premium(
                "Floral Mandapam Decoration",
                "Full flower mandapam, stage backdrop and entrance toranam",
                15000,
                3,
            ),
        ],
    },
    # --- Homams ----------------------------------------------------------------
    {
        "id": "a1000009-0000-4000-8000-000000000009",
        "slug": "ganapathi-homam",
        "category_slug": "homams",
        "name": "Ganapathi Homam",
        "tagline": "Obstacle removal before any new beginning",
        "description": (
            "The foundational homam invoking Lord Ganapati to clear obstacles, "
            "performed before new ventures, weddings, or as a standalone remedy. "
            "Modaka and durva ahuti are offered with the Ganapati Atharvashirsha."
        ),
        "default_price": 3000,
        "price_max": 8000,
        "duration_minutes": 90,
        "is_muhurat_bound": False,
        "display_order": 0,
        "inclusions": [
            "1 Vedic purohit trained in Ganapathi homam vidhanam",
            _GHMC_TRAVEL,
            "Homa gundam setup and Ganapati sthapana with aarti plate",
            _CORE_SAMAGRI,
            "Samidhalu, ghee, durva and modaka ahuti materials with poornahuti",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Idol purchase or elaborate mandapam decoration",
        ],
        "requirements": [
            "Balcony, terrace or ventilated area for agni; apartment society NOC if needed",
            "Modakam ingredients at home if you wish fresh naivedyam beyond kit basics",
        ],
        "faqs": [
            {
                "q": "Homam vs puja — what is included?",
                "a": (
                    "This is a full homam with agni and ahuti, not a simple Ganapati puja. "
                    "Select the Samagri Kit for samidhalu and ghee; allow 90 minutes."
                ),
            },
            {
                "q": "When should Ganapathi Homam be performed?",
                "a": (
                    "Before weddings, griha pravesham, new business openings, travel, or "
                    "any major sankalpam. Many families also perform it on Sankatahara Chaturthi."
                ),
            },
        ],
        "addons": [
            _kit(1000),
            _premium(
                "Extended Ahuti (1008 count)",
                "Upgrade from standard to 1008 ahuti with additional priest and time",
                4500,
                1,
            ),
            _premium(
                "Floral Mandapam Decoration",
                "Fresh flower backdrop and toranam",
                3500,
                2,
            ),
        ],
    },
    {
        "id": "a1000008-0000-4000-8000-000000000008",
        "slug": "navagraha-homam",
        "category_slug": "homams",
        "name": "Navagraha Homam",
        "tagline": "Pacification of the nine planetary influences",
        "description": (
            "Performed to reduce affliction from adverse planetary periods such as Sade "
            "Sati, Rahu-Ketu dasha or a difficult transit. Each graha receives its "
            "prescribed samidha and ahuti in sequence, followed by graha shanti japam."
        ),
        "default_price": 3800,
        "price_max": 9000,
        "duration_minutes": 120,
        "is_muhurat_bound": False,
        "display_order": 1,
        "inclusions": [
            "1 Vedic purohit trained in Navagraha homam and graha shanti japam",
            _GHMC_TRAVEL,
            "Homa gundam, navagraha kalasha arrangement and mandapam setup",
            _CORE_SAMAGRI,
            "Graha-specific samidhalu, ghee, navadhanyalu and poornahuti",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Gemstone recommendations or purchases",
        ],
        "requirements": [
            "Ventilated area for homam; share janma details if graha-specific sankalpam needed",
            "Allow 2 hours; graha ahuti sequence cannot be rushed",
        ],
        "faqs": [
            {
                "q": "Do I need my horoscope for this homam?",
                "a": (
                    "Helpful but not mandatory. Share birth details at booking if you want "
                    "graha-specific emphasis; otherwise the purohit performs standard shanti."
                ),
            },
            {
                "q": "Is a muhurtam required?",
                "a": (
                    "Not strictly bound, but the purohit will avoid Rahu kalam and suggest "
                    "a clear window on your chosen date."
                ),
            },
        ],
        "addons": [
            _kit(1200),
            _premium(
                "Veda Parayanam (1 extra priest)",
                "Additional purohit for graha shanti japam",
                2500,
                1,
            ),
            _premium(
                "Navagraha Dana Kit",
                "Nine-colour cloth and prescribed dana items for post-homam dana",
                1800,
                2,
            ),
        ],
    },
    {
        "id": "a1000017-0000-4000-8000-000000000011",
        "slug": "rudrabhishekam",
        "category_slug": "homams",
        "name": "Rudrabhishekam",
        "tagline": "Shaiva abhishekam with Rudri parayanam",
        "description": (
            "Sacred abhishekam to Lord Shiva with Rudri (Sri Rudram) parayanam — "
            "performed on Mondays, Masa Shivaratri, Karthika masam or for health and "
            "obstacle relief. Eka Rudrabhishekam with one priest; extended packages "
            "available for Mrityunjaya homam pairing."
        ),
        "default_price": 4000,
        "price_max": 16000,
        "duration_minutes": 120,
        "is_muhurat_bound": False,
        "display_order": 2,
        "inclusions": [
            "1 Vedic purohit trained in Rudri parayanam and abhishekam vidhanam",
            _GHMC_TRAVEL,
            "Shiva lingam or kalasha setup, panchamrita and abhishekam dravyalu arrangement",
            _CORE_SAMAGRI,
            "Rudri path, archana, aarti and poornahuti where homam segment applies",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Shiva idol or lingam purchase; bilva leaves sourced locally on the day",
        ],
        "requirements": [
            _SPACE_REQ,
            "Family Shiva photo or lingam clean and placed before the purohit arrives",
        ],
        "faqs": [
            {
                "q": "What is the difference between Eka and Ekadasha Rudrabhishekam?",
                "a": (
                    "Eka Rudrabhishekam is one Rudri recitation (~2 hours). Ekadasha "
                    "involves eleven recitations with multiple priests and higher cost — "
                    "contact ops for a custom quote beyond this listing's max range."
                ),
            },
            {
                "q": "Can Mrityunjaya homam be added?",
                "a": (
                    "Yes — select the Mrityunjaya Homam Add-on for health-related sankalpa. "
                    "This extends duration and requires ventilated space for agni."
                ),
            },
        ],
        "addons": [
            _kit(1000),
            _premium(
                "Mrityunjaya Homam Add-on",
                "Mrityunjaya homam paired with Rudrabhishekam; needs balcony or terrace",
                11000,
                1,
            ),
            _premium(
                "Veda Parayanam (1 extra priest)",
                "Additional purohit for extended Rudri parayanam",
                2500,
                2,
            ),
        ],
    },
    {
        "id": "a1000018-0000-4000-8000-000000000012",
        "slug": "ayushya-homam",
        "category_slug": "homams",
        "name": "Ayushya Homam",
        "tagline": "Longevity and health homam on birthdays",
        "description": (
            "Ayushya homam invoking Ayur Devata for longevity, good health and relief "
            "from illness. Commonly performed on birthdays, after recovery from serious "
            "illness, or as part of milestone shanti ceremonies."
        ),
        "default_price": 4200,
        "price_max": 14000,
        "duration_minutes": 90,
        "is_muhurat_bound": False,
        "display_order": 3,
        "inclusions": [
            "1 Vedic purohit trained in Ayushya homam vidhanam",
            _GHMC_TRAVEL,
            "Homa gundam setup and Ayur Devata sankalpam",
            _CORE_SAMAGRI,
            "Samidhalu, ghee, ayushya dravyalu and poornahuti",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Medical treatment or health consultancy",
        ],
        "requirements": [
            "Ventilated area for homam",
            "Person for whom homam is performed should be present for sankalpam",
        ],
        "faqs": [
            {
                "q": "When is Ayushya Homam performed?",
                "a": (
                    "On janma nakshatram birthdays, after major illness recovery, or alongside "
                    "milestone rites like Shashti Poorthi. Annual performance is common."
                ),
            },
            {
                "q": "Is this the same as Mrityunjaya homam?",
                "a": (
                    "Related but distinct. Ayushya homam focuses on longevity and health "
                    "blessing. Mrityunjaya homam is a stronger remedial homam for serious "
                    "health crises — available as add-on on Rudrabhishekam."
                ),
            },
        ],
        "addons": [
            _kit(1300),
            _premium(
                "Veda Parayanam (1 extra priest)",
                "Additional purohit for extended Ayushya sukta recitation",
                2500,
                1,
            ),
            _premium(
                "Extended Ahuti Package",
                "Additional samidhalu and ghee for extended ahuti sequence",
                3500,
                2,
            ),
        ],
    },
    {
        "id": "a1000010-0000-4000-8000-00000000000a",
        "slug": "lakshmi-kubera-puja",
        "category_slug": "homams",
        "name": "Lakshmi Kubera Puja",
        "tagline": "Wealth flow and financial stability",
        "description": (
            "Joint invocation of Goddess Lakshmi and Kubera, the treasurer of the "
            "devas, for steady income, debt relief and business growth. Commonly "
            "performed on Fridays, Akshaya Tritiya or Dhanteras."
        ),
        "default_price": 2100,
        "price_max": 5500,
        "duration_minutes": 90,
        "is_muhurat_bound": False,
        "display_order": 4,
        "inclusions": [
            "1 Vedic purohit for Lakshmi Kubera puja with japam",
            _GHMC_TRAVEL,
            "Kalasham setup with lotus, coin arrangement and Sri yantra placement guidance",
            _CORE_SAMAGRI,
            "Prosperity mantras, Lakshmi Ashtottara and aarti",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Gold or silver coins, currency notes and account passbooks for blessing",
        ],
        "requirements": [
            _SPACE_REQ,
            "Puja is best performed in the evening on Fridays; confirm slot when booking",
        ],
        "faqs": [
            {
                "q": "Can this be done at a shop or office?",
                "a": (
                    "Yes, commonly performed at business premises. Confirm address type at "
                    "booking so the purohit plans setup for a commercial space."
                ),
            },
            {
                "q": "Is a homam included?",
                "a": (
                    "This is a puja with japam, not a homam. For agni-based Lakshmi Kubera "
                    "Homam, discuss with ops — it needs open space and longer duration."
                ),
            },
        ],
        "addons": [
            _kit(700),
            _premium(
                "Sri Yantra (energised, retained)",
                "Copper Sri Yantra energised during the puja and left with the family",
                2500,
                1,
            ),
            _premium(
                "Veda Parayanam (1 extra priest)",
                "Additional purohit for Lakshmi Sahasranama parayanam",
                2500,
                2,
            ),
        ],
    },
    {
        "id": "a1000013-0000-4000-8000-00000000000d",
        "slug": "sudarshana-homam",
        "category_slug": "homams",
        "name": "Sudarshana Homam",
        "tagline": "Protection from negativity, litigation and illness",
        "description": (
            "A potent Vaishnava homam invoking the Sudarshana Chakra of Lord Vishnu, "
            "performed for protection against persistent negativity, prolonged illness, "
            "litigation or enemy trouble. Uses the Sudarshana mantra with sustained ahuti."
        ),
        "default_price": 5700,
        "price_max": 15000,
        "duration_minutes": 150,
        "is_muhurat_bound": False,
        "display_order": 5,
        "inclusions": [
            "2 Vedic purohits trained in Sudarshana mantra and sustained ahuti",
            _GHMC_TRAVEL,
            "Homa gundam, Sudarshana yantra sthapana and full mandapam setup",
            _CORE_SAMAGRI,
            "Samidhalu, extended ghee, navadhanyalu and Sudarshana ashtakshari japam",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Vishnu or Narasimha idol and yantra you wish energised and retained",
        ],
        "requirements": [
            "Open terrace or well-ventilated area — longer duration with heavier smoke",
            "Light satvik diet by the sankalpa-karta on the day, as advised by the purohit",
        ],
        "faqs": [
            {
                "q": "When is Sudarshana Homam recommended?",
                "a": (
                    "Chosen for persistent difficulty — prolonged illness, court matters, "
                    "repeated obstacles — where a general shanti has not helped."
                ),
            },
            {
                "q": "Can it be done inside a flat?",
                "a": (
                    "Not recommended. Duration and ahuti volume produce significant smoke. "
                    "A terrace, open parking area or community hall is safer."
                ),
            },
        ],
        "addons": [
            _kit(1800),
            _premium(
                "Veda Parayanam (2 extra priests)",
                "Two additional purohits for Narasimha and Sudarshana parayanam",
                5000,
                1,
            ),
            _premium(
                "Sudarshana Yantra (energised)",
                "Copper yantra energised in the homam and left with the family",
                3000,
                2,
            ),
        ],
    },
    {
        "id": "a1000019-0000-4000-8000-000000000013",
        "slug": "chandi-homam",
        "category_slug": "homams",
        "name": "Chandi Homam",
        "tagline": "Durga invocation for protection and victory",
        "description": (
            "Powerful Devi homam with Chandipath and sustained ahuti to Goddess Durga. "
            "Performed for protection, court victory, removal of persistent obstacles and "
            "major dosha nivarana. Requires multiple priests and a ventilated venue — "
            "priced as a fixed starter package; larger formats quoted by ops."
        ),
        "default_price": 25000,
        "price_max": 105000,
        "duration_minutes": 240,
        "is_muhurat_bound": False,
        "display_order": 6,
        "inclusions": [
            "4 Vedic purohits for Chandipath and Chandi homam vidhanam",
            _GHMC_TRAVEL,
            "Homa gundam, Devi mandala setup and full mandapam arrangement",
            _CORE_SAMAGRI,
            "Samidhalu, homa dravyalu, navadhanyalu and extended ghee for sustained ahuti",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Kanya puja gifts, large-scale catering and function-hall rental",
        ],
        "requirements": [
            "Large open terrace, function hall or community space with ventilation",
            "Minimum 4 hours; confirm priest count and format with ops before the date",
        ],
        "faqs": [
            {
                "q": "Why is the price range so wide?",
                "a": (
                    "Chandi Homam scale depends on priest count (4 to 11+), Chandipath "
                    "recitations and duration. This listing is a 4-priest starter package. "
                    "Contact ops for 7-priest or 11-priest formats."
                ),
            },
            {
                "q": "Can this be done at home?",
                "a": (
                    "Only in a large villa with open terrace or a rented function hall. "
                    "Standard apartments are not suitable due to smoke and duration."
                ),
            },
        ],
        "addons": [
            _kit(5000),
            _premium(
                "Upgrade to 7-Priest Format",
                "Extended Chandipath with 3 additional purohits — ops confirms final quote",
                38000,
                1,
            ),
            _premium(
                "Floral Mandapam Decoration",
                "Full flower mandapam, stage backdrop and entrance toranam",
                15000,
                2,
            ),
        ],
    },
    # --- Daily & Special -------------------------------------------------------
    {
        "id": "a1000011-0000-4000-8000-00000000000b",
        "slug": "vahana-puja",
        "category_slug": "daily-special",
        "name": "Vahana Puja",
        "tagline": "Blessing for a new vehicle",
        "description": (
            "A short protective puja for a newly purchased vehicle, invoking Ganapati "
            "and performing drishti parihara. Includes marking the vehicle, tying "
            "nimbu-mirchi and a brief safety sankalpam before the first drive."
        ),
        "default_price": 600,
        "price_max": 1500,
        "duration_minutes": 30,
        "is_muhurat_bound": False,
        "display_order": 0,
        "inclusions": [
            "1 purohit for Ganapati invocation and drishti parihara",
            _GHMC_TRAVEL,
            "Compact puja kit and vehicle marking arrangement",
            _CORE_SAMAGRI,
            "Nimbu-mirchi, protective thread and safety sankalpam before the first drive",
        ],
        "exclusions": [
            "Fresh flower garland for the vehicle",
            "Coconut for breaking, fruits and sweets for distribution",
            "Car wash and the vehicle itself — washed and ready at the location",
        ],
        "requirements": [
            "Vehicle parked in an accessible open spot with room to circumambulate",
            "Registration documents present if you want them included in the sankalpam",
        ],
        "faqs": [
            {
                "q": "Can this be done at the showroom?",
                "a": (
                    "Yes, many customers book at delivery. Give the showroom address at "
                    "booking; travel within city limits is included."
                ),
            },
            {
                "q": "Is a muhurtam needed?",
                "a": (
                    "Not strictly. Most families choose the delivery day and avoid Rahu kalam. "
                    "The purohit can suggest a clear window on your chosen date."
                ),
            },
        ],
        "addons": [
            _kit(200),
            _premium(
                "Vehicle Floral Decoration",
                "Full fresh-flower decoration of the vehicle for delivery photos",
                1800,
                1,
            ),
        ],
    },
    {
        "id": "a1000014-0000-4000-8000-00000000000e",
        "slug": "saraswati-puja",
        "category_slug": "daily-special",
        "name": "Saraswati Puja",
        "tagline": "Blessing for learning, arts and examinations",
        "description": (
            "Invocation of Goddess Saraswati for education, artistic skill and examination "
            "success, traditionally on Moola nakshatram during Dasara or on Vasant Panchami. "
            "Books, instruments and tools of learning are placed for blessing."
        ),
        "default_price": 1600,
        "price_max": 3800,
        "duration_minutes": 75,
        "is_muhurat_bound": False,
        "display_order": 1,
        "inclusions": [
            "1 Vedic purohit for Saraswati Ashtottara and vidyarambha sankalpam",
            _GHMC_TRAVEL,
            "Puja setup with kalasham, book and instrument placement arrangement",
            _CORE_SAMAGRI,
            "Saraswati Ashtottara parayanam and akshara guidance if aksharabhyasam included",
        ],
        "exclusions": [
            _FLOWERS_EXCL,
            _NAIVEDYAM_EXCL,
            _DEEPAM_EXCL,
            "Books, musical instruments, laptops or tools of study to be placed for blessing",
        ],
        "requirements": [
            _SPACE_REQ,
            "If aksharabhyasam is included for a child, bring a slate or rice tray",
        ],
        "faqs": [
            {
                "q": "Is this the same as Aksharabhyasam?",
                "a": (
                    "Related but distinct. Saraswati Puja is the worship; Aksharabhyasam is "
                    "the child's first-letter initiation. Select the add-on if you want both."
                ),
            },
            {
                "q": "Best day to book?",
                "a": (
                    "Moola nakshatram during Dasara and Vasant Panchami are traditional. "
                    "Outside those, any Wednesday or exam-eve date works."
                ),
            },
        ],
        "addons": [
            _kit(500),
            _premium(
                "Aksharabhyasam Add-on",
                "First-letter initiation for a child within the same sitting, with slate and guidance",
                1500,
                1,
            ),
            _premium(
                "Floral Decoration",
                "Fresh flower decoration for the puja area and book placement",
                2500,
                2,
            ),
        ],
    },
    # --- Pitru Karyam ----------------------------------------------------------
    {
        "id": "a1000020-0000-4000-8000-000000000014",
        "slug": "taddinam-abdikam",
        "category_slug": "pitru-karyam",
        "name": "Taddinam / Abdikam",
        "tagline": "Annual shraddha on the death tithi",
        "description": (
            "Annual ancestral shraddha performed on the same tithi (lunar day) of passing, "
            "not the English calendar date. Includes pinda pradanam, tarpanam and "
            "punyahavachanam as per your gotra and sampradaya."
        ),
        "default_price": 2000,
        "price_max": 5500,
        "duration_minutes": 120,
        "is_muhurat_bound": True,
        "display_order": 0,
        "inclusions": [
            "1 Vedic purohit trained in shraddha vidhanam for your sampradaya",
            _GHMC_TRAVEL,
            "Pinda pradanam, tarpanam and sankalpam as per Telugu tradition",
            "Guidance on darbha, tila and pinda materials (family arranges per list)",
            "Printed checklist of family-arranged items before the date",
        ],
        "exclusions": [
            "Darbha, tila (sesame), rice, ghee and pinda cooking materials",
            "Brahmana bhojanam food, new clothes for purohit and venue rental",
            "Hiranya shraddha vs homam variant — confirm with purohit at booking",
        ],
        "requirements": [
            "Death tithi details and gotra shared at least 3 days before the date",
            "Clean puja space; vegetarian kitchen for the day as per tradition",
        ],
        "faqs": [
            {
                "q": "Taddinam vs Abdikam — are they the same?",
                "a": (
                    "Both are annual death-anniversary rites. Families use the terms "
                    "interchangeably in Telugu; the purohit follows your kula achara."
                ),
            },
            {
                "q": "Why is there no standard samagri kit?",
                "a": (
                    "Shraddha dravyalu (darbha, tila, pinda) are traditionally prepared by "
                    "the family. Add Brahmin Bhojana Setup if you need bhoktas arranged."
                ),
            },
        ],
        "addons": [
            {
                "name": "Essential Shraddha Dravya Kit",
                "description": (
                    "Tila, rice, ghee and basic pinda-prep items supplied by the purohit. "
                    "Darbha and cooked bhojanam still arranged by family."
                ),
                "price": 800,
                "display_order": 0,
            },
            _premium(
                "Brahmin Bhojana Setup (2 Bhoktas)",
                "Two additional brahmins for aupasana and bhojanam as per Brahmin tradition",
                2200,
                1,
            ),
        ],
    },
    {
        "id": "a1000021-0000-4000-8000-000000000015",
        "slug": "masikam",
        "category_slug": "pitru-karyam",
        "name": "Masikam",
        "tagline": "Monthly ancestral rite on the death tithi",
        "description": (
            "Monthly shraddha performed on the same tithi each month after passing, "
            "until the first annual Abdikam/Taddinam. Shorter than the annual rite but "
            "follows the same pinda pradanam sequence."
        ),
        "default_price": 2000,
        "price_max": 5500,
        "duration_minutes": 90,
        "is_muhurat_bound": True,
        "display_order": 1,
        "inclusions": [
            "1 Vedic purohit for monthly shraddha vidhanam",
            _GHMC_TRAVEL,
            "Pinda pradanam, tarpanam and sankalpam",
            "Guidance on monthly dravya list (family arranges per tradition)",
            "Printed checklist before the date",
        ],
        "exclusions": [
            "Darbha, tila, rice, ghee and pinda materials",
            "Brahmana bhojanam and catering",
            "Annual Abdikam — book separately when the year completes",
        ],
        "requirements": [
            "Death tithi and gotra shared at booking; monthly tithi may shift on panchangam",
            "Vegetarian observance on the day as per family tradition",
        ],
        "faqs": [
            {
                "q": "How long is masikam performed?",
                "a": (
                    "Monthly until the first annual Abdikam/Taddinam, then annually on the "
                    "tithi. Some families continue annual rites only — the purohit will advise."
                ),
            },
            {
                "q": "Can masikam and taddinam use the same booking?",
                "a": (
                    "They are separate listings because vidhanam and duration differ. Book "
                    "Masikam for monthly observance and Taddinam/Abdikam for the annual rite."
                ),
            },
        ],
        "addons": [
            {
                "name": "Essential Shraddha Dravya Kit",
                "description": "Tila, rice, ghee and basic pinda-prep items supplied by the purohit",
                "price": 800,
                "display_order": 0,
            },
            _premium(
                "Brahmin Bhojana Setup (2 Bhoktas)",
                "Two additional brahmins for aupasana and bhojanam",
                2200,
                1,
            ),
        ],
    },
    {
        "id": "a1000022-0000-4000-8000-000000000016",
        "slug": "tarpanam",
        "category_slug": "pitru-karyam",
        "name": "Tarpanam",
        "tagline": "Water offering to ancestors",
        "description": (
            "Tarpanam — offering water with tila and darbha to pitrus — performed on "
            "Amavasya, during Pitru Paksha, or on specific tithis. Shorter than full "
            "shraddha; suitable when a condensed ancestral rite is needed."
        ),
        "default_price": 1200,
        "price_max": 2000,
        "duration_minutes": 45,
        "is_muhurat_bound": True,
        "display_order": 2,
        "inclusions": [
            "1 Vedic purohit for tarpanam vidhanam",
            _GHMC_TRAVEL,
            "Sankalpam and tarpanam sequence as per your gotra",
            "Guidance on darbha and tila arrangement",
            "Printed procedure summary for the family",
        ],
        "exclusions": [
            "Darbha, tila and water vessels — family arranges",
            "Pinda pradanam and homam (not part of standard tarpanam)",
            "Brahmana bhojanam",
        ],
        "requirements": [
            "Gotra and names of ancestors (pitru / matru) shared at booking",
            "Outdoor or balcony access preferred for tarpanam direction",
        ],
        "faqs": [
            {
                "q": "When is tarpanam performed?",
                "a": (
                    "On Amavasya, during Pitru Paksha, on the parent's death tithi, or before "
                    "major samskaras. The purohit will confirm the correct day."
                ),
            },
            {
                "q": "Is this enough instead of full shraddha?",
                "a": (
                    "Tarpanam is a distinct, shorter rite. Annual Abdikam/Taddinam requires "
                    "the full shraddha listing. Do not substitute one for the other."
                ),
            },
        ],
        "addons": [
            {
                "name": "Essential Tarpanam Dravya Kit",
                "description": "Tila, darbha and basic tarpanam items supplied by the purohit",
                "price": 400,
                "display_order": 0,
            },
        ],
    },
]

SEED_PUJA_SLUGS: frozenset[str] = frozenset(p["slug"] for p in PUJAS)
