import os
import hmac
import hashlib
import secrets
import streamlit as st
from supabase import create_client, Client
from streamlit_autorefresh import st_autorefresh

# -------------------- Page --------------------
st.set_page_config(
    page_title="مدیریت کارهای خانه",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

TASKS = {
    "جارو": "🧹",
    "ظرف‌ها": "🍽️",
    "آشغال": "🗑️",
    "سفره": "🧺",
    "خرید": "🛒",
    "لباس‌ها": "👕",
}
PEOPLE = ["هانی", "احمرضا", "ارمیا"]
STATE_ID = 1
ADMIN_ID = 1
PBKDF2_ITERATIONS = 310_000

# -------------------- Styling --------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], button, input, textarea {
    font-family: 'Vazirmatn', sans-serif !important;
}
.block-container {max-width: 1100px; padding-top: 2rem; direction: rtl;}
h1,h2,h3,p,div,label {text-align: right;}
.task-card {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 12px;
    background: rgba(128,128,128,.035);
}
.person-row {
    display:flex; align-items:center; justify-content:space-between;
    padding: 8px 10px; margin: 5px 0; border-radius: 10px;
    background: rgba(128,128,128,.07);
}
.rank {font-weight:800; min-width:34px; text-align:center;}
.small-muted {opacity:.7; font-size:.85rem;}
.stButton>button {border-radius: 10px; min-height: 42px;}
[data-testid="stForm"] {border: 1px solid rgba(128,128,128,.25); border-radius: 14px;}
</style>
""", unsafe_allow_html=True)

# -------------------- Supabase --------------------
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError(
            "تنظیمات Supabase پیدا نشد. فایل secrets.toml را طبق README تنظیم کنید."
        )
    return create_client(url, key)

def hash_password(password: str, salt_hex: str | None = None):
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()

def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    _, actual = hash_password(password, salt_hex)
    return hmac.compare_digest(actual, expected_hash)

def initialize_admin_if_needed(sb: Client):
    rows = sb.table("admin_credentials").select("*").eq("id", ADMIN_ID).limit(1).execute().data
    if rows:
        return
    # Bootstrap values are private server-side secrets. They are used only once.
    username = st.secrets.get("INITIAL_ADMIN_USERNAME", "")
    password = st.secrets.get("INITIAL_ADMIN_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "حساب مدیر هنوز ساخته نشده است. INITIAL_ADMIN_USERNAME و "
            "INITIAL_ADMIN_PASSWORD را در Secrets تنظیم کنید."
        )
    salt, digest = hash_password(password)
    sb.table("admin_credentials").insert({
        "id": ADMIN_ID,
        "username": username.strip(),
        "password_salt": salt,
        "password_hash": digest,
    }).execute()

def get_orders(sb: Client):
    rows = sb.table("task_state").select("orders").eq("id", STATE_ID).limit(1).execute().data
    if not rows:
        raise RuntimeError("ردیف task_state پیدا نشد. فایل schema.sql را کامل اجرا کنید.")
    return rows[0]["orders"]

def login(sb: Client, username: str, password: str) -> bool:
    rows = (
        sb.table("admin_credentials")
        .select("username,password_salt,password_hash")
        .eq("id", ADMIN_ID)
        .limit(1)
        .execute().data
    )
    if not rows:
        return False
    row = rows[0]
    return (
        hmac.compare_digest(username.strip(), row["username"])
        and verify_password(password, row["password_salt"], row["password_hash"])
    )

def change_password(sb: Client, old_password: str, new_password: str):
    rows = (
        sb.table("admin_credentials")
        .select("password_salt,password_hash")
        .eq("id", ADMIN_ID)
        .limit(1)
        .execute().data
    )
    if not rows or not verify_password(old_password, rows[0]["password_salt"], rows[0]["password_hash"]):
        return False
    salt, digest = hash_password(new_password)
    sb.table("admin_credentials").update({
        "password_salt": salt,
        "password_hash": digest,
    }).eq("id", ADMIN_ID).execute()
    return True

def complete_task(sb: Client, task: str):
    result = sb.rpc("complete_task", {"p_task": task}).execute()
    return result.data

def reset_all(sb: Client):
    sb.rpc("reset_all_tasks").execute()

# -------------------- App --------------------
st.markdown("<h1 style='text-align:center'>🏠 مدیریت کارهای خانه</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;opacity:.7'>نوبت‌ها را منظم، ساده و مشترک مدیریت کنید</p>", unsafe_allow_html=True)

try:
    supabase = get_supabase()
    initialize_admin_if_needed(supabase)
except Exception as e:
    st.error(f"اتصال یا راه‌اندازی دیتابیس کامل نیست: {e}")
    st.info("راهنمای نصب را در فایل README.md بخوانید.")
    st.stop()

if not st.session_state.get("authenticated", False):
    st.markdown("### 🔐 ورود مدیر")
    with st.form("login_form"):
        username = st.text_input("نام کاربری")
        password = st.text_input("رمز عبور", type="password")
        submitted = st.form_submit_button("ورود", use_container_width=True)
    if submitted:
        try:
            if login(supabase, username, password):
                st.session_state.authenticated = True
                st.session_state.admin_username = username.strip()
                st.rerun()
            else:
                st.error("نام کاربری یا رمز عبور اشتباه است.")
        except Exception as e:
            st.error(f"خطا هنگام ورود: {e}")
    st.caption("این برنامه فقط یک حساب مدیر دارد. افراد نام‌برده‌شده در فهرست، حساب کاربری جداگانه ندارند.")
    st.stop()

# Sidebar: settings and logout
with st.sidebar:
    st.success(f"وارد شده‌اید: {st.session_state.get('admin_username', 'مدیر')}")
    if st.button("خروج از حساب", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.pop("admin_username", None)
        st.rerun()

    st.markdown("---")
    st.subheader("🔑 تغییر رمز مدیر")
    with st.form("change_password_form"):
        old_pw = st.text_input("رمز فعلی", type="password")
        new_pw = st.text_input("رمز جدید", type="password")
        confirm_pw = st.text_input("تکرار رمز جدید", type="password")
        change_submit = st.form_submit_button("ذخیره رمز جدید", use_container_width=True)
    if change_submit:
        if len(new_pw) < 10:
            st.error("رمز جدید باید حداقل ۱۰ نویسه داشته باشد.")
        elif new_pw != confirm_pw:
            st.error("تکرار رمز جدید یکسان نیست.")
        elif change_password(supabase, old_pw, new_pw):
            st.success("رمز با موفقیت تغییر کرد.")
        else:
            st.error("رمز فعلی صحیح نیست.")

# Poll shared database every 5 seconds so other devices see changes automatically.
st_autorefresh(interval=5000, key="shared_state_refresh")

st.markdown("---")
st.markdown("### 📋 نوبت کارها")
st.caption("با زدن دکمه «انجام شد»، نام آن شخص در همان کار به انتهای صف منتقل می‌شود.")

try:
    orders = get_orders(supabase)
except Exception as e:
    st.error(f"خواندن اطلاعات ممکن نشد: {e}")
    st.stop()

cols = st.columns(3)
for idx, (task, emoji) in enumerate(TASKS.items()):
    with cols[idx % 3]:
        with st.container(border=True):
            st.subheader(f"{emoji} {task}")
            current_order = orders.get(task, PEOPLE)
            for rank, person in enumerate(current_order, start=1):
                if rank == 1:
                    st.success(f"🥇  {rank} ـ {person}")
                elif rank == 2:
                    st.warning(f"🥈  {rank} ـ {person}")
                else:
                    st.info(f"🥉  {rank} ـ {person}")
            current_person = current_order[0]
            if st.button(
                f"✓ انجام شد: {current_person}",
                key=f"done_{task}",
                use_container_width=True,
                type="primary",
            ):
                try:
                    complete_task(supabase, task)
                    st.toast(f"نوبت {task} به‌روزرسانی شد", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"ثبت تغییر انجام نشد: {e}")

st.markdown("---")
left, right = st.columns([2, 1])
with left:
    st.caption("اطلاعات در دیتابیس آنلاین ذخیره می‌شود و از همه دستگاه‌ها قابل مشاهده است.")
with right:
    if st.button("🔄 تازه‌سازی اطلاعات", use_container_width=True):
        st.rerun()

with st.expander("⚠️ بازنشانی همه نوبت‌ها"):
    st.warning("با این کار ترتیب تمام کارها به هانی، احمرضا، ارمیا برمی‌گردد.")
    confirm_reset = st.checkbox("بازنشانی همه شش کار را تأیید می‌کنم")
    if st.button("بازنشانی نوبت‌ها", disabled=not confirm_reset):
        try:
            reset_all(supabase)
            st.success("همه نوبت‌ها بازنشانی شدند.")
            st.rerun()
        except Exception as e:
            st.error(f"بازنشانی انجام نشد: {e}")
