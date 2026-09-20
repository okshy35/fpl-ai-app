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
st.write("احصل على تحليل استراتيجي لتشكيلتك وتوصيات بالتبديلات واختيار الكابتن للجولة القادمة.")

# الشريط الجانبي لإدخال البيانات (Sidebar)
st.sidebar.header("⚙️ إعدادات الحساب")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="أدخل مفتاح Gemini API الخاص بك")
team_id = st.sidebar.number_input("FPL Team ID", value=0, step=1, help="رقم فريقك في موقع الفانتسي الرسمي")

def get_fpl_analysis(team_id: int, api_key: str):
    """جلب بيانات الفانتسي وتحليلها عبر Gemini"""
    base_url = "https://fantasy.premierleague.com/api/"
    base_data = requests.get(f"{base_url}bootstrap-static/").json()
    
    # تحديد الجولة الحالية والجولة القادمة
    events = base_data["events"]
    current_gw = next((e["id"] for e in events if e["is_current"]), 1)
    next_gw = current_gw + 1 if current_gw < 38 else 38
    
    # جلب تشكيلة المستخدم
    picks_url = f"{base_url}entry/{team_id}/event/{current_gw}/picks/"
    user_picks = requests.get(picks_url).json()
    
    if "detail" in user_picks and user_picks["detail"] == "Not found.":
        st.error(f"❌ لم يتم العثور على فريق بالرقم {team_id}.")
        return None, None

    # تجهيز سجلات اللاعبين
    players_map = {p["id"]: p for p in base_data["elements"]}
    
    squad_list = []
    for pick in user_picks["picks"]:
        p_info = players_map[pick["element"]]
        squad_list.append({
            "الاسم": p_info["web_name"],
            "الفورمة (Form)": p_info["form"],
            "السعر": p_info["now_cost"] / 10,
            "كابتن": "نعم" if pick["is_captain"] else "لا"
        })
    
    squad_df = pd.DataFrame(squad_list)
    bank_money = user_picks["entry_history"]["bank"] / 10
    free_transfers = user_picks["entry_history"]["event_transfers"]

    # صياغة الاستعلام للذكاء الاصطناعي
    prompt = f"""
    أنت مستشار فانتسي البريميرليج (FPL) محترف. 
    هذه تشكيلتي الحالية وأنا أستعد للتحضير والتخطيط للجولة القادمة (الجولة {next_gw}):
    
    {squad_df.to_string(index=False)}
    
    المبلغ المتاح في البنك (Bank): {bank_money}M
    عدد التبديلات المتاحة (Free Transfers): {free_transfers}
    
    المطلوب تقديم تقرير شامل يحتوي على:
    1. تقييم سريع ومختصر للتشكيلة قبل الجولة {next_gw}.
    2. ترشيح أفضل تبديل للجولة {next_gw} (بيع لاعب وتحديد البديل الأفضل مع التكلفة).
    3. اختيارات الكابتن ونائب الكابتن للجولة {next_gw}.
    4. نصيحة حول الخواص (Chips) وتوقيت استخدامها إذا كان ذلك مناسباً.
    """

    client = genai.Client(api_key=api_key)
    target_model = "gemini-3.6-flash"
    max_attempts = 4
    response_text = None
    
    status_placeholder = st.empty()
    
    for attempt in range(1, max_attempts + 1):
        try:
            status_placeholder.info(f"🔄 جاري تحليل التشكيلة عبر الذكاء الاصطناعي (المحاولة {attempt} من {max_attempts})...")
            response = client.models.generate_content(
                model=target_model,
                contents=prompt
            )
            response_text = response.text
            status_placeholder.empty()
            break
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if attempt < max_attempts:
                    wait_time = attempt * 4
                    status_placeholder.warning(f"⚠️ السيرفر يشهد ضغطاً مؤقتاً.. جاري الانتظار {wait_time} ثوانٍ وإعادة المحاولة تلقائياً...")
                    time.sleep(wait_time)
                else:
                    status_placeholder.empty()
                    st.error("❌ السيرفر مشغول جداً في هذه اللحظة بسبب الإقبال المرتفع. اضغط على الزر مرة أخرى بعد القليل من الوقت.")
                    return None, None
            else:
                status_placeholder.empty()
                st.error(f"❌ حدث خطأ أثناء الاتصال: {e}")
                return None, None

    return response_text, next_gw

# زر التشغيل في الواجهة الرئيسية
if st.button("🚀 بدء التحليل واستخراج التوصيات", type="primary"):
    if not api_key:
        st.warning("⚠️ يرجى إدخال Gemini API Key في الشريط الجانبي أولاً.")
    elif team_id <= 0:
        st.warning("⚠️ يرجى إدخال رقم فريق (Team ID) صحيح.")
    else:
        try:
            report, next_gw = get_fpl_analysis(team_id, api_key)
            if report:
                st.success(f"✅ تم إعداد تقرير الجولة {next_gw} بنجاح!")
                st.markdown("---")
                st.markdown(report)
        except Exception as e:
            st.error(f"حدث خطأ أثناء جلب البيانات: {e}")
