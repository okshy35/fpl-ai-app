import streamlit as st
import requests
import pandas as pd
import time
from google import genai

# إعدادات واجهة المستخدم (Streamlit Page Setup)
st.set_page_config(
    page_title="مساعد الفانتسي الذكي المتقدم",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ مساعد فانتسي البريميرليج الذكي - التحديث الشامل (FPL AI Advisor)")
st.write("تحليل استراتيجي متقدم يغطي 5 جولات قادمة، إحصائيات xG/xA، صعوبة المباريات FDR، وتخطيط الخواص (Chips).")

# ==========================================
# 1. الشريط الجانبي (Sidebar)
# ==========================================
st.sidebar.header("⚙️ إعدادات الحساب")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="أدخل مفتاح Gemini API الخاص بك")
team_id = st.sidebar.number_input("FPL Team ID", value=0, step=1, help="رقم فريقك من صفحة النقاط Points")

st.sidebar.subheader("🛠️ ضبط التبديلات والبنك")
manual_ft = st.sidebar.number_input("عدد التبديلات المجانية المتاحة حالياً", min_value=0, max_value=5, value=1)
manual_bank = st.sidebar.number_input("الميزانية المتاحة بالبنك (M£)", min_value=0.0, max_value=15.0, value=0.0, step=0.1)

st.sidebar.subheader("🔄 التبديل المعلق للجولة القادمة (اختياري)")
sold_player = st.sidebar.text_input("لاعب قمت ببيعه", help="مثل: Joao Pedro")
bought_player = st.sidebar.text_input("لاعب قمت بشرائه", help="مثل: Solanke")

st.sidebar.subheader("🃏 الخواص المتبقية لديك (Chips)")
has_wc = st.sidebar.checkbox("الوايلد كارد (Wildcard)", value=True)
has_fh = st.sidebar.checkbox("الفري هيت (Free Hit)", value=True)
has_bb = st.sidebar.checkbox("البنش بوست (Bench Boost)", value=True)
has_tc = st.sidebar.checkbox("التريبل كابتن (Triple Captain)", value=True)

# ==========================================
# 2. الدالة الرئيسية لجلب البيانات والتحليل
# ==========================================
def get_advanced_fpl_analysis(
    team_id: int, 
    api_key: str, 
    ft: int, 
    bank: float, 
    player_out: str, 
    player_in: str,
    chips_status: dict
):
    base_url = "https://fantasy.premierleague.com/api/"
    
    # جلب البيانات الأساسية للبريميرليج والمباريات
    base_data = requests.get(f"{base_url}bootstrap-static/").json()
    fixtures_data = requests.get(f"{base_url}fixtures/").json()
    
    # تحديد الجولة الحالية والجولات الخمس القادمة
    events = base_data["events"]
    current_gw = next((e["id"] for e in events if e["is_current"]), 1)
    next_gw = current_gw + 1 if current_gw < 38 else 38
    future_gws = list(range(next_gw, min(next_gw + 5, 39)))
    
    # خرائط تحويل المعرفات للأنداد والراكز
    teams_map = {t["id"]: t["short_name"] for t in base_data["teams"]}
    players_map = {p["id"]: p for p in base_data["elements"]}
    pos_map = {1: "حارس (GKP)", 2: "مدافع (DEF)", 3: "وسط (MID)", 4: "مهاجم (FWD)"}
    
    # بناء جدول مواجهات الـ 5 جولات القادمة مع مؤشر صعوبة المباريات (Fixture Difficulty Rating - FDR)
    next_5_fixtures = {t_id: [] for t_id in teams_map.keys()}
    
    for gw in future_gws:
        gw_fixtures = [f for f in fixtures_data if f.get("event") == gw]
        for f in gw_fixtures:
            h_id = f["team_h"]
            a_id = f["team_a"]
            h_diff = f["team_h_difficulty"]
            a_diff = f["team_a_difficulty"]
            
            next_5_fixtures[h_id].append(f"{teams_map[a_id]} (أرضه-FDR:{h_diff})")
            next_5_fixtures[a_id].append(f"{teams_map[h_id]} (خارجه-FDR:{a_diff})")

    # جلب تشكيلة الفريق الرسمية
    picks_url = f"{base_url}entry/{team_id}/event/{current_gw}/picks/"
    public_picks = requests.get(picks_url).json()
    
    if "detail" in public_picks and public_picks["detail"] == "Not found.":
        st.error(f"❌ لم يتم العثور على فريق بالرقم {team_id}.")
        return None, None
        
    user_picks = public_picks["picks"]

    # استخراج تفاصيل التشكيلة الشاملة
    squad_list = []
    for pick in user_picks:
        p_info = players_map[pick["element"]]
        p_team = p_info["team"]
        
        # تجميع مواجهات الخمس جولات القادمة
        fixtures_str = " | ".join(next_5_fixtures.get(p_team, [])[:5])
        
        # الحالة الطبية وتفاصيل الإصابات
        news_status = p_info["news"] if p_info["news"] else "سليم وجاهز"
        chance = p_info["chance_of_playing_next_round"]
        chance_str = f"{chance}%" if chance is not None else "100%"
        
        # الإحصائيات الهجومية المتوقعة
        xg = p_info.get("expected_goals", "0.0")
        xa = p_info.get("expected_assists", "0.0")

        squad_list.append({
            "اللاعب": p_info["web_name"],
            "المركز": pos_map.get(p_info["element_type"], "غير محدد"),
            "الفورمة": p_info["form"],
            "السعر": p_info["now_cost"] / 10,
            "xG (أهداف متوقعة)": xg,
            "xA (صناعة متوقعة)": xa,
            "الحالة الطبية": f"{news_status} ({chance_str})",
            "مواجهات الـ 5 جولات القادمة (خصم-مكان-FDR)": fixtures_str,
            "كابتن حالي": "نعم" if pick.get("is_captain") else "لا"
        })
    
    squad_df = pd.DataFrame(squad_list)

    # تجهيز ملاحظة التبديل المجرى إن وجد
    transfer_note = ""
    if player_out and player_in:
        transfer_note = f"""
        ⚠️ تعديل معلق تم إجراؤه بالفعل للجولة القادمة (GW{next_gw}):
        - قام ببيع: {player_out}
        - قام بشراء: {player_in}
        * اعتبر {player_in} موجوداً في التشكيلة الأساسية بدلاً من {player_out} عند التحليل.
        """

    # تحويل الخواص المتبقية لنص
    available_chips = [chip for chip, avail in chips_status.items() if avail]
    chips_str = ", ".join(available_chips) if available_chips else "لا توجد خواص متبقية"

    # ==========================================
    # 3. صياغة الاستعلام للذكاء الاصطناعي (Prompt)
    # ==========================================
    prompt = f"""
    أنت مستشار فانتسي البريميرليج (FPL) الخبير والمحلل الإحصائي المتقدم.
    هذه تشكيلة المستخدم الحالية مع بيانات تفصيلية لخمس جولات قادمة (من GW{next_gw} إلى GW{min(next_gw+4, 38)}):
    
    {squad_df.to_string(index=False)}
    
    {transfer_note}
    
    بيانات الحساب المعتمدة:
    - المبلغ المتاح في البنك (Bank): {bank}M£
    - عدد التبديلات المجانية المتاحة (Free Transfers): {ft}
    - الخواص المتبقية لدى المستخدم (Chips Available): {chips_str}
    
    المطلوب تقديم تقرير استراتيجي تحليلي شامل ومفصل يحتوي على القطاعات التالية:

    1. **تقييم التشكيلة والإصابات (SQUAD & INJURY ASSESSMENT):**
       - مراجعة حالة اللاعبين المصابين والشكوك (بناءً على عمود الحالة الطبية).
       - تقييم أرقام الأهداف المتوقعة (Expected Goals - xG) والتمريرات الحاسمة المتوقعة (Expected Assists - xA) لتحديد اللاعبين المستحقين للتواجد واللاعبين المحظوظين فقط بالنقاط.

    2. **توصية التبديل للجولة {next_gw} (TRANSFER RECOMMENDATION):**
       - إذا كانت التبديلات المتاحة 0، لا تنصح بخصم نقاط (-4) إلا في حال وجود إصابة مؤكدة للاعب أساسي.
       - رشح أفضل لاعب للبيع وأفضل بديل للشراء بناءً على مواجهات الـ 5 جولات القادمة ومؤشر صعوبة المباريات (Fixture Difficulty Rating - FDR).

    3. **اختيارات الكابتن (CAPTAINCY OPTIONS):**
       - **الكابتن الآمن (Safe Captain):** الخيار الأكثر موثوقية للحفاظ على الترتيب.
       - **الكابتن الفارق (Differential Captain):** خيار بمخاطرة أعلى ونسبة ملكية أقل للصعود في الترتيب.

    4. **ترتيب الدكة المثالي (BENCH ORDER):**
       - حدد الترتيب الدقيق للاعبي الدكة (حارس المرمى، دكة 1، دكة 2، دكة 3) مع توضيح سبب الترتيب وفقاً لنسبة المشاركة وصعوبة المواجهة.

    5. **خطة الخواص للجولات الـ 5 القادمة (CHIPS STRATEGY):**
       - تقييم الخواص المتبقية ({chips_str}) واقتراح التوقيت والجولة الأنسب لتفعيل أي منها خلال الـ 5 جولات القادمة إذا كانت هناك جولة صعبة أو جولة دبل (Double Gameweek).
    """

    # الاتصال بنموذج الذكاء الاصطناعي
    client = genai.Client(api_key=api_key)
    status_placeholder = st.empty()
    
    for attempt in range(1, 4):
        try:
            status_placeholder.info(f"🔄 جاري تحليل التشكيلة والـ 5 جولات القادمة عبر الذكاء الاصطناعي (المحاولة {attempt} من 3)...")
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            status_placeholder.empty()
            return response.text, next_gw
        except Exception as e:
            if attempt < 3:
                time.sleep(3)
            else:
                status_placeholder.empty()
                st.error(f"❌ تعذر الحصول على التقرير: {e}")
                return None, None

# ==========================================
# 4. تشغيل التطبيق (Main Trigger)
# ==========================================
if st.button("🚀 بدء التحليل الاستراتيجي المتقدم", type="primary"):
    if not api_key:
        st.warning("⚠️ يرجى إدخال Gemini API Key أولاً.")
    elif team_id <= 0:
        st.warning("⚠️ يرجى إدخال رقم فريق (Team ID) صحيح.")
    else:
        chips_map = {
            "Wildcard": has_wc,
            "Free Hit": has_fh,
            "Bench Boost": has_bb,
            "Triple Captain": has_tc
        }
        report, next_gw = get_advanced_fpl_analysis(
            team_id, api_key, manual_ft, manual_bank, sold_player, bought_player, chips_map
        )
        if report:
            st.success(f"✅ تم إعداد التقرير المتقدم للجولة {next_gw} بنجاح!")
            st.markdown("---")
            st.markdown(report)
