# TDS — `.env` వేరియబుల్స్ (తెలుగు వాయిస్ స్క్రిప్ట్)

**ఎలా వినిపించాలి:** ఈ ఫైల్‌లోని **“వాయిస్ భాగం”** పేరాలను కాపీ చేసి, ఫోన్‌లో **Google Translate → Telugu → Speaker**, లేదా **Google Text-to-Speech (Telugu)**, **Narakeet**, **ElevenLabs (Telugu voice)** లాంటి టూల్‌లో paste చేసి ఆడించండి.  
(కర్సర్‌లో నేరుగా ఆడియో ఫైల్ రూపొందించలేము — ఇది రికార్డ్/టీటీఎస్ కోసం స్క్రిప్ట్.)

**గమనిక:** ఇవి **API సర్వర్ `.env`** లో పెట్టే `true` / `false` స్విచ్‌లు. మార్చిన తర్వాత **uvicorn రీస్టార్ట్** చేయాలి.

---

## వాయిస్ భాగం — పూర్తి వివరణ (ఒకేసారి చదవండి / టీటీఎస్)

నమస్తే. ఇది మన గురుజీ ప్లాట్‌ఫారమ్‌లో **TDS మరియు PAN** కు సంబంధించిన **ఎన్విరాన్మెంట్ వేరియబుల్స్** — అంటే సర్వర్ సెట్టింగ్‌లు — సాధారణ తెలుగులో.

---

### ఒకటి — T D S A C C R U A L E N A B L E D

**TDS_ACCRUAL_ENABLED.**

ఇది **true** అయితే: సిస్టమ్ **టీడీఎస్‌ను లెక్కించి డేటాబేస్‌లో నమోదు చేస్తుంది** — పూజారి ఒక బుకింగ్ **అక్సెప్ట్** చేసినప్పుడు, ఆ financial year టోటల్, ఎంత TDS applicable అనేది కూడా ట్రాక్ అవుతుంది.

**false** అయితే: ఈ ట్రాకింగ్ చalıపి ఉంటుంది — launch కు TDS off posture.

**లేమన్:** “టీడీఎస్ గణన మరియు రికార్డ్ ఆన్/ఆఫ్.”  
**ముఖ్యం:** ఇది **ప్రభుత్వానికి TDS చెల్లింపు** కాదు — అది వేరే భవిష్యత్ దశ.

---

### రెండు — T D S A C C E P T S T U B C O L L E C T

**TDS_ACCEPT_STUB_COLLECT.**

**true** — **టెస్టింగ్ కోసం.** అక్సెప్ట్ చేసిన వెంటనే “కస్టమర్ ఆన్‌లైన్‌లో TDS చెల్లించినట్లు” అని సిస్టమ్ **నటిస్తుంది** — Razorpay లేకుండా.

**false** — **నిజమైన “ప్లాట్‌ఫారమ్ TDS భరిస్తుంది”** మోడల్: పూజా **మొత్తం ఆఫ్‌లైన్**; TDS ఆన్‌లైన్‌లో కస్టమర్ నుండి collection simulate చేయదు.

**లేమన్:** “టెస్ట్‌లో TDS online collect అయినట్లు నటన” — production platform-bears కు **false**.

---

### మూడు — P A N A C C E P T G A T E E N A B L E D

**PAN_ACCEPT_GATE_ENABLED.**

**true** — PAN **ప్రొఫైల్‌లో లేకుండా** పూజారి **ఏ offer ను accept చేయలేడు** — FY **₹5 లక్షల** కంటే తక్కువ ఉన్నా block.

**false** — “ప్రతి accept కు PAN అవసరం” నియమం **ఆఫ్**.

**లేమన్:** “PAN లేకుండా offer accept చేయడం పూర్తిగా నిషేధం — FY సంఖ్య చూడదు.”  
**₹5 లక్ష తర్వాత మాత్రమే PAN** policy కు ఇది **false** ఉండాలి.

---

### నాలుగు — P U J A R I F Y P A N G A T E E N A B L E D

**PUJARI_FY_PAN_GATE_ENABLED.**

**true** — **₹5 లక్ష FY facilitation** నియమం:

- సుమారు **₹4.5 లక్ష** దగ్గర — **warning** (accept కు hard block కాదు; messages/snackbar).
- **₹5 లక్ష cross** — **operative PAN** (Setu verify success) లేకుండా:
  - **offer accept** block,
  - **online** (go online / heartbeat) block.
- **accept చేసే offer** వలన FY **₹5L cross** అవుతుందా అని చూస్తారు — ఉదాహరణ: ₹4.99L + ₹3000 offer → accept block, PAN verify వరకు.

**false** — ఈ ₹5L PAN gate ఆఫ్.

**లేమన్:** “₹5 లక్ష దాటిన తర్వాత PAN తప్పనిసరి — దానికి ముందు PAN లేకుండా accept OK (ఇతర gates off అయితే).”

---

### ఐదు — P U J A R I T A X P R O F I L E R E Q U I R E D F O R A C C E P T

**PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT.**

**true** — **ప్రతి accept** కు **PAN + entity type** (individual / HUF / firm…) **రెండూ** ఉండాలి — FY ₹0 నుండే.

**false** — accept కు “full tax profile” అవసరం లేదు.

**లేమన్:** “PAN accept gate కంటే కఠినం — entity type కూడా తప్పనిసరి, ₹5L చూడకుండా.”  
**₹5L వరకు PAN లేకుండా పని** policy కు ఇది **false**.

---

### ఆరు — Setu PAN verify (TDSకు సహాయకం)

**KYC_SETU_PAN_PRODUCT_ID** — Setu లో PAN verify product ID.  
**KYC_SETU_BASE_URL, CLIENT_ID, CLIENT_SECRET** — Setu sandbox లేదా production connection.

**లేమన్:** “PAN నమోదు చేసినట్టు మాత్రమే సరిపోదు — **verify** అయితే **operative PAN**; ₹5L gate దీన్నే చూస్తుంది.”

Production లో PAN product ID లేకుంటe PAN submit fail / 503 రావచ్చు.

---

### ఏడు — APP E N V మరియు DEBUG (TDS direct కాదు)

**APP_ENV=production** — strict rules (PAN verify config).  
**DEBUG=true** — dev OTP logs; production లో false.

---

## మీ policy కు సిఫార్సు combo (సాధారణ)

**“₹5 లక్ష varaku PAN lekunda accept; ₹5L tarvata operative PAN”:**

- TDS_ACCRUAL_ENABLED = true (staging tracking)
- PUJARI_FY_PAN_GATE_ENABLED = true
- PAN_ACCEPT_GATE_ENABLED = **false**
- PUJARI_TAX_PROFILE_REQUIRED_FOR_ACCEPT = **false**
- TDS_ACCEPT_STUB_COLLECT = false (platform-bears) లేదా true (testing stub only)

**Celery worker + beat** — accrual/dispatch/notifications/sweep; `.env` కాదు కానీ **process** — accrual true అయితే run చేయాలి.

---

## ₹5L / 0.1% / 5% — `.env` లో లేవు

**₹4.5L warn, ₹5L block, 0.1%, 5% fail-safe** — admin **platform_settings** / DB statutory config. `.env` flags **features on/off** మాత్రమే.

---

## చివరి సారాంశం (30 సెకన్లు)

TDS_ACCRUAL — లెక్కలు ఆన్.  
TDS_ACCEPT_STUB — టెస్ట్‌లో online TDS నటన.  
PAN_ACCEPT_GATE — PAN లేకుండా **ఎప్పుడూ** accept వద్దు.  
PUJARI_FY_PAN_GATE — **₹5L** తర్వాత operative PAN తప్పనిసరి.  
PUJARI_TAX_PROFILE — PAN + entity type **ఎప్పుడూ** accept కు.  
Setu IDs — PAN **verify** కోసం.

ధన్యవాదాలు.

---

## చిన్న వాయిస్ భాగం — quick recap only (1 minute)

TDS env variables — server lo true false switches.

Accrual enabled — TDS track cheyyadam database lo.

Stub collect — test lo customer TDS pay chesinattu act cheyyadam; real platform model ki false.

Pan accept gate true — PAN lekunda eppudu offer accept cheyaleru; five lakh kante takkuva unna kuda.

Fy pan gate true — five lakh financial year cross ayyaka Setu verify PAN lekunda accept and online block; four point five lakh daggara warning.

Tax profile required true — PAN plus entity type rendu lekunda prati accept block; fy chudadu.

Pan accept false plus tax profile false plus fy pan gate true — five lakh varaku PAN lekunda accept; cross ayyaka PAN mandatory.

Setu pan product id — PAN verify; operative ani matrame gate satisfy.

Migrations tarvata uvicorn restart cheyandi.

---

*Last updated for repo policy docs: PAN_FY_GATES.md, TDS_RUNTIME_CONFIG.md*
