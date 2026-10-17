"""Civora AI v3.3 - Tamil interface (தமிழ்).

When a user picks "தமிழ் + English" in Settings, the finished page is passed through `translate_html`.
Only WHOLE visible text nodes (and input placeholders) that exactly match an entry below are replaced, so:
  * numbers, units, project names, form values, URLs and calculations are never changed;
  * anything not in the list simply stays in English (safe fallback);
  * <script>, <style>, <svg>, <textarea> and <title> are left alone.
Technical words engineers and dealers use daily (BOQ, BBS, RCC, PCC, M20, TMT, GST, sq.ft, kg, m³) stay in English.
Material names show Tamil with the English name in brackets so a dealer can still match the invoice.
"""
import html as _html
import re

TA = {
    # v3.6.0
    'Vastu': 'வாஸ்து', 'Vastu guide': 'வாஸ்து வழிகாட்டி', 'Multi-drawing analysis': 'பல வரைபட பகுப்பாய்வு',
    'Data storage': 'தரவு சேமிப்பு', 'Save rate': 'விலையை சேமி', 'Check Vastu': 'வாஸ்து சரிபார்',
    'Detailed BOQ total': 'விரிவான BOQ மொத்தம்', 'Not backed up': 'காப்புப்பிரதி இல்லை',
    # ---- shell, menu, top bar
    'Dashboard': 'முகப்பு', 'Projects': 'திட்டங்கள்', 'Drawing Studio': 'வரைபட ஸ்டுடியோ', 'Smart Estimate': 'ஸ்மார்ட் மதிப்பீடு',
    'Structural Studio': 'கட்டமைப்பு ஸ்டுடியோ', 'Rate Master': 'விலைப் பட்டியல்', 'Reports': 'அறிக்கைகள்', 'Team': 'குழு',
    'Settings': 'அமைப்புகள்', 'WORKSPACE': 'பணியிடம்', 'MANAGEMENT': 'மேலாண்மை', 'Advanced tools': 'கூடுதல் கருவிகள்',
    'Project Workflow': 'திட்டப் படிநிலைகள்', 'Measure on drawing': 'வரைபடத்தில் அளவிடு', 'Material Takeoff': 'பொருள் கணக்கீடு',
    'Design Inputs': 'வடிவமைப்பு விவரங்கள்', 'Design Review': 'வடிவமைப்பு மதிப்பாய்வு', 'Home': 'முகப்பு', 'Studio': 'ஸ்டுடியோ',
    'New Project': 'புதிய திட்டம்', 'New project': 'புதிய திட்டம்', '＋ New Project': '＋ புதிய திட்டம்',
    'Construction Intelligence Workspace': 'கட்டுமான நுண்ணறிவுப் பணியிடம்',
    'Engineer review required': 'பொறியாளர் ஆய்வு அவசியம்', 'Guest Preview': 'விருந்தினர் பார்வை', 'Sign in': 'உள்நுழை',
    'Create Account': 'கணக்கு உருவாக்கு', 'Get started': 'தொடங்குக', 'Saved': 'சேமிக்கப்பட்டது', 'All steps done': 'எல்லா படிகளும் முடிந்தது',
    'Workspace': 'பணியிடம்', 'Estimate': 'மதிப்பீடு', 'Structure': 'கட்டமைப்பு', 'Owner': 'உரிமையாளர்', 'Admin': 'நிர்வாகி', 'Creator': 'உருவாக்கியவர்', 'User': 'பயனர்', 'No estimate yet': 'இன்னும் மதிப்பீடு இல்லை',
    'PH:Search projects by name, type or location…': 'பெயர், வகை அல்லது இடம் மூலம் திட்டங்களைத் தேடுக…',
    # ---- workflow steps
    'Project Setup': 'திட்ட அமைப்பு', 'Drawings & Input': 'வரைபடம் & விவரங்கள்', 'Quantity Estimation': 'அளவு மதிப்பீடு',
    'Design Guidance': 'வடிவமைப்பு வழிகாட்டல்', 'Cost & Budget': 'செலவு & பட்ஜெட்', 'Reports & Execute': 'அறிக்கை & செயல்படுத்தல்',
    'Type, location, area': 'வகை, இடம், பரப்பு', 'Upload plans, dimensions': 'வரைபடம், அளவுகள் பதிவேற்று', 'Materials & BOQ': 'பொருட்கள் & BOQ',
    'Structural review': 'கட்டமைப்பு மதிப்பாய்வு', 'Rates & total cost': 'விலை & மொத்த செலவு', 'Excel, PDF, download': 'Excel, PDF, பதிவிறக்கம்',
    'Project setup': 'திட்ட அமைப்பு', 'Drawings & input': 'வரைபடம் & விவரங்கள்', 'Quantity estimation': 'அளவு மதிப்பீடு',
    'Design guidance': 'வடிவமைப்பு வழிகாட்டல்', 'Cost & budget': 'செலவு & பட்ஜெட்', 'Reports ready': 'அறிக்கைகள் தயார்',
    # ---- statuses
    'Draft': 'வரைவு', 'Needs input': 'விவரம் தேவை', 'In progress': 'நடைபெறுகிறது', 'Needs review': 'ஆய்வு தேவை', 'Checked': 'சரிபார்க்கப்பட்டது',
    'Needs engineer review': 'பொறியாளர் ஆய்வு தேவை', 'Pending': 'நிலுவையில்', 'Not ready': 'தயாராகவில்லை', 'Manual entry': 'கைமுறை பதிவு',
    'Reviewed': 'ஆய்வு செய்யப்பட்டது', 'Signed off': 'ஒப்புதல் அளிக்கப்பட்டது', 'Not signed off': 'ஒப்புதல் இல்லை',
    'Not signed off yet': 'இன்னும் ஒப்புதல் இல்லை', 'Provisional': 'தற்காலிகம்', 'Typical size': 'வழக்கமான அளவு', 'Area only': 'பரப்பு மட்டும்',
    'Measured': 'அளக்கப்பட்டது', 'not priced': 'விலை இல்லை', 'just now': 'இப்போது',
    # ---- dashboard
    'How big is your building?': 'உங்கள் கட்டிடம் எவ்வளவு பெரியது?', 'Built-up area (all floors)': 'கட்டுமானப் பரப்பு (எல்லா தளங்களும்)',
    'Get full estimate →': 'முழு மதிப்பீடு பெறுக →', 'Upload a drawing instead': 'பதிலாக வரைபடம் பதிவேற்று',
    'Materials, steel and cost in one click. Have a drawing?': 'பொருட்கள், கம்பி, செலவு — ஒரே கிளிக்கில். வரைபடம் உள்ளதா?',
    'Upload it for an exact estimate': 'துல்லியமான மதிப்பீட்டுக்கு பதிவேற்றுங்கள்', 'Active projects': 'செயலில் உள்ள திட்டங்கள்',
    'owned + shared with you': 'உங்களுடையவை + பகிரப்பட்டவை', 'estimates without sign-off': 'ஒப்புதல் இல்லாத மதிப்பீடுகள்',
    'no estimate or no prices yet': 'மதிப்பீடு அல்லது விலை இன்னும் இல்லை', 'Estimated budget': 'மதிப்பிட்ட பட்ஜெட்',
    'Continue where you left off': 'விட்ட இடத்திலிருந்து தொடருங்கள்', 'Download reports': 'அறிக்கைகளைப் பதிவிறக்கு',
    'Open workspace': 'பணியிடத்தைத் திற', 'View all →': 'அனைத்தையும் பார் →', 'Recent activity': 'சமீபத்திய செயல்பாடு',
    'Your local prices': 'உங்கள் உள்ளூர் விலைகள்', 'Drawing → full estimate': 'வரைபடம் → முழு மதிப்பீடு', 'Start a new building': 'புதிய கட்டிடம் தொடங்கு',
    'Excel, PDF, Download All': 'Excel, PDF, அனைத்தையும் பதிவிறக்கு',
    'New here? Type your building’s built-up area below and press “Get full estimate”.': 'புதியவரா? கீழே கட்டிடப் பரப்பை உள்ளிட்டு “முழு மதிப்பீடு பெறுக” அழுத்துங்கள்.',
    'Have a drawing? Upload it in Drawing Studio for an exact estimate.': 'வரைபடம் உள்ளதா? துல்லியமான மதிப்பீட்டுக்கு வரைபட ஸ்டுடியோவில் பதிவேற்றுங்கள்.',
    # ---- portfolio / wizard
    'All types': 'எல்லா வகைகளும்', 'All statuses': 'எல்லா நிலைகளும்', 'Apply': 'பயன்படுத்து', 'Table': 'அட்டவணை', 'Cards': 'அட்டைகள்',
    'Updated': 'புதுப்பிக்கப்பட்டது', 'Type': 'வகை', 'Area (sq.ft)': 'பரப்பு (sq.ft)', 'Progress': 'முன்னேற்றம்', 'Status': 'நிலை',
    'Project': 'திட்டம்', 'Location': 'இடம்', 'PH:Search name, type, location': 'பெயர், வகை, இடம் தேடுக',
    'Residential': 'குடியிருப்பு', 'Commercial': 'வணிகம்', 'Industrial': 'தொழிற்சாலை', 'Infrastructure': 'உள்கட்டமைப்பு', 'Custom': 'பிற',
    'Not specified': 'குறிப்பிடப்படவில்லை', 'Create a project': 'திட்டம் உருவாக்கு',
    'Four short steps. Everything can be changed later.': 'நான்கு சிறிய படிகள். எதையும் பின்னர் மாற்றலாம்.',
    'Basic details': 'அடிப்படை விவரங்கள்', 'Building': 'கட்டிடம்', 'How to start': 'எப்படித் தொடங்குவது', 'Review': 'சரிபார்', 'Review & create': 'சரிபார்த்து உருவாக்கு',
    'Project type': 'திட்ட வகை', 'Project name': 'திட்டப் பெயர்', 'Built-up area, all floors (sq.ft)': 'கட்டுமானப் பரப்பு, எல்லா தளங்களும் (sq.ft)',
    'Floors': 'தளங்கள்', 'G (ground only)': 'G (தரைத்தளம் மட்டும்)', 'G (ground)': 'G (தரைத்தளம்)',
    'How do you want to start?': 'எப்படித் தொடங்க விரும்புகிறீர்கள்?',
    'Full estimate now from the built-up area and floors. Typical sizes are used.': 'கட்டுமானப் பரப்பு, தளங்களைக் கொண்டு இப்போதே முழு மதிப்பீடு. வழக்கமான அளவுகள் பயன்படும்.',
    'Upload a drawing': 'வரைபடம் பதிவேற்று', 'Civora reads the plan and asks only for what is missing. Most accurate.': 'Civora வரைபடத்தைப் படித்து, விடுபட்டதை மட்டும் கேட்கும். மிகத் துல்லியம்.',
    'Set up later': 'பின்னர் அமை', 'Just create the project; add drawings and estimates any time.': 'திட்டத்தை மட்டும் உருவாக்குங்கள்; வரைபடம், மதிப்பீட்டை எப்போது வேண்டுமானாலும் சேர்க்கலாம்.',
    'Create project →': 'திட்டம் உருவாக்கு →', 'Cancel': 'ரத்து செய்', 'PH:Example: Kumar Residence': 'உதாரணம்: குமார் இல்லம்', 'PH:City, District': 'நகரம், மாவட்டம்',
    # ---- workspace / workflow
    'Project Input': 'திட்ட விவரங்கள்', 'Built-up area': 'கட்டுமானப் பரப்பு', 'Created': 'உருவாக்கப்பட்டது', 'Project details': 'திட்ட விவரங்கள்',
    'Drawings & files': 'வரைபடங்கள் & கோப்புகள்', 'No drawing yet': 'இன்னும் வரைபடம் இல்லை', 'Drawing workspace': 'வரைபடப் பணியிடம்',
    'Material Estimation': 'பொருள் மதிப்பீடு', 'New estimate': 'புதிய மதிப்பீடு', 'Open full BOQ': 'முழு BOQ திற', 'Structural Guidance': 'கட்டமைப்பு வழிகாட்டல்',
    'Reinforcement (BBS)': 'கம்பி அமைப்பு (BBS)', 'Design inputs recorded': 'வடிவமைப்பு விவரங்கள் பதிவு', 'Sign off': 'ஒப்புதல் அளி',
    'Cost Summary': 'செலவு சுருக்கம்', 'Estimated total': 'மதிப்பிட்ட மொத்தம்', 'per sq.ft': 'ஒரு sq.ft-க்கு', 'Apply my rates': 'என் விலைகளைப் பயன்படுத்து',
    'Edit line rates': 'வரி விலைகளைத் திருத்து', 'Download All (ZIP)': 'அனைத்தையும் பதிவிறக்கு (ZIP)', 'Download All': 'அனைத்தையும் பதிவிறக்கு',
    'Download all': 'அனைத்தையும் பதிவிறக்கு', 'Download all reports': 'எல்லா அறிக்கைகளையும் பதிவிறக்கு',
    'All six steps are done.': 'ஆறு படிகளும் முடிந்தன.', 'Download every report as one ZIP.': 'எல்லா அறிக்கைகளையும் ஒரே ZIP-ஆகப் பதிவிறக்குங்கள்.',
    'Upload': 'பதிவேற்று', 'Delete': 'நீக்கு', 'Start Smart Estimate': 'ஸ்மார்ட் மதிப்பீடு தொடங்கு', 'Project workflow': 'திட்டப் படிநிலைகள்',
    'PROJECT WORKFLOW': 'திட்டப் படிநிலைகள்', 'Back to workflow': 'படிநிலைகளுக்குத் திரும்பு',
    'Upload drawing': 'வரைபடம் பதிவேற்று', 'Upload & read drawing': 'பதிவேற்றி வரைபடத்தைப் படி',
    # ---- drawing studio / smart estimate
    'Drawings': 'வரைபடங்கள்', 'No drawings yet.': 'இன்னும் வரைபடங்கள் இல்லை.', 'Get a full estimate from your drawing': 'உங்கள் வரைபடத்திலிருந்து முழு மதிப்பீடு',
    'Choose drawing': 'வரைபடம் தேர்வு', 'Check measurements': 'அளவுகளைச் சரிபார்', 'Estimate ready': 'மதிப்பீடு தயார்',
    'Upload your building plan': 'உங்கள் கட்டிட வரைபடத்தைப் பதிவேற்றுங்கள்', 'Only know the area?': 'பரப்பு மட்டும் தெரியுமா?',
    'Quick estimate': 'விரைவு மதிப்பீடு', 'Quick Estimate': 'விரைவு மதிப்பீடு', 'Know the sizes?': 'அளவுகள் தெரியுமா?',
    'Enter length, width, height and wall details yourself.': 'நீளம், அகலம், உயரம், சுவர் விவரங்களை நீங்களே உள்ளிடுங்கள்.', 'Enter sizes': 'அளவுகளை உள்ளிடு',
    # ---- rate master
    'My Local Rates': 'என் உள்ளூர் விலைகள்', "Enter today's price from your dealer. Leave blank if not used.": 'உங்கள் டீலரின் இன்றைய விலையை உள்ளிடுங்கள். பயன்படுத்தாதவற்றை காலியாக விடுங்கள்.',
    'Rates for work paid by quantity.': 'அளவு அடிப்படையில் கூலி வழங்கும் வேலைகளுக்கான விலை.',
    'Labour is multiplied by the built-up area (sq.ft).': 'கூலி × கட்டுமானப் பரப்பு (sq.ft).', 'Save my rates': 'என் விலைகளைச் சேமி', 'Back to Home': 'முகப்புக்குத் திரும்பு',
    'Shuttering / centring': 'சென்டரிங் (Shuttering)', 'Backfilling': 'மண் நிரப்புதல்', 'Transport': 'போக்குவரத்து', 'GST / tax': 'GST / வரி',
    # ---- materials (Tamil + English so the dealer bill still matches)
    'Cement': 'சிமெண்ட் (Cement)', 'Sand': 'மணல் (Sand)', 'Sand (river / P-sand)': 'மணல் (ஆற்று / P-sand)', 'M-sand': 'எம்-சாண்ட் (M-sand)',
    'Coarse aggregate': 'ஜல்லி (Aggregate)', '20 mm jelly / aggregate': '20 mm ஜல்லி', 'Bricks': 'செங்கல் (Bricks)', 'Red brick': 'செங்கல் (Red brick)',
    'AAC block': 'ஏஏசி பிளாக்', 'AAC adhesive': 'ஏஏசி ஒட்டு பசை', 'Tiles': 'டைல்ஸ் (Tiles)', 'Floor / wall tile': 'தரை / சுவர் டைல்', 'Tile adhesive': 'டைல் ஒட்டு பசை',
    'Paint': 'பெயிண்ட் (Paint)', 'Primer': 'பிரைமர் (Primer)', 'Waterproofing material': 'நீர்க்காப்பு பொருள்', 'Steel / TMT bars': 'கம்பி / TMT',
    'Ready-mix concrete (RMC)': 'ரெடிமிக்ஸ் கான்கிரீட் (RMC)', 'Steel planning allowance (not BBS)': 'கம்பி திட்ட அளவு (BBS அல்ல)', 'Steel': 'கம்பி (Steel)',
    'Formwork': 'சென்டரிங் (Formwork)', 'Labour': 'கூலி', 'Concrete': 'கான்கிரீட்', 'Excavation': 'மண் தோண்டுதல்', 'Backfill': 'மண் நிரப்புதல்',
    'Material': 'பொருள்', 'Materials': 'பொருட்கள்', 'Quantity': 'அளவு', 'Qty': 'அளவு', 'Amount': 'தொகை', 'Rate ₹': 'விலை ₹', 'Total': 'மொத்தம்',
    'Material · how it was worked out': 'பொருள் · எப்படிக் கணக்கிடப்பட்டது',
    # ---- cost & BOQ
    'Cost & BOQ': 'செலவு & BOQ', 'Grand total': 'மொத்தத் தொகை', 'BOQ + charges + GST': 'BOQ + கட்டணங்கள் + GST', 'from Rate Master or entered': 'விலைப் பட்டியல் அல்லது உள்ளீடு',
    'Transport + other': 'போக்குவரத்து + பிற', 'on materials + charges': 'பொருட்கள் + கட்டணங்கள் மீது', 'Per sq.ft': 'ஒரு sq.ft-க்கு',
    'Material cost by stage': 'நிலை வாரியான பொருள் செலவு', 'What money goes where — and roughly in what order you buy.': 'பணம் எங்கே செல்கிறது — எந்த வரிசையில் வாங்குவீர்கள்.',
    'Biggest material costs': 'அதிக செலவுள்ள பொருட்கள்', 'Negotiate these first with your dealer.': 'இவற்றை முதலில் டீலரிடம் பேரம் பேசுங்கள்.',
    'Work items by stage': 'நிலை வாரியான வேலைகள்', 'Foundation': 'அஸ்திவாரம்', 'Frame & slab': 'தூண், பீம் & தளம்', 'Walls': 'சுவர்கள்', 'Finishes': 'பூச்சு வேலைகள்',
    'Roof': 'மேல்தளம்', 'Change any rate, then save. Totals and GST update on this page.': 'எந்த விலையையும் மாற்றிச் சேமியுங்கள். மொத்தமும் GST-யும் இங்கேயே புதுப்பிக்கப்படும்.',
    'Save rates': 'விலைகளைச் சேமி', 'Labour, transport, other charges & GST': 'கூலி, போக்குவரத்து, பிற கட்டணங்கள் & GST', 'Labour ₹': 'கூலி ₹',
    'Transport ₹': 'போக்குவரத்து ₹', 'Other charges ₹': 'பிற கட்டணங்கள் ₹', 'Save charges': 'கட்டணங்களைச் சேமி', 'Structural Studio quantities': 'கட்டமைப்பு ஸ்டுடியோ அளவுகள்',
    'Revisions': 'திருத்தங்கள்', 'Revision': 'திருத்தம்', 'Source': 'மூலம்', 'Work items': 'வேலைகள்', 'Change': 'மாற்றம்', 'View': 'பார்',
    'Set rates in Rate Master →': 'விலைப் பட்டியலில் விலை அமை →', 'Materials (BOQ)': 'பொருட்கள் (BOQ)', 'Materials & services': 'பொருட்கள் & சேவைகள்', 'Contingency & margin': 'எதிர்பாராத செலவு & லாபம்', 'Other charges': 'பிற கட்டணங்கள்',
    'Structural works': 'கட்டமைப்பு வேலைகள்', 'Bar schedule (BBS)': 'கம்பி அட்டவணை (BBS)',
    'One place for every quantity, rate and charge in this project': 'இந்தத் திட்டத்தின் எல்லா அளவு, விலை, கட்டணமும் ஒரே இடத்தில்',
    # ---- structural studio
    'Measured structural quantities, bars and design inputs — element by element': 'அளக்கப்பட்ட கட்டமைப்பு அளவுகள், கம்பிகள், வடிவமைப்பு விவரங்கள் — ஒவ்வொரு உறுப்பாக',
    'Measured quantity ≠ validated design.': 'அளக்கப்பட்ட அளவு ≠ சரிபார்க்கப்பட்ட வடிவமைப்பு.', 'Overview': 'மேலோட்டம்', 'Preliminary frame': 'ஆரம்பநிலை சட்டகம்',
    'Project structure overview': 'திட்டக் கட்டமைப்பு மேலோட்டம்', 'Columns & walls': 'தூண்கள் & சுவர்கள்', 'Beams': 'பீம்கள்', 'Slabs & others': 'தளங்கள் & பிற',
    'Site detail sheet (all elements)': 'தள விவரத் தாள் (எல்லா உறுப்புகளும்)', 'Site detail sheet': 'தள விவரத் தாள்', 'Add element': 'உறுப்பு சேர்',
    'Take sizes from the structural drawing. Give each element its own mark (F1, C1, B1, S1).': 'அளவுகளைக் கட்டமைப்பு வரைபடத்திலிருந்து எடுங்கள். ஒவ்வொரு உறுப்புக்கும் தனிக் குறி (F1, C1, B1, S1).',
    'Element': 'உறுப்பு', 'Elements': 'உறுப்புகள்', 'Count': 'எண்ணிக்கை', 'Length m': 'நீளம் m', 'Width m': 'அகலம் m', 'Depth m': 'ஆழம் m',
    'Drawing / sheet ref': 'வரைபட / தாள் எண்', 'Deduction m³': 'கழிவு m³', 'Calculate & save': 'கணக்கிட்டுச் சேமி', 'Use my Rate Master rates': 'என் விலைப் பட்டியலைப் பயன்படுத்து',
    'Isolated Footing': 'தனி அடித்தளம் (Footing)', 'Combined Footing': 'இணைந்த அடித்தளம்', 'Raft Foundation': 'ராஃப்ட் அஸ்திவாரம்', 'RCC Column': 'RCC தூண்',
    'Plinth Beam': 'பிளிந்த் பீம்', 'Grade Beam': 'கிரேடு பீம்', 'Roof Beam': 'மேல்தள பீம்', 'Lintel': 'லிண்டல்', 'RCC Slab': 'RCC தளம் (Slab)',
    'Sunshade / Chajja': 'சன்ஷேட் / சஜ்ஜா', 'Parapet': 'பாராபெட் சுவர்', 'Retaining Wall': 'தடுப்புச் சுவர்', 'Plain Cement Concrete': 'சாதா சிமெண்ட் கான்கிரீட் (PCC)',
    'Reinforcement details': 'கம்பி அமைப்பு விவரங்கள்', 'Main bars': 'முதன்மைக் கம்பிகள்', 'Ties / stirrups / distribution': 'ரிங் / ஸ்டிரப் / பரவல் கம்பிகள்',
    'Lap zone': 'லேப் பகுதி', 'Engineer sign-off': 'பொறியாளர் ஒப்புதல்', 'Design inputs': 'வடிவமைப்பு விவரங்கள்',
    # ---- BBS
    'Bar Bending Schedule': 'கம்பி வளைப்பு அட்டவணை (BBS)', 'Order list by diameter': 'விட்டம் வாரியான ஆர்டர் பட்டியல்',
    'Give this to the steel dealer. “To order” includes the wastage % entered for each bar.': 'இதைக் கம்பி டீலரிடம் கொடுங்கள். “ஆர்டர் அளவு” ஒவ்வொரு கம்பிக்கும் உள்ளிட்ட கழிவு % சேர்த்தது.',
    'Diameter': 'விட்டம்', 'Bars': 'கம்பிகள்', 'Theoretical': 'கணக்கு அளவு', 'To order': 'ஆர்டர் அளவு', 'Tonnes': 'டன்', 'Steel by diameter': 'விட்டம் வாரியான கம்பி',
    'Bar schedule': 'கம்பி அட்டவணை', 'Cut length': 'வெட்டு நீளம்', 'Total length': 'மொத்த நீளம்', 'kg to order': 'ஆர்டர் kg', 'Add bar': 'கம்பி சேர்',
    'Bar mark': 'கம்பிக் குறி', 'No. of bars': 'கம்பிகளின் எண்ணிக்கை', 'Straight length per bar (m)': 'ஒரு கம்பியின் நேர் நீளம் (m)', 'Calculate & save bar': 'கணக்கிட்டுக் கம்பியைச் சேமி',
    'Wastage %': 'கழிவு %', 'Mark': 'குறி', 'Bar marks': 'கம்பிக் குறிகள்', 'PH:Search bar mark or diameter (e.g. C1, 12)': 'கம்பிக் குறி அல்லது விட்டம் தேடுக (எ.கா. C1, 12)',
    # ---- reports
    'Project reports': 'திட்ட அறிக்கைகள்', 'Documents ready': 'தயாரான ஆவணங்கள்', 'Documents': 'ஆவணங்கள்', 'Total estimate': 'மொத்த மதிப்பீடு',
    'Estimate revisions': 'மதிப்பீட்டுத் திருத்தங்கள்', 'Engineer review': 'பொறியாளர் ஆய்வு', 'Project summary report': 'திட்ட சுருக்க அறிக்கை',
    'Material BOQ': 'பொருள் பட்டியல் (BOQ)', 'Structural quantities': 'கட்டமைப்பு அளவுகள்', 'Structural review report': 'கட்டமைப்பு மதிப்பாய்வு அறிக்கை',
    'Material takeoffs': 'பொருள் கணக்கீடுகள்', 'Summary': 'சுருக்கம்', 'Detail sheet': 'விவரத் தாள்', 'Takeoffs': 'கணக்கீடுகள்',
    'Structural': 'கட்டமைப்பு', 'none yet': 'இன்னும் இல்லை', 'Not ready yet.': 'இன்னும் தயாராகவில்லை.', 'Estimate': 'மதிப்பீடு',
    'no BOQ saved yet': 'இன்னும் BOQ சேமிக்கவில்லை', 'Needs engineer review': 'பொறியாளர் ஆய்வு தேவை', 'Bar marks': 'கம்பிக் குறிகள்',
    'RCC concrete': 'RCC கான்கிரீட்', 'Projects': 'திட்டங்கள்', 'Open & print': 'திறந்து அச்சிடு', 'Open': 'திற', 'Download ZIP': 'ZIP பதிவிறக்கு', 'Filter': 'வடிகட்டு',
    'All projects': 'எல்லா திட்டங்களும்', 'With reports ready': 'அறிக்கைகள் தயாரானவை', 'Print / save PDF': 'அச்சிடு / PDF சேமி', 'Back to reports': 'அறிக்கைகளுக்குத் திரும்பு',
    'Cost summary': 'செலவு சுருக்கம்', 'Main materials': 'முக்கிய பொருட்கள்', 'Steel order by diameter': 'விட்டம் வாரியான கம்பி ஆர்டர்',
    'An engineer must review the design before construction.': 'கட்டுமானத்துக்கு முன் பொறியாளர் வடிவமைப்பை ஆய்வு செய்ய வேண்டும்.',
    'needed before construction': 'கட்டுமானத்துக்கு முன் தேவை', 'the rest show what to do': 'மற்றவை என்ன செய்ய வேண்டும் எனக் காட்டும்',
    'materials + charges + structural': 'பொருட்கள் + கட்டணங்கள் + கட்டமைப்பு', 'you own or were invited to': 'உங்களுடையவை அல்லது அழைக்கப்பட்டவை',
    'across all projects': 'எல்லா திட்டங்களிலும்', 'sum of the latest estimates': 'சமீபத்திய மதிப்பீடுகளின் கூட்டு', 'design not signed off': 'வடிவமைப்புக்கு ஒப்புதல் இல்லை',
    'Print this page or save it as PDF from the print window': 'இந்தப் பக்கத்தை அச்சிடுங்கள் அல்லது அச்சு சாளரத்தில் PDF-ஆகச் சேமியுங்கள்',
    'Every project’s documents in one place — open a project to preview, print or download': 'எல்லா திட்டங்களின் ஆவணங்களும் ஒரே இடத்தில் — முன்னோட்டம், அச்சு, பதிவிறக்கத்துக்கு திட்டத்தைத் திறக்கவும்',
    'Cost, materials, structural totals, steel and review status on one printable page': 'செலவு, பொருட்கள், கட்டமைப்பு, கம்பி, ஆய்வு நிலை — ஒரே அச்சுப் பக்கத்தில்',
    'Every material with quantity, rate and amount': 'ஒவ்வொரு பொருளும் அளவு, விலை, தொகையுடன்',
    'Concrete, formwork, steel by element and the bar bending schedule': 'உறுப்பு வாரியான கான்கிரீட், சென்டரிங், கம்பி மற்றும் BBS',
    'Where the rods go, bend and lap - footing, column, beam, slab sketches': 'கம்பி எங்கே போகும், எங்கே வளையும், எங்கே லேப் — footing, தூண், பீம், தள வரைபடங்கள்',
    'Reconciliation of design inputs against measured quantities': 'வடிவமைப்பு விவரங்கள் vs அளக்கப்பட்ட அளவுகள் ஒப்பீடு',
    'Run an estimate first': 'முதலில் மதிப்பீடு செய்யுங்கள்', 'Run Quick or Smart Estimate': 'விரைவு அல்லது ஸ்மார்ட் மதிப்பீடு செய்யுங்கள்',
    'Add elements in Structural Studio': 'கட்டமைப்பு ஸ்டுடியோவில் உறுப்புகளைச் சேர்', 'Add a footing, column, beam or slab': 'footing, தூண், பீம் அல்லது தளம் சேர்',
    'PH:Search by name, type or location': 'பெயர், வகை அல்லது இடம் தேடுக', 'Drawing quantities with rates': 'விலையுடன் வரைபட அளவுகள்',
    'Printable summary': 'அச்சிடக்கூடிய சுருக்கம்', 'Concrete, steel, formwork, BBS': 'கான்கிரீட், கம்பி, சென்டரிங், BBS', 'Reconciliation report': 'ஒப்பீட்டு அறிக்கை',
    'Elements measured': 'அளக்கப்பட்ட உறுப்புகள்', 'RCC to order': 'RCC ஆர்டர் அளவு', 'Latest saved drawing BOQ': 'கடைசியாகச் சேமித்த BOQ',
    # ---- team
    'People on this project': 'இந்தத் திட்டத்தில் உள்ளவர்கள்', 'Invite people': 'நபர்களை அழை', 'Create invite link': 'அழைப்பு இணைப்பு உருவாக்கு', 'Add': 'சேர்',
    'Create a link and send it on WhatsApp, or add someone who already has a Civora account.': 'இணைப்பை உருவாக்கி WhatsApp-ல் அனுப்புங்கள், அல்லது ஏற்கனவே Civora கணக்கு உள்ளவரைச் சேருங்கள்.',
    'Who can do what': 'யார் என்ன செய்யலாம்', 'Role': 'பங்கு', 'Meaning': 'பொருள்', 'Edit': 'திருத்து', 'Design sign-off': 'வடிவமைப்பு ஒப்புதல்',
    'Engineer': 'பொறியாளர்', 'Colleague': 'சக பணியாளர்', 'Dealer': 'டீலர்', 'Customer': 'வாடிக்கையாளர்', 'Your role:': 'உங்கள் பங்கு:',
    'Everyone on the project can view and download reports.': 'திட்டத்தில் உள்ள அனைவரும் அறிக்கைகளைப் பார்க்கவும் பதிவிறக்கவும் முடியும்.',
    'PH:Their Civora username': 'அவர்களின் Civora பயனர்பெயர்',
    # ---- settings
    'Personalise Civora': 'Civora-வை உங்களுக்கு ஏற்ப அமை', 'How much detail?': 'எவ்வளவு விவரம்?', 'Guided mode': 'எளிய முறை', 'Expert mode': 'நிபுணர் முறை',
    'Both modes use the same calculations. Engineer review warnings show in both.': 'இரண்டு முறைகளும் ஒரே கணக்கீட்டைப் பயன்படுத்தும். பொறியாளர் ஆய்வு எச்சரிக்கைகள் இரண்டிலும் தெரியும்.',
    'Also here': 'இங்கேயும்', 'Database backups': 'தரவுக் காப்புப் பிரதிகள்', 'Save settings': 'அமைப்புகளைச் சேமி', 'Planned — not available yet': 'திட்டமிடப்பட்டது — இன்னும் இல்லை',
    'Units, theme, notifications': 'அலகுகள், தோற்றம், அறிவிப்புகள்',
    # ---- activity log
    'Uploaded a drawing for Smart Estimate': 'ஸ்மார்ட் மதிப்பீட்டுக்கு வரைபடம் பதிவேற்றினார்', 'Ran Smart Estimate': 'ஸ்மார்ட் மதிப்பீடு செய்தார்',
    'Applied Rate Master prices': 'விலைப் பட்டியல் விலைகளைப் பயன்படுத்தினார்', 'Ran Quick Estimate': 'விரைவு மதிப்பீடு செய்தார்',
    'Uploaded a file': 'கோப்பு பதிவேற்றினார்', 'Saved a drawing BOQ': 'வரைபட BOQ சேமித்தார்', 'Edited BOQ line rates': 'BOQ விலைகளைத் திருத்தினார்',
    'Edited labour / transport / tax': 'கூலி / போக்குவரத்து / வரியைத் திருத்தினார்', 'Updated structural design inputs': 'வடிவமைப்பு விவரங்களைப் புதுப்பித்தார்',
    'Updated structural quantities': 'கட்டமைப்பு அளவுகளைப் புதுப்பித்தார்', 'Updated material takeoff': 'பொருள் கணக்கீட்டைப் புதுப்பித்தார்',
    'Updated measurements': 'அளவுகளைப் புதுப்பித்தார்', 'Deleted an item': 'ஒன்றை நீக்கினார்', 'Signed off the design review': 'வடிவமைப்புக்கு ஒப்புதல் அளித்தார்',
    'Recent activity': 'சமீபத்திய செயல்பாடு', 'Notifications': 'அறிவிப்புகள்',
    # ---- v3.4 project data
    'Data': 'தரவு', 'Stored data': 'சேமித்த தரவு', 'Stored data · delete': 'சேமித்த தரவு · நீக்கு', 'Upload a drawing or file': 'வரைபடம் அல்லது கோப்பு பதிவேற்று',
    'Drawings & files': 'வரைபடங்கள் & கோப்புகள்', 'Saved estimates': 'சேமித்த மதிப்பீடுகள்', 'Saved estimates (Quick, Smart, Drawing BOQ)': 'சேமித்த மதிப்பீடுகள் (விரைவு, ஸ்மார்ட், வரைபட BOQ)',
    'Structural elements': 'கட்டமைப்பு உறுப்புகள்', 'Takeoffs & measurements': 'கணக்கீடுகள் & அளவுகள்', 'Bar bending schedule (BBS)': 'கம்பி வளைப்பு அட்டவணை (BBS)',
    'Nothing saved.': 'எதுவும் சேமிக்கப்படவில்லை.', 'Delete this whole project': 'இந்த முழுத் திட்டத்தையும் நீக்கு', 'Delete project': 'திட்டத்தை நீக்கு',
    'Type the project name to confirm': 'உறுதிப்படுத்த திட்டப் பெயரை உள்ளிடுங்கள்', 'Clear all my rates': 'என் எல்லா விலைகளையும் அழி', 'Latest': 'சமீபத்தியது',
    'File': 'கோப்பு', 'Size': 'அளவு', 'Used by': 'பயன்படுத்தியவை', 'Lines': 'வரிகள்', 'Total (excl. structural)': 'மொத்தம் (கட்டமைப்பு தவிர)',
    'BOQ revisions': 'BOQ திருத்தங்கள்', 'manual calculations': 'கைமுறை கணக்கீடுகள்', 'Item': 'உருப்படி',
    'Move my data': 'என் தரவை மாற்று', 'Move projects between Civora sites': 'Civora தளங்களுக்கு இடையே திட்டங்களை மாற்று',
    'Upload into this site': 'இந்தத் தளத்தில் பதிவேற்று', 'Download my data (.zip)': 'என் தரவைப் பதிவிறக்கு (.zip)',
    # ---- safety text (kept bilingual on purpose)
    'DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED.': 'DESIGN INCOMPLETE — ENGINEER REVIEW REQUIRED. (வடிவமைப்பு முழுமையில்லை — பொறியாளர் ஆய்வு அவசியம்.)',
}

# a few count patterns ("6 work item(s)", "5 of 5 ready", "6 of 20 rates set")
PATTERNS = [
    (re.compile(r'^(\d+) work item\(s\)$'), r'\1 வேலைகள்'),
    (re.compile(r'^(\d+) of (\d+) ready$'), r'\2-ல் \1 தயார்'),
    (re.compile(r'^(\d+) of (\d+)$'), r'\2-ல் \1'),
    (re.compile(r'^(\d+) of (\d+) rates set$'), r'\2-ல் \1 விலைகள் அமைக்கப்பட்டன'),
    (re.compile(r'^(\d+) of (\d+) steps done$'), r'\2-ல் \1 படிகள் முடிந்தன'),
    (re.compile(r'^(\d+) min ago$'), r'\1 நிமிடம் முன்'),
    (re.compile(r'^Estimate rev (\d+)$'), r'மதிப்பீடு திருத்தம் \1'),
    (re.compile(r'^Next: (.+)$'), lambda m: 'அடுத்து: ' + TA.get(m.group(1), m.group(1))),
]

_SKIP = re.compile(r'(?is)(<(script|style|svg|textarea|title)\b.*?</\2\s*>)')
_TEXT = re.compile(r'>([^<>]+)<')
_PH = re.compile(r'placeholder="([^"]*)"')


def word(text):
    """Tamil for one exact English string, or None."""
    t = ' '.join(text.split())
    if t in TA:
        return TA[t]
    for rx, rep in PATTERNS:
        m = rx.match(t)
        if m:
            return rep(m) if callable(rep) else m.expand(rep)
    return None


def _text(m):
    raw = m.group(1)
    if not raw.strip():
        return m.group(0)
    ta = word(_html.unescape(raw))
    if ta is None:
        return m.group(0)
    lead = raw[:len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    return '>' + lead + _html.escape(ta, quote=False) + trail + '<'


def _ph(m):
    ta = TA.get('PH:' + _html.unescape(m.group(1)))
    return f'placeholder="{_html.escape(ta)}"' if ta else m.group(0)


def translate_html(doc):
    parts = _SKIP.split(doc)
    out = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i % 3 == 0:
            # text right after a skipped block (e.g. an icon <svg> inside a button) starts without '>'
            lead = '>' if i else ''
            done = _PH.sub(_ph, _TEXT.sub(_text, lead + chunk))
            out.append(done[len(lead):])
            i += 1
        else:
            out.append(chunk)  # skipped block (group 1); group 2 (tag name) follows
            i += 2
    return ''.join(out)
