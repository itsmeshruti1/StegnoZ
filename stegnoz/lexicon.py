"""Generic vocabularies. Nothing here is copied from the practice data's patients: names are a
public-domain-style list of common Indian given names / surnames, and the clinical words are
standard medical vocabulary.  Used as *weak* signals - context decides."""
from __future__ import annotations

# ---------------------------------------------------------------- honorifics / kinship
PRE_HONORIFICS = {
    "mr", "mrs", "ms", "miss", "smt", "shri", "sri", "shrimati", "kumari", "km", "kum", "master",
    "baby", "mst", "sushri", "late", "स्व", "श्री", "श्रीमती", "कुमारी", "सुश्री",
}
POST_HONORIFICS = {
    "ji", "jee", "sahab", "saheb", "sahib", "saab", "didi", "bhai", "bhaiya", "bhaiyya", "bhaiyaa",
    "ben", "behen", "behan", "behenji", "bahenji", "amma", "ammaji", "maa", "mataji", "chacha",
    "chachi", "mausi", "dada", "dadi", "nana", "nani", "babu", "bibi", "begum", "kaka", "kaki",
    "bua", "uncle", "aunty", "aunti", "bhabhi", "bhabi", "jija", "devi",
    "जी", "साहब", "दीदी", "भाई", "भैया", "बहन", "अम्मा", "बेगम", "बाबू",
}
GENERIC_NAME_PARTS = {"devi", "kumar", "kumari", "md", "ji", "bibi", "begum", "bano", "khatoon",
                      "lal", "ram", "prasad", "singh", "kaur", "nath", "chand"}

# relation markers: the following capitalised tokens are a *relative's* name
KIN_MARKERS_LATIN = [
    r"S\s*/\s*[Oo]", r"D\s*/\s*[Oo]", r"W\s*/\s*[Oo]", r"F\s*/\s*[Oo]", r"M\s*/\s*[Oo]",
    r"B\s*/\s*[Oo]", r"Son\s+of", r"Daughter\s+of", r"Wife\s+of", r"Husband\s+of", r"Father\s+of",
    r"Mother\s+of", r"Care\s+of", r"Guardian", r"Attendant", r"Father", r"Husband", r"Mother",
    r"Spouse", r"Relative", r"NOK", r"Next\s+of\s+kin",
]
KIN_MARKERS_DEVA = ["पुत्र", "पुत्री", "पत्नी", "पति", "पिता", "माता", "पिता का नाम", "पति का नाम",
                    "पिता/पति का नाम", "अभिभावक", "बेटा", "बेटी", "सुपुत्र", "सुपुत्री"]
HINGLISH_KIN = {"beta", "beti", "biwi", "pati", "patni", "pita", "papa", "bhai", "bahu", "saas",
                "sasur", "beta", "putra", "putri", "ladka", "ladki", "mummy", "father", "husband",
                "wife", "son", "daughter", "mother", "brother", "sister", "attendant", "rishtedar"}

# ---------------------------------------------------------------- name labels
NAME_LABELS_LATIN = [
    r"patient(?:'s)?\s*name", r"name\s+of\s+(?:the\s+)?patient", r"pt\.?\s*name", r"patient",
    r"pt", r"name", r"naam", r"mareez(?:\s+ka)?\s+naam", r"marij", r"rogi(?:\s+ka)?\s+naam",
    r"report\s+of", r"visitor", r"caller", r"called\s+by", r"raised\s+by", r"witnessed\s+by",
    r"informant", r"contact\s+person", r"attended\s+by", r"brought\s+by", r"referred\s+by\s+relative",
    r"consent\s+(?:given|signed)\s+by", r"signed\s+by", r"accompanied\s+by", r"escorted\s+by",
    r"beneficiary", r"insured", r"policy\s*holder", r"member", r"client", r"customer",
]
NAME_LABELS_DEVA = ["नाम", "मरीज़ का नाम", "मरीज का नाम", "रोगी का नाम", "रोगी", "मरीज़", "मरीज",
                    "लाभार्थी", "आगंतुक"]

DOCTOR_MARKERS = [r"Dr\.?", r"DR\.?", r"Doctor", r"Prof\.?", r"Consultant", r"Surgeon",
                  r"Physician", r"Ref(?:erred)?\.?\s*(?:by\s+)?Dr\.?", r"डॉ\.?", r"डा\.", r"डॉक्टर",
                  r"Sister", r"Nurse", r"Staff\s+Nurse", r"SN", r"Matron"]

# ---------------------------------------------------------------- field-label lexicon (header/key -> kind)
FIELD_LEXICON = {
    "name": ["patient name", "patientname", "name", "naam", "full name", "fullname", "pt name",
             "patient_name", "first", "last", "given", "family", "firstname", "lastname",
             "first name", "last name", "surname", "middle name", "mareez ka naam", "rogi ka naam",
             "नाम", "मरीज़ का नाम", "रोगी का नाम", "local", "display name", "beneficiary name",
             "insured name", "member name", "patient", "pname", "p name", "name local",
             "name hindi", "naam hindi", "visitor", "caller", "raised by", "contact name"],
    "relative": ["relative name", "relative", "guardian", "guardian name", "father name",
                 "father's name", "husband name", "husband's name", "spouse", "spouse name",
                 "pita/pati ka naam", "pita ka naam", "pati ka naam", "pita pati ka naam",
                 "पिता का नाम", "पति का नाम", "पिता/पति का नाम", "next of kin", "nok", "attendant",
                 "attendant name", "kin", "mother name", "care of", "c/o", "so do wo",
                 "relation name", "father/husband", "father husband name"],
    "relation": ["relation", "relationship", "rel", "rishta", "संबंध"],
    "dob": ["dob", "date of birth", "birth date", "birthdate", "d.o.b", "janm tithi", "janam tithi",
            "जन्म तिथि", "जन्मतिथि", "dob (mm/dd/yyyy)", "dob (dd/mm/yyyy)", "birth", "born"],
    "age": ["age", "umar", "umr", "aayu", "आयु", "उम्र", "age (yrs)", "age years", "age_yrs",
            "age in years"],
    "age_sex": ["age/sex", "age_sex", "agesex", "age sex", "age/gender", "age_gender"],
    "gender": ["gender", "sex", "ling", "लिंग", "m/f"],
    "phone": ["mobile", "phone", "mobile no", "phone no", "contact", "contact no", "mob", "mob no",
              "telephone", "tel", "cell", "callback", "whatsapp", "mobile number", "phone number",
              "मोबाइल", "फ़ोन", "फोन", "contact number", "alt mobile", "alternate mobile",
              "emergency contact", "landline", "telecom"],
    "email": ["email", "e-mail", "mail", "email id", "ईमेल"],
    "aadhaar": ["aadhaar", "aadhar", "aadhaar no", "aadhar no", "aadhaar number", "uid", "uidai",
                "aadhar_no", "adhaar", "adhar", "aadhaar_no", "आधार", "आधार सं", "national id"],
    "abha": ["abha", "abha no", "abha number", "health id", "healthid", "abha_no", "abha id",
             "phr", "ndhm id"],
    "abha_addr": ["abha address", "abha_address", "phr address", "health id address"],
    "mrn": ["uhid", "mrn", "reg no", "registration no", "patient id", "patientid", "hospital uhid",
            "hospital_uhid", "patient_ref", "patient ref", "ipd no", "ip no", "opd no", "cr no",
            "crno", "hospital no", "hosp no", "case no", "file no", "pid", "patient no",
            "registration number", "पंजीकरण सं", "पंजीकरण संख्या", "आईपीडी सं", "mr no", "mr number",
            "admission no", "adm no", "uhid no", "id", "patient_id", "record no", "ref no"],
    "insurance": ["pmjay_id", "pmjay id", "policy_no", "policy no", "policy number", "insurance id",
                  "insurance no", "member id", "card no", "ayushman", "claim id", "tpa id",
                  "beneficiary id", "scheme id", "pmjay"],
    "pan": ["pan", "pan no", "payer_pan", "payer pan", "pan number", "pan card"],
    "address": ["address", "addr", "street", "address line", "line", "pata", "पता", "residence",
                "house", "house no", "h.no", "locality", "mohalla", "landmark", "ward no",
                "permanent address", "current address", "address1", "address2", "colony"],
    "village": ["village", "village/mohalla", "gaon", "gram", "गाँव", "गांव", "ग्राम", "city",
                "town", "vill", "village name", "basti", "mauza"],
    "tehsil": ["tehsil", "tahsil", "taluka", "block", "तहसील", "sub district", "subdistrict"],
    "district": ["district", "distt", "jila", "zila", "जिला", "ज़िला", "dist"],
    "state": ["state", "rajya", "राज्य"],
    "pin": ["pin", "pin code", "pincode", "zip", "zip code", "postal code", "postalcode",
            "पिन", "पिन कोड", "post code"],
    "doctor": ["doctor", "ref_doctor", "ref doctor", "consultant", "physician", "referred_by",
               "referred by", "treating doctor", "attending", "surgeon", "doctor name", "dr",
               "practitioner", "author"],
    "date": ["date", "visit_date", "visit date", "reg date", "registration date", "registered",
             "registered on", "registered_on", "admission_date", "discharge_date", "admission date",
             "discharge date", "doa", "dod", "collected_on", "reported_on", "collected", "reported",
             "date of admission", "date of discharge", "bhartee", "registered (mm/dd/yyyy)",
             "visit", "on", "authoredon", "recordeddate", "effectivedatetime", "performeddatetime",
             "issued", "timestamp"],
}

# ---------------------------------------------------------------- clinical vocabulary (never a name)
MEDICAL_WORDS = set("""
fever cough cold pain ache headache giddiness dizziness vomiting nausea diarrhoea diarrhea loose motions
weakness fatigue breathlessness dyspnea dyspnoea chest abdominal abdomen burning micturition swelling
edema oedema rash itching bleeding jaundice palpitation palpitations syncope seizure seizures fits
convulsions body joint joints back knee leg legs arm arms throat sore runny nose sneezing wheeze
wheezing constipation anorexia appetite loss weight unconsciousness confusion altered sensorium
tingling numbness blurring vision hearing ear eye eyes urine urinary retention frequency
dysuria hematuria haematuria melena hematemesis cramps spasm stiffness tremors tremor anxiety
depression insomnia sleep diabetes diabetic hypertension hypertensive hypothyroidism hyperthyroidism
asthma copd tuberculosis tb typhoid malaria dengue chikungunya covid pneumonia anaemia anemia
infection sepsis gastritis gastroenteritis hepatitis cirrhosis appendicitis cholecystitis pancreatitis
nephritis ckd aki stroke cva mi cad ihd angina failure disease syndrome disorder cancer carcinoma
tumour tumor fracture injury wound burn burns bite snake dog scorpion poisoning stone stones calculus
hernia cataract glaucoma otitis sinusitis tonsillitis bronchitis cellulitis abscess ulcer ulcers
migraine epilepsy palsy paralysis arthritis gout osteoarthritis spondylosis spondylitis lupus
psoriasis eczema dermatitis urticaria allergy allergic anaphylaxis shock dehydration hypoglycemia
hyperglycemia ketoacidosis obesity pregnancy pregnant delivery labour labor abortion miscarriage
caesarean cesarean section lscs normal vaginal surgery surgical operation procedure repair
cholecystectomy appendicectomy appendectomy hysterectomy dialysis haemodialysis hemodialysis
transfusion angioplasty bypass laparoscopic laparotomy biopsy endoscopy colonoscopy ultrasound usg
xray x-ray ct mri ecg echo scan test tests report reports result results sample collected
haemoglobin hemoglobin hb glucose sugar random fasting rbs fbs ppbs hba1c creatinine urea serum
sodium potassium chloride bilirubin sgpt sgot alt ast alp albumin protein lipid cholesterol
triglycerides hdl ldl tsh t3 t4 platelet platelets count wbc rbc tlc dlc esr crp ns1 widal
malaria antigen culture sensitivity urine stool blood pressure pulse temperature temp spo2 oxygen
saturation respiratory rate rr bp hr weight height bmi gcs
tab tablet tablets cap capsule capsules inj injection syrup syp susp suspension drops drop
ointment oint cream gel inhaler puffs puff nebulisation nebulization iv im sc po od bd tds tid qid
hs sos stat prn ac pc mg mcg ml g gm kg iu units unit tabs days day week weeks wks month months
yrs years year hrs hours hour min mins
paracetamol dolo crocin calpol amlodipine telmisartan losartan ramipril enalapril metoprolol
atenolol metformin glimepiride gliclazide insulin glargine levothyroxine thyroxine pantoprazole
omeprazole rabeprazole ranitidine ondansetron domperidone metoclopramide ceftriaxone cefixime
amoxicillin augmentin azithromycin doxycycline ciprofloxacin ofloxacin levofloxacin
metronidazole tinidazole artesunate artemether lumefantrine chloroquine primaquine
rifampicin isoniazid pyrazinamide ethambutol salbutamol budesonide montelukast cetirizine
levocetirizine ibuprofen diclofenac aceclofenac tramadol aspirin clopidogrel atorvastatin
rosuvastatin furosemide frusemide spironolactone hydrochlorothiazide ferrous sulphate sulfate
folic acid calcium vitamin multivitamin zinc ors iron b12 d3 dexamethasone prednisolone
hydrocortisone methylprednisolone heparin enoxaparin warfarin digoxin nitroglycerin isosorbide
amikacin gentamicin vancomycin meropenem piperacillin tazobactam linezolid fluconazole
albendazole ivermectin acyclovir oseltamivir ringer lactate saline dextrose normal
advice adv diet review follow followup follow-up rest plenty fluids low salt sugar free continue
stop start stable discharged discharge admitted admission condition improved treated treatment
conservatively course hospital ward bed opd ipd icu emergency casualty department medicine
surgery orthopaedics orthopedics paediatrics pediatrics gynaecology gynecology obstetrics ent
ophthalmology dermatology psychiatry neurology cardiology nephrology urology oncology pulmonary
general physician consultant md ms mbbs dnb frcs mrcp registrar resident
history past significant known case of complaints complaint presenting diagnosis provisional
final impression findings examination investigations medications medication prescription rx
summary note notes nursing vitals chart lab laboratory pathology diagnostics clinic centre center
morning evening night daily twice thrice once after before food meal meals breakfast lunch dinner
bedtime empty stomach with without if needed required as per
""".split())

HINGLISH_MEDICAL = set("""
bukhar bukhaar khansi khasi dard sar sir pet pait ulti ultee dast kamzori chakkar saans sans
jalan sujan khujli peshab pishab pesab khoon thakan neend bhookh bhook bp sugar dawai dawa
goli injection drip theek thik stable hai ho gayi gaya gaye raha rahi rahe hua hui hue nahi
nahin hona karo kar kiya diya diye liya lena dena hai hain tha thi the se ko ka ki ke mein me
par aur ya bhi abhi ab kal aaj raat subah shaam din dino hafte hafta mahine saal baar wala wali
patient mareez marij condition normal band chalu shuru kam zyada jyada bahut thoda khana pani
paani doodh roti chawal dal pura poora poori puri haath pair sar ghutne kamar seena chhati gala
aankh kaan naak daant muh munh
""".split())

COMMON_EN = set("""
the a an and or of to in on at for from by with without as is are was were be been being this that
these those it its he she they them his her their him our we you your i me my mine yes no not
none nil na n/a all any some each every other another same such only also very more most less
least many much few several new old good bad high low left right upper lower front back first
second third last next previous today tomorrow yesterday date time am pm hrs total sr no s.no
copy original duplicate page sheet form record records file files export data system module
generated prepared request research purpose bundle extract extracts summary details detail
information info status pending approved settled rejected closed open active final completed
current entered category type code codes display value unit units range reference ref sample id
report reports doc document documents trip from to remarks remark comment comments note notes
query billing bill amount inr rs package claim claims payer policy scheme ward bed room floor
block unit icu ot opd ipd general private semi male female m f other unknown not specified
yrs years months days weeks year month day week time times hours minutes call called by raised
callback ticket helpdesk support desk staff clerk admin officer it cell team hospital clinic
centre center lab labs laboratory pathology diagnostics city lifeline pathkind multispeciality
multi speciality specialty charitable trust district medical college government govt state up
uttar pradesh india india. lucknow road street near opp opposite behind beside temple mandir
masjid church gurudwara school primary tank pani tanki chowk bazar market colony nagar
forwarded attachment pdf jpg image photo scanned consent witnessed surgical form attendant
visitor log evening round took took morning given en route oxygen ambulance
""".split())

# Words that look like names but are clinical eponyms or community roles - keep them.
EPONYMS = {"parkinson", "parkinson's", "addison", "addison's", "crohn", "crohn's", "alzheimer",
           "alzheimer's", "bell", "bell's", "hodgkin", "hodgkin's", "cushing", "cushing's",
           "graves", "graves'", "hashimoto", "hashimoto's", "down", "down's", "wilson",
           "wilson's", "guillain", "barre", "barré", "raynaud", "raynaud's", "huntington",
           "huntington's", "kawasaki", "meniere", "meniere's", "paget", "paget's", "bright's",
           "pott", "pott's", "colles", "colles'", "whipple", "whipple's", "sjogren", "sjogren's",
           "tourette", "tourette's", "marfan", "turner", "klinefelter", "duchenne", "becker",
           "kaposi", "burkitt", "ewing", "wilms", "hirschsprung", "stevens", "johnson", "reiter",
           "behcet", "takayasu", "buerger", "budd", "chiari", "fallot", "apgar", "glasgow",
           "babinski", "kernig", "brudzinski", "murphy", "murphy's", "mcburney", "homan",
           "trendelenburg", "denver", "gilbert", "gilbert's", "conn", "conn's", "fournier"}
COMMUNITY_ROLES = {"asha", "anm", "aww", "anganwadi", "dai", "mitanin"}

# ---------------------------------------------------------------- generic Indian name gazetteer
GIVEN_NAMES = set("""
aarav aarti aditi aditya ajay ajit akash akhilesh alok aman amar amit amita amrita anand anil
anita anjali anju ankit ankita anoop anuj anupam anuradha anwar arjun arun aruna arvind asha
ashish ashok ashraf ashu asif aslam ayesha babita babu balram bhagwan bharat bhavna bhola
brijesh chandan chandra chhaya deepa deepak deepika dev devendra dhananjay dharmendra dilip
dinesh durga farhan farida faisal fatima firoz ganesh gaurav geeta gita girish gopal govind
gulshan gurpreet hanif harish hari harpreet hemant hina imran indu irfan ishaan jagdish
jameel jamil jasbir jaspreet jaya jitendra jyoti kailash kajal kalpana kamal kamala kamla
kamlesh kanchan karan kavita kiran kishan kishore krishna kuldeep kusum lakshmi lalit lata
laxmi leela madhu mahesh mahendra mamta manish manju manoj meena meera mehboob mohan mohini
mukesh munni nadeem nafisa naresh naseem naveen neelam neeraj neha nikhil nirmala nisha nitin
noor om pankaj parveen parvati pawan pinki pooja poonam pradeep prakash pramod prashant preeti
prem priya priyanka puja pushpa rachna radha rahul raj rajan rajendra rajesh raju rakesh
rakhi ram ramesh rani ranjeet ranjit rashmi ravi reena rekha renu reshma rina ritu rohit roshan
ruby sachin sadhana sagar sahil saira sajid salma sameer samir sandeep sangeeta sanjay sanjeev
santosh sapna sarita satish savita seema shabana shahid shakeel shakuntala shalini shankar
shanti sharda shashi sheela shilpa shiv shivani shobha shyam sita smita sneha sonam sonia
subhash sudha sudhir sudesh suman sumit sunil sunita suraj surendra suresh sushila sushil
swati tabassum tahir tanvi tarun uma umesh usha vandana varsha vijay vikas vikram vimal vinay
vinod vipin vishal yash yogesh zainab zubair zahid zeenat nasreen rubina shabnam afsana
gurmeet sukhwinder harjeet manpreet simran baljeet balwinder kuljeet jasvinder navneet
rajinder joseph mary anthony thomas john george peter david maria grace
""".split())

SURNAMES = set("""
sharma verma gupta singh yadav kumar mishra tiwari pandey dubey dwivedi trivedi chaturvedi
shukla tripathi srivastava saxena mathur agarwal agrawal bansal goyal jain mittal khanna kapoor
malhotra mehta shah patel desai joshi kulkarni deshpande nair menon pillai iyer iyengar reddy
rao naidu chauhan rathore rajput thakur bhatia sethi arora chopra kaur gill sandhu dhillon
khan ansari qureshi siddiqui shaikh sheikh syed rizvi naqvi hussain hasan ahmed ahmad malik
mirza pathan baig bano khatoon begum nishad paswan maurya kushwaha lodhi lodh pal prajapati
saini sahu soni chaudhary choudhary chaudhari jaiswal rastogi kashyap bhardwaj vishwakarma
rawat negi bisht gautam ram jatav valmiki kori kurmi gond meena meghwal masih das dutta
bose banerjee mukherjee chatterjee ghosh sen roy bhattacharya nambiar
""".split())
