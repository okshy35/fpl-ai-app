import streamlit as st
import requests
import pandas as pd
import time
from google import genai

# إعدادات واجهة المستخدم (Streamlit Page Setup)
st.set_page_config(
    page_title="مساعد الفانتسي الذكي",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ مساعد فانتسي البريميرليج الذكي (FPL AI Advisor)")
st.write("تحليل استراتيجي دقيق يراعي الإصابات، المباريات القادمة، والتبديلات المعلقة.")

# الشريط الجانبي (Sidebar)
st.sidebar.header("⚙️ إعدادات الحساب")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="أدخل مفتاح Gemini API الخاص بك")
team_id = st.sidebar.number_input("FPL Team ID", value=0, step=1, help="رقم فريقك من صفحة النقاط Points")

st.sidebar.subheader("🛠️ ضبط التبديلات والبنك")
manual_ft = st.sidebar.number_input("عدد التبديلات المتاحة المتبقية", min_value=0, max_value=5, value=0)
manual_bank = st.sidebar.number_input("الميزانية المتاحة بالبنك (M£)", min_value=0.0, max_value=15.0, value=0.0, step=0.1)

# تسجيل التبديلات الجديدة المعلقة
st.sidebar.subheader("🔄 التبديل الذي أجريته مؤخراً (اختياري)")
sold_player = st.sidebar.text_input("اسم لاعب قمت ببيعه للجولة القادمة", help="مثل: Joao Pedro")
bought_player = st.sidebar.text_input("اسم لاعب قمت بشرائه بدلاً منه", help="مثل: Solanke")

def get_fpl_analysis(team_id: int, api_key: str, ft: int, bank: float, player_out: str, player_in: str):
    """جلب بيانات الفانتسي مع تحديث التبديلات المعلقة يدوياً"""
    base_url = "https://fantasy.premierleague.com/api/"
    
    # 1. جلب البيانات العامة والمباريات
    base_data = requests.get(f"{base_url}bootstrap-static/").json()
    fixtures_data = requests.get(f"{base_url}fixtures/").json()
    
    events = base_data["events"]
    current_gw = next((e["id"] for e in events if e["is_current"]), 1)
    next_gw = current_gw + 1 if current_gw < 38 else 38
    
    teams_map = {t["id"]: t["short_name"] for t in base_data["teams"]}
    players_map = {p["id"]: p for p in base_data["elements"]}
    
    # تحديد خصوم الجولة القادمة (Fixture Difficulty / Opponents)
    next_fixtures = {}
    for f in fixtures_data:
        if f.get("event") == next_gw:
            h_team = teams_map[f["team_h"]]
            a_team = teams_map[f["team_a"]]
            next_fixtures[f["team_h"]] = f"{a_team} (أرضه)"
            next_fixtures[f["team_a"]] = f"{h_team} (خارجه)"

    # 2. جلب تشكيلة الفريق عبر Team ID
    picks_url = f"{base_url}entry/{team_id}/event/{current_gw}/picks/"
    public_picks = requests.get(picks_url).json()
    
    if "detail" in public_picks and public_picks["detail"] == "Not found.":
        st.error(f"❌ لم يتم العثور على فريق بالرقم {team_id}.")
        return None, None
        
    user_picks = public_picks["picks"]

    # 3. بناء جدول التشكيلة وحالات الإصابة
    squad_list = []
    for pick in user_picks:
        p_info = players_map[pick["element"]]
        opponent = next_fixtures.get(p_info["team"], "غير محدد")
        
        news_status = p_info["news"] if p_info["news"] else "سليم وجاهز"
        chance = p_info["chance_of_playing_next_round"]
        chance_str = f"{chance}%" if chance is not None else "100%"

        squad_list.append({
            "اللاعب": p_info["web_name"],
            "المركز": p_info["element_type"],
            "الخصم القادم": opponent,
            "الفورمة (Form)": p_info["form"],
            "السعر": p_info["now_cost"] / 10,
            "الحالة الطبية/الإصابة": f"{news_status} ({chance_str})",
            "كابتن": "نعم" if pick.get("is_captain") else "لا"
        })
    
    squad_df = pd.DataFrame(squad_list)

    # إضافة صياغة نصية بخصوص التبديل المعلق
    transfer_note = ""
    if player_out and player_in:
        transfer_note = f"""
        ⚠️ تنبيه هام حول التعديل الأخير:
        قام المستخدم بالفعل بعمل تبديل رسمي للجولة القادمة (GW{next_gw}):
        - قام ببيع اللاعب: {player_out}
        - قام بشراء اللاعب: {player_in}
        * يرجى إزالة {player_out} من حسابات التشكيلة واعتبار {player_in} هو المتواجد فعلياً في التشكيلة الحالية عند التحليل واختيار الكابتن.
        """

    # 4. صياغة الاستعلام للذكاء الاصطناعي (Prompt Engineering)
    prompt = f"""
    أنت مستشار فانتسي البريميرليج (FPL) محترف وخبير إحصائي.
    هذه تشكيلة المستخدم المسجلة للجولة {next_gw}:
    
    {squad_df.to_string(index=False)}
    
    {transfer_note}
    
    البيانات المعتمدة من المستخدم حالياً:
    - المبلغ المتاح في البنك (Bank): {bank}M£
    - عدد التبديلات المجانية المتبقية المتاحة (Free Transfers): {ft}
    
    المطلوب تقديم تقرير استراتيجي دقيق يراعي النقاط التالية:
    1. **تحليل التشكيلة المعدلة:** تقييم التشكيلة بعد أخذ التبديل المذكور أعلاه ({player_in} بدلاً من {player_out}) بعين الاعتبار.
    2. **حالة الإصابات:** مراجعة غيابات بقية اللاعبين والتعامل مع أي مصاب آخر.
    3. **النصيحة القادمة:** المتبقي من التبديلات هو {ft}. إذا كان 0، ينصح بعدم إجراء تبديلات إضافية إلا للضرورة القادمة لحفظ النقاط.
    4. **اختيارات الكابتن ونائب الكابتن للجولة {next_gw}.**
    """

    client = genai.Client(api_key=api_key)
    status_placeholder = st.empty()
    
    for attempt in range(1, 4):
        try:
            status_placeholder.info(f"🔄 جاري تحليل التشكيلة المعدلة وحالة الإصابات (المحاولة {attempt} من 3)...")
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

# زر التشغيل
if st.button("🚀 بدء التحليل واستخراج التوصيات", type="primary"):
    if not api_key:
        st.warning("⚠️ يرجى إدخال Gemini API Key أولاً.")
    elif team_id <= 0:
        st.warning("⚠️ يرجى إدخال رقم فريق (Team ID) صحيح.")
    else:
        report, next_gw = get_fpl_analysis(team_id, api_key, manual_ft, manual_bank, sold_player, bought_player)
        if report:
            st.success(f"✅ تم إعداد التقرير بنجاح للجولة {next_gw}!")
            st.markdown("---")
            st.markdown(report)
