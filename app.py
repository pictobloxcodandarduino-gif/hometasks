
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

.block-container {
    max-width: 1100px;
    padding-top: 2rem;
    direction: rtl;
}

h1,h2,h3,p,div,label {
    text-align: right;
}

.stButton>button {
    border-radius: 10px;
    min-height: 42px;
}

[data-testid="stForm"] {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 14px;
}
</style>
""", unsafe_allow_html=True)


# -------------------- Supabase --------------------
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
    key = st.secrets.get(
        "SUPABASE_SERVICE_ROLE_KEY",
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    if not url or not key:
        raise RuntimeError("تنظیمات Supabase پیدا نشد.")

    return create_client(url, key)


# -------------------- Password --------------------
def hash_password(password: str, salt_hex: str | None = None):
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS
    )

    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, expected_hash):
    _, actual = hash_password(password, salt_hex)
    return hmac.compare_digest(actual, expected_hash)


# -------------------- Admin --------------------
def initialize_admin_if_needed(sb):
    rows = (
        sb.table("admin_credentials")
        .select("*")
        .eq("id", ADMIN_ID)
        .limit(1)
        .execute().data
    )

    if rows:
        return

    username = st.secrets.get("INITIAL_ADMIN_USERNAME", "")
    password = st.secrets.get("INITIAL_ADMIN_PASSWORD", "")

    if not username or not password:
        raise RuntimeError(
            "INITIAL_ADMIN_USERNAME و INITIAL_ADMIN_PASSWORD را در Secrets تنظیم کنید."
        )

    salt, digest = hash_password(password)

    sb.table("admin_credentials").insert({
        "id": ADMIN_ID,
        "username": username.strip(),
        "password_salt": salt,
        "password_hash": digest,
    }).execute()


def login(sb, username, password):
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
        and verify_password(
            password,
            row["password_salt"],
            row["password_hash"]
        )
    )


def change_password(sb, old_password, new_password):
    rows = (
        sb.table("admin_credentials")
        .select("password_salt,password_hash")
        .eq("id", ADMIN_ID)
        .limit(1)
        .execute().data
    )

    if not rows:
        return False

    row = rows[0]

    if not verify_password(
        old_password,
        row["password_salt"],
        row["password_hash"]
    ):
        return False

    salt, digest = hash_password(new_password)

    sb.table("admin_credentials").update({
        "password_salt": salt,
        "password_hash": digest,
    }).eq("id", ADMIN_ID).execute()

    return True


# -------------------- Database --------------------
def get_orders(sb):
    rows = (
        sb.table("task_state")
        .select("orders")
        .eq("id", STATE_ID)
        .limit(1)
        .execute().data
    )

    if not rows:
        raise RuntimeError("ردیف task_state پیدا نشد.")

    return rows[0]["orders"]


def get_completion_counts(sb):
    rows = (
        sb.table("task_state")
        .select("completion_counts")
        .eq("id", STATE_ID)
        .limit(1)
        .execute().data
    )

    if not rows:
        raise RuntimeError("اطلاعات شمارنده‌ها پیدا نشد.")

    return rows[0].get("completion_counts") or {}


def complete_task(sb, task, person):
    return sb.rpc(
        "complete_task",
        {
            "p_task": task,
            "p_person": person
        }
    ).execute()


def reset_all(sb):
    sb.rpc("reset_all_tasks").execute()


# -------------------- Callback --------------------
def register_task(task, person):
    """
    این تابع قبل از اجرای دوباره صفحه فراخوانی می‌شود.
    هر بار فعال شدن چک‌باکس فقط یک بار ثبت انجام می‌دهد.
    """
    sb = get_supabase()

    try:
        complete_task(sb, task, person)

        st.session_state["last_message"] = (
            f"یک مورد {task} برای {person} ثبت شد."
        )

        st.session_state["last_message_type"] = "success"

    except Exception as e:
        st.session_state["last_message"] = (
            f"ثبت کار انجام نشد: {e}"
        )

        st.session_state["last_message_type"] = "error"


# -------------------- App --------------------
st.markdown(
    "<h1 style='text-align:center'>🏠 مدیریت کارهای خانه</h1>",
    unsafe_allow_html=True
)

st.markdown(
    "<p style='text-align:center;opacity:.7'>نوبت‌ها را منظم، ساده و مشترک مدیریت کنید</p>",
    unsafe_allow_html=True
)


# -------------------- Connection --------------------
try:
    supabase = get_supabase()
    initialize_admin_if_needed(supabase)

except Exception as e:
    st.error(f"اتصال یا راه‌اندازی دیتابیس کامل نیست: {e}")
    st.stop()


# -------------------- Login --------------------
if not st.session_state.get("authenticated", False):

    st.markdown("### 🔐 ورود مدیر")

    with st.form("login_form"):

        username = st.text_input("نام کاربری")
        password = st.text_input("رمز عبور", type="password")

        submitted = st.form_submit_button(
            "ورود",
            use_container_width=True
        )

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

    st.caption(
        "این برنامه فقط یک حساب مدیر دارد."
    )

    st.stop()


# -------------------- Sidebar --------------------
with st.sidebar:

    st.success(
        f"وارد شده‌اید: {st.session_state.get('admin_username', 'مدیر')}"
    )

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

        change_submit = st.form_submit_button(
            "ذخیره رمز جدید",
            use_container_width=True
        )

    if change_submit:

        if len(new_pw) < 10:
            st.error("رمز جدید باید حداقل ۱۰ نویسه داشته باشد.")

        elif new_pw != confirm_pw:
            st.error("تکرار رمز جدید یکسان نیست.")

        elif change_password(supabase, old_pw, new_pw):
            st.success("رمز با موفقیت تغییر کرد.")

        else:
            st.error("رمز فعلی صحیح نیست.")


# -------------------- Refresh --------------------
st_autorefresh(
    interval=5000,
    key="shared_state_refresh"
)


# -------------------- Messages --------------------
message = st.session_state.pop("last_message", None)
message_type = st.session_state.pop("last_message_type", None)

if message:
    if message_type == "success":
        st.success(message)
    else:
        st.error(message)


# -------------------- Tasks --------------------
st.markdown("---")
st.markdown("### 📋 کارها و انتخاب افراد")

st.caption(
    "با هر بار زدن تیک، یک واحد به شمارنده همان شخص اضافه می‌شود. "
    "برای ثبت دوباره، دوباره تیک را بزن."
)

try:
    orders = get_orders(supabase)
    completion_counts = get_completion_counts(supabase)

except Exception as e:
    st.error(f"خواندن اطلاعات ممکن نشد: {e}")
    st.stop()


cols = st.columns(3)

for idx, (task, emoji) in enumerate(TASKS.items()):

    with cols[idx % 3]:

        with st.container(border=True):

            st.subheader(f"{emoji} {task}")

            current_order = orders.get(task, PEOPLE)
            task_counts = completion_counts.get(task, {})

            st.markdown("**ترتیب فعلی نوبت‌ها**")

            for rank, person in enumerate(current_order, start=1):

                medals = ["🥇", "🥈", "🥉"]
                medal = medals[rank - 1] if rank <= 3 else "▪️"

                st.write(f"{medal} {rank}. {person}")

            st.markdown("**ثبت انجام کار و تعداد دفعات**")

            for person in PEOPLE:

                count = int(task_counts.get(person, 0))

                checkbox_key = f"check_{task}_{person}"

                st.checkbox(
                    f"{person} · انجام‌شده: {count} بار",
                    key=checkbox_key,
                    on_change=register_task,
                    args=(task, person),
                )


# -------------------- Footer --------------------
st.markdown("---")

left, right = st.columns([2, 1])

with left:
    st.caption(
        "اطلاعات در دیتابیس آنلاین ذخیره می‌شود و از همه دستگاه‌ها قابل مشاهده است."
    )

with right:
    if st.button("🔄 تازه‌سازی اطلاعات", use_container_width=True):
        st.rerun()


# -------------------- Reset --------------------
with st.expander("⚠️ بازنشانی همه نوبت‌ها"):

    st.warning(
        "با این کار ترتیب نوبت‌ها به حالت اول برمی‌گردد "
        "و شمارنده تمام افراد برای همه کارها صفر می‌شود."
    )

    confirm_reset = st.checkbox(
        "بازنشانی همه شش کار را تأیید می‌کنم",
        key="confirm_reset"
    )

    if st.button(
        "بازنشانی نوبت‌ها",
        disabled=not confirm_reset
    ):

        try:
            reset_all(supabase)

            st.success(
                "نوبت‌ها بازنشانی شدند و شمارنده‌ها صفر شدند."
            )

            st.rerun()

        except Exception as e:
            st.error(f"بازنشانی انجام نشد: {e}")
