# ============================================================
# 🤖 ربات فروشگاهی + آگهی‌های دیواری + کاریابی (نسخه نهایی)
# ============================================================

from rubka import Robot, Message
from rubka.keypad import ChatKeypadBuilder
import re
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import json
import threading
from flask import Flask, request, jsonify
import requests
import logging
import uuid

logging.basicConfig(level=logging.INFO)

# ============================================================
# 📦 فایل‌های ذخیره‌سازی
# ============================================================

PRODUCTS_FILE = "products.json"
DATA_FILE = "data.json"
ADS_FILE = "ads.json"
CATEGORIES_FILE = "categories.json"

# ============================================================
# 📦 مدیریت داده‌های پایدار
# ============================================================

def load_data():
    default_data = {
        "invoice_counter": 0,
        "customer_counter": 3000,
        "customer_codes": {},
        "customer_debts": {},
        "last_invoice_for_admin": {}
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data.setdefault("invoice_counter", 0)
                data.setdefault("customer_counter", 3000)
                data.setdefault("customer_codes", {})
                data.setdefault("customer_debts", {})
                data.setdefault("last_invoice_for_admin", {})
                return data
        except:
            return default_data
    return default_data

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()
invoice_counter = data.get("invoice_counter", 0)
customer_counter = data.get("customer_counter", 3000)
customer_codes = data.get("customer_codes", {})
customer_debts = data.get("customer_debts", {})
last_invoice_for_admin = data.get("last_invoice_for_admin", {})

# ============================================================
# 🔗 توابع ارتباط با وب‌هوک گوگل‌شیت
# ============================================================

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycby8J4Zi9s0GKM_-B8E8HKYDPwR9pEQAfOsk36FuL7cqY5vtATV8hMuepgvujwW8NgGTtQ/exec"

def call_webhook(action, payload={}):
    payload["action"] = action
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                return result
        return None
    except Exception as e:
        logging.error(f"❌ خطا در ارتباط با وب‌هوک: {e}")
        return None

# ============================================================
# 📦 توابع تولید شماره فاکتور و کد مشتری
# ============================================================

def generate_invoice_number():
    global invoice_counter, data
    result = call_webhook("get_next_invoice")
    if result and result.get("invoice_number"):
        invoice_counter += 1
        data["invoice_counter"] = invoice_counter
        save_data(data)
        return result["invoice_number"]
    else:
        invoice_counter += 1
        data["invoice_counter"] = invoice_counter
        save_data(data)
        now = datetime.now()
        return f"M_{now.strftime('%Y%m%d')}{invoice_counter:04d}"

def get_or_create_customer_code(phone):
    global customer_counter, customer_codes, data
    phone = phone.replace(' ', '').replace('-', '')
    result = call_webhook("get_or_create_customer", {"phone": phone})
    if result and result.get("customer_code"):
        code = result["customer_code"]
        customer_codes[phone] = code
        data["customer_codes"] = customer_codes
        save_data(data)
        return code
    else:
        if phone in customer_codes:
            return customer_codes[phone]
        customer_counter += 1
        code = f"MO_{customer_counter}"
        customer_codes[phone] = code
        data["customer_counter"] = customer_counter
        data["customer_codes"] = customer_codes
        save_data(data)
        return code

def get_customer_debt_from_sheet(customer_code):
    result = call_webhook("get_customer_debt", {"customer_code": customer_code})
    if result and "debt" in result:
        return int(result["debt"])
    return None

# ============================================================
# 📦 ذخیره‌سازی محصولات
# ============================================================

def load_products():
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_products(products):
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

all_products = load_products()
for p in all_products:
    if "category" not in p:
        p["category"] = "متفرقه"

# ============================================================
# 📦 مدیریت آگهی‌های کاربران
# ============================================================

def load_ads():
    if os.path.exists(ADS_FILE):
        with open(ADS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_ads(ads):
    with open(ADS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ads, f, ensure_ascii=False, indent=2)

all_ads = load_ads()

# ============================================================
# 📂 مدیریت دسته‌بندی‌ها (برای آگهی‌ها)
# ============================================================

def load_categories():
    default_categories = {
        "کالا": {
            "املاک": ["آپارتمان", "ویلا", "زمین", "کلنگی"],
            "وسایل نقلیه": ["خودرو", "موتورسیکلت", "قطعات یدکی"],
            "دیجیتال": ["موبایل", "تبلت", "لپ‌تاپ", "لوازم جانبی"],
            "خانه و آشپزخانه": ["مبل", "یخچال", "ظروف", "لوازم تزیینی"],
            "خدمات": ["تعمیرات", "آموزش", "حمل و نقل"]
        },
        "استخدام": {
            "فنی و مهندسی": ["برنامه‌نویس", "مهندس عمران", "مهندس برق", "تکنسین"],
            "خدمات و پشتیبانی": ["منشی", "پشتیبانی مشتری", "نگهبان", "خدمات نظافتی"],
            "آموزش و پرورش": ["معلم", "مربی", "استاد دانشگاه"],
            "بهداشت و درمان": ["پزشک", "پرستار", "داروساز"],
            "کشاورزی و دامداری": ["کشاورز", "دامدار", "باغبان"],
            "صنعت و تولید": ["کارگر خط تولید", "جوشکار", "اپراتور"],
            "بازرگانی و فروش": ["فروشنده", "بازاریاب", "نماینده فروش"]
        }
    }
    if os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        with open(CATEGORIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_categories, f, ensure_ascii=False, indent=2)
        return default_categories

CATEGORIES = load_categories()

def get_main_categories():
    return list(CATEGORIES.keys())

def get_sub_categories(main_cat):
    return CATEGORIES.get(main_cat, {})

def get_leaf_categories(main_cat, sub_cat):
    return CATEGORIES.get(main_cat, {}).get(sub_cat, [])

# ============================================================
# 🤖 تنظیمات اولیه
# ============================================================

TOKEN = os.environ.get("TOKEN", "")
BOT_USERNAME = "FroghiShopBot"
ADMIN_CHAT_ID = "b0HWCJJ0xHE0e4e078b6c5228504866a"

# ============================================================
# 🔍 توابع کمکی
# ============================================================

def convert_persian_number(text):
    mapping = {'۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
               '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9'}
    for p, e in mapping.items():
        text = text.replace(p, e)
    return text

def normalize_phone(phone):
    phone = str(phone).replace(' ', '').replace('-', '')
    if phone.startswith('+98'):
        phone = '0' + phone[3:]
    elif phone.startswith('0098'):
        phone = '0' + phone[4:]
    elif phone.startswith('98') and len(phone) == 12:
        phone = '0' + phone[2:]
    elif phone.startswith('9') and len(phone) == 10:
        phone = '0' + phone
    return phone

def detect_category(text):
    text = text.lower()
    if "مردانه" in text or "آقایان" in text:
        return "مردانه"
    elif "زنانه" in text or "بانوان" in text:
        return "زنانه"
    elif "میانه" in text:
        return "میانه"
    elif "بچگانه" in text or "بچه" in text or "کودک" in text:
        return "بچگانه"
    elif "دخترانه" in text or "دختر" in text:
        return "دخترانه"
    elif "پسرانه" in text or "پسر" in text:
        return "پسرانه"
    else:
        return "متفرقه"

def detect_product(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        return None
    name = lines[0]
    pair_count = 0
    pair_match = re.search(r'([\d۰-۹]+)\s*(?:زوجی|جفت)', text)
    if pair_match:
        pair_count = int(convert_persian_number(pair_match.group(1))) or 0
    text_clean = re.sub(r'[٬,/]', '', text)
    persian_numbers = re.findall(r'([\u06F0-\u06F9]{3,})', text_clean)
    all_numbers = []
    for n in persian_numbers:
        all_numbers.append(int(convert_persian_number(n)))
    english_numbers = re.findall(r'(\d{3,})', text_clean)
    for n in english_numbers:
        all_numbers.append(int(n))
    if not all_numbers:
        return None
    price = max(all_numbers)
    if not name or price == 0:
        return None
    category = detect_category(text)
    return {'name': name, 'price': price, 'pairCount': pair_count, 'category': category}

def extract_amount(text):
    text_clean = re.sub(r'[٬,/]', '', text)
    numbers = re.findall(r'(\d+)', text_clean)
    if numbers:
        amounts = [int(n) for n in numbers if len(n) >= 4]
        if amounts:
            return max(amounts)
    return None

def format_price(num):
    if not num:
        return "0"
    if num < 0:
        return f"-{abs(num):,}".replace(',', '٬')
    return f"{num:,}".replace(',', '٬')

def add_to_cart(user_id, product, quantity):
    cart = get_cart(user_id)
    if len(cart['items']) >= 15:
        return False, "❌ حداکثر ۱۵ محصول قابل سفارش است!"
    for item in cart['items']:
        if item['name'] == product['name']:
            item['quantity'] += quantity
            return True, f"✅ تعداد {product['name']} افزایش یافت!"
    cart['items'].append({
        'name': product['name'], 'price': product['price'],
        'quantity': quantity, 'pairCount': product.get('pairCount', 0)
    })
    return True, f"✅ {product['name']} به سبد خرید اضافه شد!"

# ============================================================
# 📦 حافظه موقت
# ============================================================

carts = {}

def get_cart(user_id):
    if user_id not in carts:
        carts[user_id] = {
            'items': [], 'step': 'idle', 'selected_product': None,
            'customer': {}, 'search_query': '',
            'current_page': 1, 'current_category': 'همه محصولات',
            'ad_step': None,
            'ad_data': {},
            'ad_type': None,
            'ad_category_path': '',
            'ad_images': []
        }
    return carts[user_id]

# ============================================================
# 🎨 دکوریشن و نمایش (منوی اصلی)
# ============================================================

async def show_main_menu(message, user_id):
    keypad_builder = ChatKeypadBuilder()
    keypad_builder.row(
        ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات"),
        ChatKeypadBuilder().button(id="show_ads", text="📢 مشاهده آگهی‌ها"),
    )
    keypad_builder.row(
        ChatKeypadBuilder().button(id="new_ad", text="➕ ثبت آگهی جدید"),
        ChatKeypadBuilder().button(id="search", text="🔍 جستجو"),
    )
    keypad_builder.row(
        ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید"),
        ChatKeypadBuilder().button(id="help", text="📋 راهنما"),
    )
    await message.reply_keypad("🏠 **منوی اصلی فروشگاه و آگهی‌ها:**", keypad_builder.build())

# ============================================================
# 🗂️ نمایش دسته‌بندی‌های محصولات (برای خرید) - ثابت مانند کد قدیمی
# ============================================================

async def show_categories_menu(message, user_id, bot):
    keypad = ChatKeypadBuilder()
    keypad.row(
        ChatKeypadBuilder().button(id="cat_همه محصولات", text="📦 همه محصولات"),
    )
    keypad.row(
        ChatKeypadBuilder().button(id="cat_مردانه", text="👞 مردانه"),
        ChatKeypadBuilder().button(id="cat_زنانه", text="👠 زنانه"),
    )
    keypad.row(
        ChatKeypadBuilder().button(id="cat_میانه", text="👟 میانه"),
        ChatKeypadBuilder().button(id="cat_بچگانه", text="🧒 بچگانه"),
    )
    keypad.row(
        ChatKeypadBuilder().button(id="cat_دخترانه", text="👧 دخترانه"),
        ChatKeypadBuilder().button(id="cat_پسرانه", text="👦 پسرانه"),
    )
    keypad.row(
        ChatKeypadBuilder().button(id="cat_متفرقه", text="📦 متفرقه"),
    )
    keypad.row(ChatKeypadBuilder().button(id="back_to_menu", text="🔙 بازگشت"))
    await message.reply_keypad("🗂️ **دسته‌بندی محصولات را انتخاب کنید:**", keypad.build())

async def show_products_page(message, user_id, bot):
    cart = get_cart(user_id)
    category = cart.get('current_category', 'همه محصولات')
    page = cart.get('current_page', 1)
    per_page = 8

    if category == 'همه محصولات':
        filtered = all_products
    else:
        filtered = [p for p in all_products if p.get('category', 'متفرقه') == category]

    total = len(filtered)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages
    cart['current_page'] = page

    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]

    if not page_items:
        await message.reply("❌ هیچ محصولی در این دسته یافت نشد.")
        return

    keypad = ChatKeypadBuilder()
    for product in page_items:
        btn_text = f"{product['name'][:20]} - {format_price(product['price'])} تومان"
        keypad.row(ChatKeypadBuilder().button(id=f"select_{product['name']}", text=btn_text))

    # دکمه‌های صفحه‌بندی
    nav_row = []
    if page > 1:
        nav_row.append(ChatKeypadBuilder().button(id="prev_page", text="⬅️ قبلی"))
    if page < total_pages:
        nav_row.append(ChatKeypadBuilder().button(id="next_page", text="بعدی ➡️"))
    if nav_row:
        keypad.row(*nav_row)

    keypad.row(
        ChatKeypadBuilder().button(id="back_to_categories", text="🔙 دسته‌بندی"),
        ChatKeypadBuilder().button(id="back_to_menu", text="🏠 منو")
    )
    await message.reply_keypad(f"📦 **{category}** (صفحه {page} از {total_pages})", keypad.build())

# ============================================================
# 🛒 نمایش سبد خرید
# ============================================================

async def show_cart_internal(bot, message, user_id):
    cart = get_cart(user_id)
    if not cart['items']:
        await message.reply("🛒 سبد خرید شما خالی است.")
        return

    text = "🛒 **سبد خرید شما:**\n\n"
    total = 0
    for i, item in enumerate(cart['items'], 1):
        subtotal = item['price'] * item['quantity'] * item.get('pairCount', 1)
        total += subtotal
        text += f"{i}. {item['name']} × {item['quantity']} کارتن = {format_price(subtotal)} تومان\n"

    text += f"\n💰 **جمع کل: {format_price(total)} تومان**"

    keypad = ChatKeypadBuilder()
    for item in cart['items']:
        keypad.row(ChatKeypadBuilder().button(id=f"remove_{item['name']}", text=f"🗑️ حذف {item['name'][:15]}"))
    keypad.row(
        ChatKeypadBuilder().button(id="clear_cart", text="🗑️ خالی کردن"),
        ChatKeypadBuilder().button(id="checkout", text="✅ نهایی‌سازی")
    )
    keypad.row(ChatKeypadBuilder().button(id="back_to_menu", text="🔙 بازگشت"))
    await message.reply_keypad(text, keypad.build())

# ============================================================
# 🔍 نمایش نتایج جستجو
# ============================================================

async def show_search_results(message, user_id, bot):
    cart = get_cart(user_id)
    query = cart.get('search_query', '').strip().lower()
    if not query:
        await message.reply("❌ عبارت جستجو خالی است.")
        return

    results = [p for p in all_products if query in p['name'].lower()]
    if not results:
        await message.reply("❌ هیچ نتیجه‌ای یافت نشد.")
        return

    keypad = ChatKeypadBuilder()
    for product in results[:10]:
        btn_text = f"{product['name'][:20]} - {format_price(product['price'])} تومان"
        keypad.row(ChatKeypadBuilder().button(id=f"select_{product['name']}", text=btn_text))
    keypad.row(
        ChatKeypadBuilder().button(id="new_search", text="🔍 جستجوی جدید"),
        ChatKeypadBuilder().button(id="back_to_menu", text="🏠 منو")
    )
    await message.reply_keypad(f"🔍 **نتایج جستجو برای '{query}':**", keypad.build())

# ============================================================
# 🗂️ نمایش دسته‌بندی‌های آگهی (برای مشاهده)
# ============================================================

async def show_ad_categories_for_view(message, user_id):
    keypad = ChatKeypadBuilder()
    for main_cat in get_main_categories():
        keypad.row(ChatKeypadBuilder().button(id=f"view_ad_main_{main_cat}", text=main_cat))
    keypad.row(ChatKeypadBuilder().button(id="back_to_menu", text="🔙 بازگشت"))
    await message.reply_keypad("🗂️ **دسته‌بندی آگهی‌ها را انتخاب کنید:**", keypad.build())

async def show_ad_sub_categories(message, main_cat):
    subs = get_sub_categories(main_cat)
    keypad = ChatKeypadBuilder()
    for sub_cat in subs.keys():
        keypad.row(ChatKeypadBuilder().button(id=f"view_ad_sub_{main_cat}_{sub_cat}", text=sub_cat))
    keypad.row(ChatKeypadBuilder().button(id="back_to_ad_main", text="🔙 بازگشت"))
    await message.reply_keypad(f"زیردسته‌های {main_cat}:", keypad.build())

async def show_ad_leaf_categories(message, main_cat, sub_cat):
    leaves = get_leaf_categories(main_cat, sub_cat)
    keypad = ChatKeypadBuilder()
    for leaf in leaves:
        keypad.row(ChatKeypadBuilder().button(id=f"view_ad_leaf_{main_cat}_{sub_cat}_{leaf}", text=leaf))
    keypad.row(ChatKeypadBuilder().button(id=f"back_to_ad_sub_{main_cat}", text="🔙 بازگشت"))
    await message.reply_keypad(f"دسته‌های {sub_cat}:", keypad.build())

async def show_ads_by_category(message, user_id, category_path):
    cart = get_cart(user_id)
    cart['ad_category_path'] = category_path
    ads = [ad for ad in all_ads if ad.get('category_path') == category_path and ad.get('status') == 'approved']
    if not ads:
        await message.reply("❌ هیچ آگهی تایید شده‌ای در این دسته یافت نشد.")
        return
    keypad = ChatKeypadBuilder()
    for ad in ads:
        title = ad.get('title', 'بدون عنوان')[:20]
        keypad.row(ChatKeypadBuilder().button(id=f"view_ad_detail_{ad['id']}", text=title))
    keypad.row(ChatKeypadBuilder().button(id="back_to_ad_main", text="🔙 بازگشت"))
    await message.reply_keypad(f"📋 {len(ads)} آگهی در این دسته:", keypad.build())

# ============================================================
# 🆕 نمایش جزئیات آگهی
# ============================================================

async def show_ad_detail(message, user_id, ad_id, bot):
    ad = next((a for a in all_ads if a['id'] == ad_id), None)
    if not ad or ad['status'] != 'approved':
        await message.reply("❌ آگهی یافت نشد یا تایید نشده است.")
        return
    text = f"📢 **{ad.get('title', 'بدون عنوان')}**\n"
    text += f"🗂️ دسته: {ad.get('category_path', 'نامشخص')}\n"
    text += f"📝 توضیحات: {ad.get('description', '')}\n"
    if ad.get('price'):
        text += f"💰 قیمت: {format_price(ad['price'])} تومان\n"
    text += f"📅 تاریخ ثبت: {ad.get('created_at', '')[:10]}\n"
    if ad.get('contact_phone'):
        text += f"📞 تماس: {ad['contact_phone']}\n"
    else:
        text += f"📞 برای تماس با فروشنده، از طریق ربات پیام دهید.\n"

    keypad = ChatKeypadBuilder()
    if ad.get('type') == 'product':
        keypad.row(ChatKeypadBuilder().button(id=f"order_ad_{ad['id']}", text="🛒 سفارش این کالا"))
    elif ad.get('type') == 'job':
        keypad.row(ChatKeypadBuilder().button(id=f"contact_ad_{ad['id']}", text="📩 تماس با کارفرما"))
    keypad.row(ChatKeypadBuilder().button(id="back_to_ads_list", text="🔙 بازگشت به لیست"))
    await message.reply_keypad(text, keypad.build())

# ============================================================
# 📝 جریان ثبت آگهی
# ============================================================

async def start_new_ad(message, user_id):
    cart = get_cart(user_id)
    cart['ad_step'] = 'choose_type'
    cart['ad_data'] = {}
    cart['ad_images'] = []
    keypad = ChatKeypadBuilder()
    keypad.row(
        ChatKeypadBuilder().button(id="ad_type_product", text="📦 کالا"),
        ChatKeypadBuilder().button(id="ad_type_job", text="💼 استخدام")
    )
    keypad.row(ChatKeypadBuilder().button(id="back_to_menu", text="🔙 انصراف"))
    await message.reply_keypad("📢 **ثبت آگهی جدید**\nلطفاً نوع آگهی را انتخاب کنید:", keypad.build())

async def show_ad_category_selection(message, user_id, step='main'):
    cart = get_cart(user_id)
    if step == 'main':
        keypad = ChatKeypadBuilder()
        for main_cat in get_main_categories():
            keypad.row(ChatKeypadBuilder().button(id=f"ad_cat_main_{main_cat}", text=main_cat))
        keypad.row(ChatKeypadBuilder().button(id="back_to_menu", text="🔙 انصراف"))
        await message.reply_keypad("🗂️ **دسته‌بندی اصلی را انتخاب کنید:**", keypad.build())
    elif step == 'sub':
        main_cat = cart['ad_data'].get('main_category')
        if not main_cat:
            await message.reply("❌ خطا! دوباره شروع کنید.")
            return
        subs = get_sub_categories(main_cat)
        keypad = ChatKeypadBuilder()
        for sub_cat in subs.keys():
            keypad.row(ChatKeypadBuilder().button(id=f"ad_cat_sub_{main_cat}_{sub_cat}", text=sub_cat))
        keypad.row(ChatKeypadBuilder().button(id="back_to_ad_main_cat", text="🔙 بازگشت"))
        await message.reply_keypad(f"زیردسته‌های {main_cat}:", keypad.build())
    elif step == 'leaf':
        main_cat = cart['ad_data'].get('main_category')
        sub_cat = cart['ad_data'].get('sub_category')
        if not main_cat or not sub_cat:
            await message.reply("❌ خطا! دوباره شروع کنید.")
            return
        leaves = get_leaf_categories(main_cat, sub_cat)
        if not leaves:
            cart['ad_data']['category_path'] = f"{main_cat}/{sub_cat}"
            cart['ad_step'] = 'enter_title'
            await message.reply("📝 **عنوان آگهی** را وارد کنید:")
            return
        keypad = ChatKeypadBuilder()
        for leaf in leaves:
            keypad.row(ChatKeypadBuilder().button(id=f"ad_cat_leaf_{main_cat}_{sub_cat}_{leaf}", text=leaf))
        keypad.row(ChatKeypadBuilder().button(id=f"back_to_ad_sub_cat_{main_cat}", text="🔙 بازگشت"))
        await message.reply_keypad(f"دسته‌های {sub_cat}:", keypad.build())

# ============================================================
# 🖼️ تولید فاکتور
# ============================================================

def persian_text(text):
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except:
        return text

def create_invoice_image(customer, items, total, previous_debt, invoice_number, customer_code):
    margin = 80
    width = 3200
    row_height = 120
    header_height = 280
    customer_height = 200
    table_header_height = 100
    footer_height = 280
    height = margin + header_height + customer_height + table_header_height + (len(items) * row_height) + 200 + footer_height + margin
    if previous_debt > 0:
        height += 100
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([(margin, margin), (width - margin, height - margin)], outline=(25, 70, 160), width=6)
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/tahoma.ttf"]
    font_found = None
    for path in font_paths:
        if os.path.exists(path):
            font_found = path
            break
    if font_found:
        try:
            font_title = ImageFont.truetype(font_found, 76)
            font_header = ImageFont.truetype(font_found, 56)
            font_normal = ImageFont.truetype(font_found, 46)
            font_bold = ImageFont.truetype(font_found, 50)
            font_footer = ImageFont.truetype(font_found, 60)
        except:
            font_title = ImageFont.load_default(); font_header = ImageFont.load_default(); font_normal = ImageFont.load_default(); font_bold = ImageFont.load_default(); font_footer = ImageFont.load_default()
    else:
        font_title = ImageFont.load_default(); font_header = ImageFont.load_default(); font_normal = ImageFont.load_default(); font_bold = ImageFont.load_default(); font_footer = ImageFont.load_default()
    y = margin + 40
    right_x = width - margin - 40
    left_x = margin + 40
    draw.text((width // 2, y), persian_text("فاکتور فروش"), fill=(25, 70, 160), font=font_title, anchor="mm")
    draw.text((right_x, y), persian_text(f"شماره: {invoice_number}"), fill=(0, 0, 0), font=font_header, anchor="rm")
    draw.text((right_x, y + 100), persian_text(f"کد مشتری: {customer_code}"), fill=(25, 70, 160), font=font_header, anchor="rm")
    draw.text((right_x, y + 200), persian_text(f"تاریخ: {datetime.now().strftime('%Y/%m/%d')}"), fill=(100, 100, 100), font=font_header, anchor="rm")
    y += 280
    draw.rectangle([(margin + 20, y), (width - margin - 20, y + 200)], fill=(245, 248, 250), outline=(200, 210, 220), width=2)
    draw.text((right_x, y + 40), persian_text(f"مشتری: {customer.get('name', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal, anchor="rm")
    draw.text((right_x, y + 105), persian_text(f"تلفن: {customer.get('phone', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal, anchor="rm")
    draw.text((right_x, y + 170), persian_text(f"آدرس: {customer.get('address', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal, anchor="rm")
    draw.text((left_x, y + 40), persian_text(f"باربری: {customer.get('shipping', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal, anchor="lm")
    y += 250
    table_left = margin + 20
    table_right = width - margin - 20
    col_widths = [100, 1000, 200, 200, 450, 600]
    col_centers = []
    current = table_right
    for w in col_widths:
        col_centers.append(current - w // 2)
        current -= w
    draw.rectangle([(table_left, y), (table_right, y + 100)], fill=(25, 70, 160))
    headers = ["ردیف", "نام مدل", "کارتن", "جفت", "قیمت هر جفت", "مبلغ کل"]
    for i, h in enumerate(headers):
        draw.text((col_centers[i], y + 50), persian_text(h), fill=(255, 255, 255), font=font_bold, anchor="mm")
    y += 100
    for i, item in enumerate(items, 1):
        if i % 2 == 0:
            draw.rectangle([(table_left, y), (table_right, y + 110)], fill=(248, 250, 252))
        draw.text((col_centers[0], y + 55), str(i), fill=(0, 0, 0), font=font_normal, anchor="mm")
        draw.text((col_centers[1], y + 55), persian_text(item['name'][:50]), fill=(0, 0, 0), font=font_normal, anchor="mm")
        draw.text((col_centers[2], y + 55), str(item['quantity']), fill=(0, 0, 0), font=font_normal, anchor="mm")
        draw.text((col_centers[3], y + 55), str(item['pairCount']), fill=(0, 0, 0), font=font_normal, anchor="mm")
        draw.text((col_centers[4], y + 55), format_price(item['price_per_pair']), fill=(0, 0, 0), font=font_normal, anchor="mm")
        draw.text((col_centers[5], y + 55), format_price(item['subtotal']), fill=(0, 0, 0), font=font_normal, anchor="mm")
        y += 110
    draw.line([(table_left, y), (table_right, y)], fill=(200, 210, 220), width=4)
    y += 80
    draw.text((right_x, y), persian_text(f"جمع سفارش جدید: {format_price(total)} تومان"), fill=(25, 70, 160), font=font_bold, anchor="rm")
    y += 110
    if previous_debt != 0:
        if previous_debt < 0:
            draw.text((right_x, y), persian_text(f"بستانکاری قبلی: {format_price(previous_debt)} تومان"), fill=(200, 50, 50), font=font_bold, anchor="rm")
        else:
            draw.text((right_x, y), persian_text(f"بدهی قبلی: {format_price(previous_debt)} تومان"), fill=(200, 50, 50), font=font_bold, anchor="rm")
        y += 110
        draw.text((right_x, y), persian_text(f"مبلغ قابل پرداخت: {format_price(total + previous_debt)} تومان"), fill=(0, 150, 0), font=font_bold, anchor="rm")
    else:
        draw.text((right_x, y), persian_text(f"مبلغ قابل پرداخت: {format_price(total)} تومان"), fill=(0, 150, 0), font=font_bold, anchor="rm")
    y += 200
    draw.text((width // 2, y), persian_text("از اعتماد شما سپاسگزاریم!"), fill=(150, 150, 150), font=font_footer, anchor="mm")
    filename = f"invoices/invoice_{invoice_number}.png"
    os.makedirs("invoices", exist_ok=True)
    image.save(filename, "PNG", quality=100, dpi=(300, 300))
    return filename

# ============================================================
# 💾 نهایی‌سازی سفارش
# ============================================================

def ثبت_سفارش_در_شیت(customer, items, total, invoice_number, customer_code):
    try:
        payload = {
            "action": "register", "timestamp": datetime.now().isoformat(),
            "invoice_number": invoice_number, "customer_code": customer_code,
            "customer_name": customer.get('name', ''), "customer_phone": customer.get('phone', ''),
            "customer_address": customer.get('address', ''), "customer_shipping": customer.get('shipping', ''),
            "total": total, "items": items
        }
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"✅ سفارش {invoice_number} در گوگل‌شیت ثبت شد.")
                return True
        return False
    except Exception as e:
        print(f"❌ خطا در ثبت سفارش: {e}")
        return False

def extract_payment_info(text):
    amount = extract_amount(text)
    if not amount:
        return None, None, None
    text_clean = re.sub(r'[\d,]+', '', text)
    text_clean = re.sub(r'(تایید|شد|واریز|به|بانک|صاحب|حساب|:|ریال|تومان)', '', text_clean, flags=re.IGNORECASE)
    text_clean = re.sub(r'\s+', ' ', text_clean).strip()
    words = text_clean.split()
    if len(words) >= 2:
        bank = words[0]
        holder = ' '.join(words[1:])
    elif len(words) == 1:
        bank = words[0]
        holder = ''
    else:
        bank = ''
        holder = ''
    return bank, holder, amount

def به‌روزرسانی_واریزی_در_شیت(invoice_number, payment_amount, bank_name="", account_holder=""):
    try:
        payload = {
            "action": "update_payment",
            "invoice_number": invoice_number,
            "payment_amount": payment_amount,
            "bank_name": bank_name,
            "account_holder": account_holder
        }
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"✅ واریزی {invoice_number} ثبت شد.")
                msg = result.get("message", "")
                if "تومان" not in msg or "فاکتور" not in msg:
                    formatted_amount = f"{payment_amount:,}".replace(",", "٬")
                    msg = f"واریزی {formatted_amount} تومان برای فاکتور {invoice_number} ثبت شد. بانک: {bank_name}، صاحب حساب: {account_holder}"
                return True, msg
        return False, f"❌ خطا: {response.text}"
    except Exception as e:
        return False, f"❌ خطا: {e}"

async def finalize_order(message: Message, user_id: str, bot: Robot):
    global customer_debts, last_invoice_for_admin, data
    cart = get_cart(user_id)
    customer = cart['customer']
    if len(cart['items']) == 0:
        await message.reply("❌ سبد خرید خالی است!")
        return
    phone = normalize_phone(customer.get('phone', ''))
    customer['phone'] = phone
    if len(phone.replace(' ', '').replace('-', '')) < 11:
        await message.reply("❌ شماره تماس معتبر نیست. حداقل ۱۱ رقم وارد کنید.")
        return
    customer_code = get_or_create_customer_code(phone)

    sheet_debt = get_customer_debt_from_sheet(customer_code)
    if sheet_debt is not None:
        previous_debt = sheet_debt
        customer_debts[user_id] = previous_debt
        data["customer_debts"] = customer_debts
        save_data(data)
    else:
        previous_debt = customer_debts.get(user_id, 0)

    total = 0
    items_list = []
    for item in cart['items']:
        pair_count = item.get('pairCount', 1)
        total_pairs = item.get('quantity', 0) * pair_count
        subtotal = item['price'] * pair_count * item['quantity']
        total += subtotal
        items_list.append({
            'name': item['name'], 'quantity': item['quantity'],
            'pairCount': total_pairs, 'price_per_pair': item['price'],
            'subtotal': subtotal
        })

    total_payable = previous_debt + total
    invoice_number = generate_invoice_number()

    try:
        image_path = create_invoice_image(customer, items_list, total, previous_debt, invoice_number, customer_code)
        await bot.send_photo(chat_id=message.chat_id, photo=image_path, caption=f"🧾 فاکتور شماره: {invoice_number}\n🆔 کد مشتری: {customer_code}")
        if os.path.exists(image_path):
            os.remove(image_path)
    except Exception as e:
        print(f"⚠️ خطا در تولید فاکتور: {e}")
        await message.reply("⚠️ خطا در تولید فاکتور، لطفاً دوباره تلاش کنید.")
        return

    try:
        image_path = create_invoice_image(customer, items_list, total, previous_debt, invoice_number, customer_code)
        admin_msg = await bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=image_path, caption=f"📬 فاکتور جدید از مشتری: {customer.get('name', 'نامشخص')}\n🆔 کد مشتری: {customer_code}\n💳 بدهی فعلی: {format_price(total_payable)} تومان")
        if os.path.exists(image_path):
            os.remove(image_path)
        last_invoice_for_admin[user_id] = {
            'message_id': admin_msg.message_id,
            'chat_id': ADMIN_CHAT_ID,
            'user_name': customer.get('name', 'نامشخص'),
            'total_payable': total_payable,
            'invoice_number': invoice_number,
            'customer_code': customer_code
        }
        data["last_invoice_for_admin"] = last_invoice_for_admin
        save_data(data)
    except Exception as e:
        print(f"⚠️ خطا در ارسال فاکتور به حسابدار: {e}")

    ثبت_سفارش_در_شیت(customer, items_list, total, invoice_number, customer_code)
    customer_debts[user_id] = total_payable
    data["customer_debts"] = customer_debts
    save_data(data)

    cart['items'] = []
    cart['customer'] = {}
    cart['step'] = 'idle'
    await show_main_menu(message, user_id)

# ============================================================
# 📤 ارسال لینک به کانال
# ============================================================

async def send_link_to_channel(chat_id, product):
    bot_link = f"https://rubika.ir/{BOT_USERNAME}"
    button_text = "➕ سفارش این مدل"
    text = (
        f"📦 **{product['name']}**\n"
        f"💰 قیمت هر جفت: {format_price(product['price'])} تومان\n"
        f"📦 تعداد جفت: {product.get('pairCount', 'نامشخص')}\n\n"
        f"{button_text}"
    )
    start_index = text.index(button_text)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        meta_data={
            'meta_data_parts': [{
                'type': 'Link',
                'from_index': start_index,
                'length': len(button_text),
                'link_url': bot_link
            }]
        }
    )

# ============================================================
# 🤖 هندلر پیام‌ها
# ============================================================

bot = Robot(token=TOKEN)

@bot.on_message()
async def handle_message(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.author_guid
    text = message.text if message.text else ''
    cart = get_cart(user_id)

    # ========== بخش کانال (ادمین) - خواندن محصولات ==========
    if chat_id.startswith('c0'):
        product = detect_product(text)
        if not product:
            return
        found = False
        for i, p in enumerate(all_products):
            if p['name'] == product['name']:
                all_products[i]['price'] = product['price']
                all_products[i]['pairCount'] = product.get('pairCount', 0)
                all_products[i]['category'] = product.get('category', 'متفرقه')
                save_products(all_products)
                found = True
                break
        if not found:
            all_products.append(product)
            save_products(all_products)
        await send_link_to_channel(chat_id, product)
        return

    # ========== بخش کاربران عادی ==========
    if chat_id.startswith('b0'):
        # ========== /start ==========
        if text == '/start' or text == 'start':
            await show_main_menu(message, user_id)
            return

        # ============================================================
        # 🆕 بخش ثبت آگهی (باید قبل از سایر stepها بررسی شود)
        # ============================================================
        if cart.get('ad_step'):
            # مرحله دریافت عنوان
            if cart['ad_step'] == 'enter_title':
                if not text.strip():
                    await message.reply("❌ عنوان نمی‌تواند خالی باشد. لطفاً وارد کنید:")
                    return
                cart['ad_data']['title'] = text.strip()
                cart['ad_step'] = 'enter_description'
                await message.reply("📝 **توضیحات آگهی** را وارد کنید (می‌توانید خالی بگذارید):")
                return

            if cart['ad_step'] == 'enter_description':
                cart['ad_data']['description'] = text.strip()
                cart['ad_step'] = 'enter_price'
                await message.reply("💰 **قیمت** را به تومان وارد کنید (اگر نامشخص است، ۰ وارد کنید):")
                return

            if cart['ad_step'] == 'enter_price':
                try:
                    price = int(convert_persian_number(text))
                    if price < 0:
                        await message.reply("❌ قیمت نمی‌تواند منفی باشد. دوباره وارد کنید:")
                        return
                    cart['ad_data']['price'] = price
                except:
                    await message.reply("❌ لطفاً یک عدد معتبر وارد کنید:")
                    return
                cart['ad_step'] = 'enter_pair_count'
                await message.reply("📦 **تعداد جفت** (برای کالاها) را وارد کنید (برای استخدام ۰ وارد کنید):")
                return

            if cart['ad_step'] == 'enter_pair_count':
                try:
                    pair_count = int(convert_persian_number(text))
                    if pair_count < 0:
                        await message.reply("❌ عدد نمی‌تواند منفی باشد. دوباره وارد کنید:")
                        return
                    cart['ad_data']['pairCount'] = pair_count
                except:
                    await message.reply("❌ لطفاً یک عدد معتبر وارد کنید:")
                    return
                cart['ad_step'] = 'upload_photo'
                await message.reply("🖼️ **تصویر** آگهی را ارسال کنید (حداقل یک تصویر الزامی است).\nبرای ارسال، روی 📎 کلیک کنید و عکس را انتخاب کنید.")
                return

            if cart['ad_step'] == 'upload_photo':
                if text.strip() == 'پایان':
                    if not cart['ad_images']:
                        await message.reply("❌ حداقل یک تصویر باید ارسال کنید. لطفاً یک عکس ارسال کنید.")
                        return
                    cart['ad_step'] = 'confirm_ad'
                    ad_data = cart['ad_data']
                    summary = (
                        f"📋 **خلاصه آگهی:**\n"
                        f"نوع: {cart.get('ad_type', 'نامشخص')}\n"
                        f"دسته: {ad_data.get('category_path', 'نامشخص')}\n"
                        f"عنوان: {ad_data.get('title', '')}\n"
                        f"توضیحات: {ad_data.get('description', '')}\n"
                        f"قیمت: {format_price(ad_data.get('price', 0))} تومان\n"
                        f"تعداد جفت: {ad_data.get('pairCount', 0)}\n"
                        f"تعداد تصاویر: {len(cart['ad_images'])}\n\n"
                        f"آیا اطلاعات صحیح است؟ (برای تایید 'بله' و برای اصلاح 'خیر' بفرستید)"
                    )
                    await message.reply(summary)
                    return
                else:
                    await message.reply("❌ لطفاً یک تصویر ارسال کنید یا 'پایان' را بفرستید.")
                    return

            if cart['ad_step'] == 'confirm_ad':
                if text.strip() == 'بله':
                    ad_data = cart['ad_data']
                    if not ad_data.get('title') or not cart['ad_images']:
                        await message.reply("❌ اطلاعات ناقص! لطفاً دوباره ثبت آگهی را شروع کنید.")
                        cart['ad_step'] = None
                        return
                    ad = {
                        "id": len(all_ads) + 1,
                        "seller_id": user_id,
                        "type": cart.get('ad_type', 'product'),
                        "category_path": ad_data.get('category_path', ''),
                        "title": ad_data['title'],
                        "description": ad_data.get('description', ''),
                        "price": ad_data.get('price', 0),
                        "pairCount": ad_data.get('pairCount', 0),
                        "images": cart['ad_images'],
                        "contact_phone": ad_data.get('contact_phone', ''),
                        "status": "pending",
                        "created_at": datetime.now().isoformat()
                    }
                    all_ads.append(ad)
                    save_ads(all_ads)
                    cart['ad_step'] = None
                    cart['ad_data'] = {}
                    cart['ad_images'] = []
                    await bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"📢 **آگهی جدید در انتظار تایید:**\n"
                             f"👤 کاربر: {user_id}\n"
                             f"📌 عنوان: {ad['title']}\n"
                             f"🗂️ دسته: {ad['category_path']}\n"
                             f"💰 قیمت: {format_price(ad['price'])} تومان\n"
                             f"🆔 شناسه: {ad['id']}\n\n"
                             f"برای تایید: /approve_{ad['id']}\n"
                             f"برای رد: /reject_{ad['id']}"
                    )
                    await message.reply("✅ **آگهی شما با موفقیت ثبت شد و برای تایید به ادمین ارسال گردید.**")
                    await show_main_menu(message, user_id)
                    return
                elif text.strip() == 'خیر':
                    cart['ad_step'] = None
                    cart['ad_data'] = {}
                    cart['ad_images'] = []
                    await message.reply("❌ ثبت آگهی لغو شد. می‌توانید دوباره شروع کنید.")
                    await show_main_menu(message, user_id)
                    return
                else:
                    await message.reply("❌ لطفاً 'بله' یا 'خیر' را وارد کنید.")
                    return

        # ========== جستجو ==========
        if cart['step'] == 'searching':
            query = text.strip()
            if not query:
                await message.reply("❌ لطفاً یک نام معتبر وارد کنید.")
                return
            cart['search_query'] = query
            cart['step'] = 'idle'
            await show_search_results(message, user_id, bot)
            return

        # ========== انتخاب تعداد کارتن ==========
        if cart['step'] == 'waiting_quantity':
            try:
                quantity = int(convert_persian_number(text))
            except:
                await message.reply("❌ لطفاً یک عدد معتبر وارد کنید.")
                return
            if quantity < 1:
                await message.reply("❌ عدد باید بزرگتر از صفر باشد.")
                return
            product = cart.get('selected_product')
            if not product:
                await message.reply("❌ خطا! دوباره محصول را انتخاب کنید.")
                cart['step'] = 'idle'
                return
            success, msg = add_to_cart(user_id, product, quantity)
            await message.reply(msg)
            if success:
                cart['step'] = 'idle'
                cart['selected_product'] = None
                if cart.get('search_query'):
                    await show_search_results(message, user_id, bot)
                else:
                    await show_products_page(message, user_id, bot)
            return

        # ========== ثبت اطلاعات مشتری ==========
        if cart['step'] == 'waiting_customer_name':
            cart['customer']['name'] = text
            cart['step'] = 'waiting_customer_phone'
            await message.reply("📞 **شماره تماس** خود را وارد کنید (۱۱ رقم):")
            return
        if cart['step'] == 'waiting_customer_phone':
            phone = convert_persian_number(text).replace(' ', '').replace('-', '')
            if len(phone) < 11:
                await message.reply("❌ شماره تماس معتبر نیست. حداقل ۱۱ رقم وارد کنید.")
                return
            cart['customer']['phone'] = phone
            cart['step'] = 'waiting_customer_address'
            await message.reply("📍 **آدرس** خود را وارد کنید:")
            return
        if cart['step'] == 'waiting_customer_address':
            cart['customer']['address'] = text
            cart['step'] = 'waiting_customer_shipping'
            await message.reply("🚚 **باربری** مورد نظر را وارد کنید:")
            return
        if cart['step'] == 'waiting_customer_shipping':
            cart['customer']['shipping'] = text
            cart['step'] = 'idle'
            await finalize_order(message, user_id, bot)
            return

        # ========== بخش ادمین (حسابدار) ==========
        if chat_id == ADMIN_CHAT_ID:
            if text.startswith('/approve_'):
                ad_id = int(text.split('_')[1])
                ad = next((a for a in all_ads if a['id'] == ad_id), None)
                if not ad:
                    await message.reply("❌ آگهی یافت نشد.")
                    return
                if ad['status'] != 'pending':
                    await message.reply("❌ این آگهی قبلاً تایید یا رد شده است.")
                    return
                ad['status'] = 'approved'
                save_ads(all_ads)
                if ad['type'] == 'product':
                    category = detect_category(ad['title'])
                    new_product = {
                        'name': ad['title'],
                        'price': ad['price'],
                        'pairCount': ad.get('pairCount', 0),
                        'category': category
                    }
                    all_products.append(new_product)
                    save_products(all_products)
                try:
                    await bot.send_message(
                        chat_id=ad['seller_id'],
                        text=f"✅ **آگهی شما با موفقیت تایید شد!**\n"
                             f"📌 عنوان: {ad['title']}\n"
                             f"🆔 شناسه: {ad['id']}"
                    )
                except:
                    pass
                await message.reply(f"✅ آگهی {ad['id']} تایید شد.")
                return

            if text.startswith('/reject_'):
                ad_id = int(text.split('_')[1])
                ad = next((a for a in all_ads if a['id'] == ad_id), None)
                if not ad:
                    await message.reply("❌ آگهی یافت نشد.")
                    return
                if ad['status'] != 'pending':
                    await message.reply("❌ این آگهی قبلاً تایید یا رد شده است.")
                    return
                ad['status'] = 'rejected'
                save_ads(all_ads)
                try:
                    await bot.send_message(
                        chat_id=ad['seller_id'],
                        text=f"❌ **متأسفانه آگهی شما رد شد.**\n"
                             f"📌 عنوان: {ad['title']}\n"
                             f"🆔 شناسه: {ad['id']}"
                    )
                except:
                    pass
                await message.reply(f"❌ آگهی {ad['id']} رد شد.")
                return

            if message.reply_to_message_id:
                found_user = None
                found_info = None
                for uid, info in last_invoice_for_admin.items():
                    if info['message_id'] == message.reply_to_message_id:
                        found_user = uid
                        found_info = info
                        break
                if found_user and found_info:
                    bank, holder, amount = extract_payment_info(text)
                    if amount:
                        if not bank:
                            bank = "نامشخص"
                        if not holder:
                            holder = "نامشخص"
                        customer_code = found_info.get('customer_code')
                        sheet_debt = get_customer_debt_from_sheet(customer_code) if customer_code else None
                        if sheet_debt is not None:
                            current_debt = sheet_debt
                        else:
                            current_debt = customer_debts.get(found_user, 0)
                        new_debt = current_debt - amount
                        customer_debts[found_user] = new_debt
                        data["customer_debts"] = customer_debts
                        save_data(data)
                        result, msg = به‌روزرسانی_واریزی_در_شیت(
                            found_info.get('invoice_number', ''),
                            amount,
                            bank_name=bank,
                            account_holder=holder
                        )
                        debt_status = f"بستانکاری: {format_price(abs(new_debt))}" if new_debt < 0 else f"بدهی: {format_price(new_debt)}"
                        await message.reply(
                            f"✅ **تسویه حساب انجام شد!**\n"
                            f"👤 کاربر: {found_info['user_name']}\n"
                            f"🏦 بانک: {bank}\n"
                            f"👤 صاحب حساب: {holder}\n"
                            f"💰 مبلغ واریز: {format_price(amount)} تومان\n"
                            f"💳 وضعیت حساب: {debt_status}"
                        )
                        try:
                            await bot.send_message(
                                chat_id=found_user,
                                text=f"✅ **تسویه حساب شما تایید شد!**\n"
                                     f"🏦 بانک: {bank}\n"
                                     f"👤 صاحب حساب: {holder}\n"
                                     f"💰 مبلغ واریز: {format_price(amount)} تومان\n"
                                     f"💳 وضعیت حساب: {debt_status}"
                            )
                        except Exception as e:
                            print(f"⚠️ خطا در ارسال پیام به کاربر: {e}")
                        if result:
                            await message.reply(msg)
                        else:
                            await message.reply(f"⚠️ {msg}")
                        return
                    else:
                        await message.reply("❌ مبلغ در پیامک تراکنش پیدا نشد! لطفاً عدد را وارد کنید.")
                        return
                else:
                    await message.reply("❌ فاکتور مورد نظر پیدا نشد! لطفاً روی فاکتور صحیح ریپلای کنید.")
                    return
            else:
                await message.reply("📋 برای تایید تراکنش، روی فاکتور مورد نظر ریپلای بزنید و مبلغ را وارد کنید.")
                return
        else:
            # کاربر معمولی - ارسال پیامک تراکنش
            amount = extract_amount(text)
            if amount and user_id in last_invoice_for_admin:
                invoice_info = last_invoice_for_admin[user_id]
                bank, holder, _ = extract_payment_info(text)
                if not bank:
                    bank = "نامشخص"
                if not holder:
                    holder = "نامشخص"
                try:
                    await bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"📱 **پیامک تراکنش از مشتری:**\n"
                             f"👤 کاربر: {invoice_info['user_name']}\n"
                             f"🏦 بانک: {bank}\n"
                             f"👤 صاحب حساب: {holder}\n"
                             f"💰 مبلغ: {format_price(amount)} تومان\n"
                             f"📝 شماره تراکنش: {text[:100]}",
                        reply_to_message_id=invoice_info['message_id']
                    )
                    await message.reply("✅ پیامک تراکنش شما به حسابدار ارسال شد. پس از تایید، بدهی شما به‌روزرسانی می‌شود.")
                except Exception as e:
                    print(f"⚠️ خطا در ارسال ریپلای: {e}")
                    await message.reply("⚠️ خطا در ارسال پیامک به حسابدار. لطفاً دوباره تلاش کنید.")
                return
            else:
                await message.reply("📋 **منوی اصلی:**\nاز دکمه‌های زیر استفاده کنید.")
                return

# ============================================================
# 🎯 هندلر کلیک‌ها (با استفاده از regex برای جلوگیری از خطا)
# ============================================================

@bot.on_callback()
async def handle_callback(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.author_guid
    data = message.data
    cart = get_cart(user_id)

    # ========== دکمه‌های عمومی ==========
    if data == 'back_to_menu':
        await show_main_menu(message, user_id)
        return

    if data == 'search':
        cart['search_query'] = ''
        cart['step'] = 'searching'
        await message.reply("🔍 **جستجوی محصولات و آگهی‌ها**\n\nلطفاً عبارت مورد نظر را تایپ کنید:")
        return

    if data == 'new_search':
        cart['search_query'] = ''
        cart['step'] = 'searching'
        await message.reply("🔍 **جستجوی جدید**\n\nلطفاً عبارت مورد نظر را تایپ کنید:")
        return

    # ========== مشاهده محصولات ==========
    if data == 'show_products':
        await show_categories_menu(message, user_id, bot)
        return

    if data.startswith('cat_'):
        category = data.replace('cat_', '')
        cart['current_category'] = category
        cart['current_page'] = 1
        cart['search_query'] = ''
        await show_products_page(message, user_id, bot)
        return

    if data == 'back_to_categories':
        await show_categories_menu(message, user_id, bot)
        return

    if data == 'next_page':
        cart['current_page'] += 1
        await show_products_page(message, user_id, bot)
        return

    if data == 'prev_page':
        cart['current_page'] -= 1
        await show_products_page(message, user_id, bot)
        return

    if data == 'show_cart':
        await show_cart_internal(bot, message, user_id)
        return

    # ========== انتخاب محصول ==========
    if data.startswith('select_'):
        product_name = data.replace('select_', '')
        product = next((p for p in all_products if p['name'] == product_name), None)
        if not product:
            await message.reply("❌ محصول پیدا نشد!")
            return
        cart['selected_product'] = product
        cart['step'] = 'waiting_quantity'
        await message.reply(
            f"📦 **{product['name']}**\n💰 قیمت هر جفت: {format_price(product['price'])} تومان\n📦 تعداد جفت: {product.get('pairCount', 'نامشخص')}\n\n🔢 **تعداد کارتن مورد نظر را وارد کنید:**"
        )
        return

    # ========== مدیریت سبد خرید ==========
    if data.startswith('remove_'):
        product_name = data.replace('remove_', '')
        cart['items'] = [item for item in cart['items'] if item['name'] != product_name]
        await message.reply(f"🗑️ **{product_name}** از سبد خرید حذف شد.")
        if len(cart['items']) == 0:
            await message.reply("🛒 سبد خرید شما خالی است.")
            await show_main_menu(message, user_id)
        else:
            await show_cart_internal(bot, message, user_id)
        return

    if data == 'clear_cart':
        cart['items'] = []
        await message.reply("🗑️ **سبد خرید شما خالی شد.**")
        await show_main_menu(message, user_id)
        return

    if data == 'checkout':
        if len(cart['items']) == 0:
            await message.reply("❌ سبد خرید خالی است!")
            return
        cart['step'] = 'waiting_customer_name'
        await message.reply("✅ **مرحله نهایی‌سازی سفارش**\n\n1️⃣ **نام و نام خانوادگی:**")
        return

    # ========== راهنما ==========
    if data == 'help':
        await message.reply(
            "📋 **راهنمای فروشگاه و آگهی‌ها:**\n"
            "1️⃣ **مشاهده محصولات:** محصولات موجود (از کانال و آگهی‌های تایید شده) را نمایش می‌دهد.\n"
            "2️⃣ **مشاهده آگهی‌ها:** آگهی‌های تایید شده کاربران را بر اساس دسته‌بندی نمایش می‌دهد.\n"
            "3️⃣ **ثبت آگهی جدید:** فرم ثبت آگهی را پر کنید و پس از تایید ادمین، آگهی منتشر می‌شود.\n"
            "4️⃣ **جستجو:** در بین محصولات و آگهی‌ها جستجو کنید.\n"
            "5️⃣ **سبد خرید:** برای سفارش کالاها استفاده کنید.\n"
            "6️⃣ **تسویه حساب:** پیامک تراکنش را به ربات ارسال کنید."
        )
        return

    # ============================================================
    # 🆕 بخش آگهی‌ها (مشاهده و ثبت) - با استفاده از regex
    # ============================================================

    # ----- مشاهده آگهی‌ها -----
    if data == 'show_ads':
        await show_ad_categories_for_view(message, user_id)
        return

    main_match = re.match(r'view_ad_main_(.+)', data)
    if main_match:
        main_cat = main_match.group(1)
        await show_ad_sub_categories(message, main_cat)
        return

    sub_match = re.match(r'view_ad_sub_(.+?)_(.+)', data)
    if sub_match:
        main_cat = sub_match.group(1)
        sub_cat = sub_match.group(2)
        await show_ad_leaf_categories(message, main_cat, sub_cat)
        return

    leaf_match = re.match(r'view_ad_leaf_(.+?)_(.+?)_(.+)', data)
    if leaf_match:
        main_cat = leaf_match.group(1)
        sub_cat = leaf_match.group(2)
        leaf = leaf_match.group(3)
        category_path = f"{main_cat}/{sub_cat}/{leaf}"
        await show_ads_by_category(message, user_id, category_path)
        return

    if data == 'back_to_ad_main':
        await show_ad_categories_for_view(message, user_id)
        return

    back_sub_match = re.match(r'back_to_ad_sub_(.+)', data)
    if back_sub_match:
        main_cat = back_sub_match.group(1)
        await show_ad_sub_categories(message, main_cat)
        return

    back_leaf_match = re.match(r'back_to_ad_leaf_(.+?)_(.+)', data)
    if back_leaf_match:
        main_cat = back_leaf_match.group(1)
        sub_cat = back_leaf_match.group(2)
        await show_ad_leaf_categories(message, main_cat, sub_cat)
        return

    if data == 'back_to_ads_list':
        if cart.get('ad_category_path'):
            await show_ads_by_category(message, user_id, cart['ad_category_path'])
        else:
            await show_ad_categories_for_view(message, user_id)
        return

    detail_match = re.match(r'view_ad_detail_(\d+)', data)
    if detail_match:
        ad_id = int(detail_match.group(1))
        await show_ad_detail(message, user_id, ad_id, bot)
        return

    order_match = re.match(r'order_ad_(\d+)', data)
    if order_match:
        ad_id = int(order_match.group(1))
        ad = next((a for a in all_ads if a['id'] == ad_id), None)
        if not ad or ad['status'] != 'approved':
            await message.reply("❌ آگهی یافت نشد یا تایید نشده است.")
            return
        if ad['type'] != 'product':
            await message.reply("❌ این آگهی قابل سفارش نیست (نوع استخدام).")
            return
        product = {
            'name': ad['title'],
            'price': ad.get('price', 0),
            'pairCount': ad.get('pairCount', 1)
        }
        success, msg = add_to_cart(user_id, product, 1)
        await message.reply(msg)
        if success:
            await show_cart_internal(bot, message, user_id)
        return

    contact_match = re.match(r'contact_ad_(\d+)', data)
    if contact_match:
        ad_id = int(contact_match.group(1))
        ad = next((a for a in all_ads if a['id'] == ad_id), None)
        if not ad or ad['status'] != 'approved':
            await message.reply("❌ آگهی یافت نشد یا تایید نشده است.")
            return
        try:
            await bot.send_message(
                chat_id=ad['seller_id'],
                text=f"📩 **یک کاربر به آگهی شما علاقه‌مند شد:**\n"
                     f"📌 عنوان: {ad['title']}\n"
                     f"👤 کاربر: {user_id}\n"
                     f"💬 برای ارتباط با این کاربر، می‌توانید از طریق ربات پیام دهید."
            )
            await message.reply("✅ درخواست شما به کارفرما ارسال شد. به زودی با شما تماس گرفته می‌شود.")
        except Exception as e:
            await message.reply("⚠️ خطا در ارسال پیام به کارفرما.")
            print(f"❌ خطا در contact_ad: {e}")
        return

    # ============================================================
    # 🆕 ثبت آگهی جدید
    # ============================================================

    if data == 'new_ad':
        await start_new_ad(message, user_id)
        return

    if data == 'ad_type_product':
        cart['ad_type'] = 'product'
        cart['ad_step'] = 'choose_main_cat'
        await show_ad_category_selection(message, user_id, 'main')
        return

    if data == 'ad_type_job':
        cart['ad_type'] = 'job'
        cart['ad_step'] = 'choose_main_cat'
        await show_ad_category_selection(message, user_id, 'main')
        return

    ad_main_match = re.match(r'ad_cat_main_(.+)', data)
    if ad_main_match:
        main_cat = ad_main_match.group(1)
        cart['ad_data']['main_category'] = main_cat
        cart['ad_step'] = 'choose_sub_cat'
        await show_ad_category_selection(message, user_id, 'sub')
        return

    if data == 'back_to_ad_main_cat':
        cart['ad_step'] = 'choose_main_cat'
        await show_ad_category_selection(message, user_id, 'main')
        return

    ad_sub_match = re.match(r'ad_cat_sub_(.+?)_(.+)', data)
    if ad_sub_match:
        main_cat = ad_sub_match.group(1)
        sub_cat = ad_sub_match.group(2)
        cart['ad_data']['main_category'] = main_cat
        cart['ad_data']['sub_category'] = sub_cat
        cart['ad_step'] = 'choose_leaf_cat'
        await show_ad_category_selection(message, user_id, 'leaf')
        return

    back_ad_sub_match = re.match(r'back_to_ad_sub_cat_(.+)', data)
    if back_ad_sub_match:
        main_cat = back_ad_sub_match.group(1)
        cart['ad_data']['main_category'] = main_cat
        cart['ad_step'] = 'choose_sub_cat'
        await show_ad_category_selection(message, user_id, 'sub')
        return

    ad_leaf_match = re.match(r'ad_cat_leaf_(.+?)_(.+?)_(.+)', data)
    if ad_leaf_match:
        main_cat = ad_leaf_match.group(1)
        sub_cat = ad_leaf_match.group(2)
        leaf = ad_leaf_match.group(3)
        category_path = f"{main_cat}/{sub_cat}/{leaf}"
        cart['ad_data']['category_path'] = category_path
        cart['ad_step'] = 'enter_title'
        await message.reply("📝 **عنوان آگهی** را وارد کنید:")
        return

    await message.reply("❌ دکمه نامعتبر!")

# ============================================================
# 🌐 Flask برای Keep-Alive
# ============================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ ربات فروشگاه و آگهی‌ها فعال است!", 200

@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ============================================================
# 🚀 اجرا
# ============================================================

if __name__ == "__main__":
    print("✅ ربات فروشگاه و آگهی‌ها در حال راه‌اندازی...")
    os.makedirs('invoices', exist_ok=True)
    os.makedirs('payments', exist_ok=True)
    os.makedirs('ad_images', exist_ok=True)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ ربات با Polling اجرا شد...")
    bot.run()
