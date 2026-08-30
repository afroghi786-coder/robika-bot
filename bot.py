# ============================================================
# 🤖 ربات فروشگاهی - نسخه نهایی (جستجو فعال + دسته زنانه)
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
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging

logging.basicConfig(level=logging.INFO)

# ============================================================
# 📦 فایل‌های ذخیره‌سازی
# ============================================================

PRODUCTS_FILE = "products.json"
DATA_FILE = "data.json"
CREDENTIALS_FILE = "credentials.json"
SHEET_ID = "شناسه_شیت_خود_را_اینجا_وارد_کنید"

# ============================================================
# 📊 اتصال به گوگل‌شیت
# ============================================================

def get_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet("فروش")

def get_column_index_by_title(records, title_variants):
    if len(records) == 0:
        return None
    header = records[0]
    for i, cell in enumerate(header):
        cell_clean = str(cell).strip()
        for variant in title_variants:
            if cell_clean == variant or cell_clean.startswith(variant) or cell_clean.endswith(variant) or variant in cell_clean:
                logging.info(f"✅ ستون '{variant}' پیدا شد: ایندکس {i}")
                return i
    logging.warning(f"⚠️ هیچ یک از عنوان‌های {title_variants} در هدر پیدا نشد!")
    return None

def get_last_invoice_number_from_sheet():
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_values()
        if len(records) < 2:
            return 0
        col_invoice = get_column_index_by_title(records, ["شماره_فاکتور", "شماره فاکتور"])
        if col_invoice is None:
            return 0
        max_num = 0
        for row in records[1:]:
            if len(row) > col_invoice:
                val = row[col_invoice].strip()
                if val.startswith("M_"):
                    try:
                        num = int(val.split("_")[1])
                        if num > max_num:
                            max_num = num
                    except:
                        pass
        return max_num
    except Exception as e:
        logging.error(f"❌ خطا در خواندن شماره فاکتور: {e}")
        return 0

def get_existing_customer_data():
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_values()
        if len(records) < 2:
            return {}, 3000
        col_phone = get_column_index_by_title(records, ["تلفن_مشتری", "تلفن مشتری", "شماره تماس"])
        col_code = get_column_index_by_title(records, ["کد_مشتری", "کد مشتری"])
        if col_phone is None or col_code is None:
            return {}, 3000
        phone_to_code = {}
        max_code = 3000
        for row in records[1:]:
            if len(row) > max(col_phone, col_code):
                phone = str(row[col_phone]).strip().replace(' ', '').replace('-', '')
                code = str(row[col_code]).strip()
                if phone and code:
                    phone_to_code[phone] = code
                    if code.startswith("MO_"):
                        try:
                            num = int(code.replace("MO_", ""))
                            if num > max_code:
                                max_code = num
                        except:
                            pass
        return phone_to_code, max_code
    except Exception as e:
        logging.error(f"❌ خطا در خواندن کد مشتری: {e}")
        return {}, 3000

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
last_invoice = get_last_invoice_number_from_sheet()
if last_invoice > data.get("invoice_counter", 0):
    data["invoice_counter"] = last_invoice
    save_data(data)

phone_to_code, max_code = get_existing_customer_data()
if max_code > data.get("customer_counter", 3000):
    data["customer_counter"] = max_code
    save_data(data)

invoice_counter = data.get("invoice_counter", 0)
customer_counter = data.get("customer_counter", 3000)
customer_codes = data.get("customer_codes", {})
customer_debts = data.get("customer_debts", {})
last_invoice_for_admin = data.get("last_invoice_for_admin", {})

# ============================================================
# 🔗 توابع ارتباط با وب‌هوک گوگل‌شیت
# ============================================================

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
        phone_to_code, max_code = get_existing_customer_data()
        if phone in phone_to_code:
            code = phone_to_code[phone]
            customer_codes[phone] = code
            data["customer_codes"] = customer_codes
            save_data(data)
            return code
        if max_code > customer_counter:
            customer_counter = max_code
        customer_counter += 1
        code = f"MO_{customer_counter}"
        customer_codes[phone] = code
        data["customer_counter"] = customer_counter
        data["customer_codes"] = customer_codes
        save_data(data)
        return code

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
# 🤖 تنظیمات اولیه
# ============================================================

TOKEN = os.environ.get("TOKEN", "")
BOT_USERNAME = "FroghiShopBot"
ADMIN_CHAT_ID = "b0HWCJJ0xHE0e4e078b6c5228504866a"
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwRqVHtBhcI1T4cuTOPQBt5yAsYc6sFkgi-acRshZODZQs-t3_2gcj-7gTqoI7IfvnXSg/exec"

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

# ✅ دسته زنانه به تابع تشخیص اضافه شد
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
PERSIAN_LETTERS = ['ا', 'ب', 'پ', 'ت', 'ث', 'ج', 'چ', 'ح', 'خ', 'د', 'ذ', 'ر', 'ز', 'ژ', 'س', 'ش', 'ص', 'ض', 'ط', 'ظ', 'ع', 'غ', 'ف', 'ق', 'ک', 'گ', 'ل', 'م', 'ن', 'و', 'ه', 'ی']
NUMBERS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']

def get_cart(user_id):
    if user_id not in carts:
        carts[user_id] = {
            'items': [], 'step': 'idle', 'selected_product': None,
            'customer': {}, 'search_query': '',
            'current_page': 1, 'current_category': 'همه محصولات'
        }
    return carts[user_id]

# ============================================================
# 🎨 دکوریشن و نمایش
# ============================================================

async def show_main_menu(message, user_id):
    keypad_builder = ChatKeypadBuilder()
    keypad_builder.row(
        ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات"),
        ChatKeypadBuilder().button(id="search", text="🔍 جستجو"),
    )
    keypad_builder.row(
        ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید"),
        ChatKeypadBuilder().button(id="help", text="📋 راهنما"),
    )
    await message.reply_keypad("🏠 **منوی اصلی فروشگاه:**", keypad_builder.build())

async def show_categories_menu(message, user_id, bot):
    keypad_builder = ChatKeypadBuilder()
    keypad_builder.row(
        ChatKeypadBuilder().button(id="cat_همه محصولات", text="🗂️ همه محصولات"),
    )
    keypad_builder.row(
        ChatKeypadBuilder().button(id="cat_مردانه", text="👞 مردانه"),
        ChatKeypadBuilder().button(id="cat_زنانه", text="👠 زنانه"),
    )
    keypad_builder.row(
        ChatKeypadBuilder().button(id="cat_میانه", text="👟 میانه"),
        ChatKeypadBuilder().button(id="cat_بچگانه", text="🧒 بچگانه"),
    )
    keypad_builder.row(
        ChatKeypadBuilder().button(id="cat_دخترانه", text="👧 دخترانه"),
        ChatKeypadBuilder().button(id="cat_پسرانه", text="👦 پسرانه"),
    )
    keypad_builder.row(
        ChatKeypadBuilder().button(id="cat_متفرقه", text="📦 متفرقه"),
    )
    keypad_builder.row(ChatKeypadBuilder().button(id="back_to_menu", text="🔙 بازگشت به منو"))
    await message.reply_keypad("🗂️ **انتخاب دسته‌بندی:**", keypad_builder.build())

async def show_products_page(message, user_id, bot):
    cart = get_cart(user_id)
    category = cart['current_category']
    page = cart['current_page']
    filtered = [p for p in all_products if p['category'] == category]
    
    per_page = 20
    total_pages = (len(filtered) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]

    if not page_items:
        await message.reply("❌ محصولی در این دسته یافت نشد.")
        return

    keypad_builder = ChatKeypadBuilder()
    row = []
    for i, product in enumerate(page_items, 1):
        short_name = product['name'][:20]
        row.append(ChatKeypadBuilder().button(id=f"select_{product['name']}", text=short_name))
        if len(row) == 4:
            keypad_builder.row(*row)
            row = []
    if row:
        keypad_builder.row(*row)

    nav_row = []
    if page > 1:
        nav_row.append(ChatKeypadBuilder().button(id="prev_page", text="⏮️ قبلی"))
    nav_row.append(ChatKeypadBuilder().button(id="back_to_categories", text="🗂️ دسته‌ها"))
    if page < total_pages:
        nav_row.append(ChatKeypadBuilder().button(id="next_page", text="بعدی ⏭️"))
    if nav_row:
        keypad_builder.row(*nav_row)
    keypad_builder.row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید"))

    text = f"📦 **لیست محصولات (دسته: {category})**\nصفحه {page} از {total_pages}\n"
    await message.reply_keypad(text, keypad_builder.build())

# ✅ تابع جستجو (فعال شد)
async def show_search_keypad(message: Message, user_id: str, bot: Robot):
    cart = get_cart(user_id)
    query = cart.get('search_query', '')
    keypad_builder = ChatKeypadBuilder()
    row = []
    for i, letter in enumerate(PERSIAN_LETTERS):
        row.append(ChatKeypadBuilder().button(id=f"search_letter_{letter}", text=letter))
        if len(row) == 4:
            keypad_builder.row(*row)
            row = []
    if row:
        keypad_builder.row(*row)
    num_row = []
    for num in NUMBERS:
        num_row.append(ChatKeypadBuilder().button(id=f"search_letter_{num}", text=num))
    keypad_builder.row(*num_row)
    keypad_builder.row(
        ChatKeypadBuilder().button(id="search_backspace", text="⌫"),
        ChatKeypadBuilder().button(id="search_clear", text="🗑️ پاک کردن"),
        ChatKeypadBuilder().button(id="search_exit", text="❌ خروج")
    )
    keypad = keypad_builder.build()
    search_text = f"🔍 **جستجوی محصولات**\n\nعبارت جستجو: `{query}`\n\n" if query else "🔍 **جستجوی محصولات**\n\nلطفاً حروف را انتخاب کنید.\n"
    filtered = [p for p in all_products if query.lower() in p['name'].lower()] if query else []
    if filtered:
        search_text += f"\n✅ {len(filtered)} محصول پیدا شد:\n"
        for i, prod in enumerate(filtered[:10]):
            search_text += f"{i+1}. {prod['name']} - {format_price(prod['price'])} تومان\n"
        if len(filtered) > 10:
            search_text += f"\nو {len(filtered)-10} محصول دیگر ..."
        prod_keypad_builder = ChatKeypadBuilder()
        for prod in filtered[:10]:
            prod_keypad_builder.row(
                ChatKeypadBuilder().button(
                    id=f"select_{prod['name']}",
                    text=f"➕ {prod['name']}"
                )
            )
        if len(filtered) > 10:
            prod_keypad_builder.row(
                ChatKeypadBuilder().button(
                    id="search_show_more",
                    text="📋 نمایش همه"
                )
            )
        prod_keypad = prod_keypad_builder.build()
        await bot.send_message(
            chat_id=message.chat_id,
            text=search_text,
            inline_keypad=prod_keypad
        )
    else:
        await bot.send_message(
            chat_id=message.chat_id,
            text=search_text,
            inline_keypad=keypad
        )

async def show_cart_internal(bot, message, user_id):
    cart = get_cart(user_id)
    if len(cart['items']) == 0:
        await message.reply("🛒 سبد خرید شما خالی است!")
        return
    total = 0
    keypad_builder = ChatKeypadBuilder()
    row = []
    for item in cart['items']:
        pair_count = item.get('pairCount', 1)
        subtotal = item['price'] * pair_count * item['quantity']
        total += subtotal
        short_name = item['name'][:20]
        row.append(ChatKeypadBuilder().button(id=f"remove_{item['name']}", text=f"🗑️ {short_name}"))
        if len(row) == 2:
            keypad_builder.row(*row)
            row = []
    if row:
        keypad_builder.row(*row)
    keypad_builder.row(ChatKeypadBuilder().button(id="checkout", text="✅ نهایی‌سازی سفارش"))
    keypad_builder.row(ChatKeypadBuilder().button(id="clear_cart", text="🗑️ خالی کردن سبد"))
    keypad_builder.row(ChatKeypadBuilder().button(id="back_to_menu", text="🔙 بازگشت به منو"))
    text = f"🛒 **سبد خرید شما:**\n💰 **جمع کل: {format_price(total)} تومان**"
    await message.reply_keypad(text, keypad_builder.build())

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

def به‌روزرسانی_واریزی_در_شیت(invoice_number, payment_amount, account_number="", account_holder=""):
    try:
        payload = {
            "action": "update_payment", "invoice_number": invoice_number,
            "payment_amount": payment_amount, "account_number": account_number,
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
                    msg = f"واریزی {formatted_amount} تومان برای فاکتور {invoice_number} ثبت شد."
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
    previous_debt = customer_debts.get(user_id, 0)
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
            'message_id': admin_msg.message_id, 'chat_id': ADMIN_CHAT_ID,
            'user_name': customer.get('name', 'نامشخص'),
            'total_payable': total_payable, 'invoice_number': invoice_number
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
    menu_keypad = ChatKeypadBuilder()
    menu_keypad.row(ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات"))
    menu_keypad.row(ChatKeypadBuilder().button(id="search", text="🔍 جستجو"))
    menu_keypad.row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید"))
    menu_keypad.row(ChatKeypadBuilder().button(id="help", text="📋 راهنما"))
    await message.reply_keypad(
        "✅ **سفارش شما با موفقیت ثبت شد!**\n\n"
        f"🆔 **کد مشتری شما: {customer_code}**\n"
        f"💳 **وضعیت حساب شما: {format_price(total_payable)} تومان**\n\n"
        "📱 **برای تسویه حساب، پیامک تراکنش را همراه با مبلغ به این حساب ارسال کنید.**",
        menu_keypad.build()
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

    if chat_id.startswith('b0'):
        cart = get_cart(user_id)
        if text == '/start' or text == 'start':
            await show_main_menu(message, user_id)
            return
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
                await show_products_page(message, user_id, bot)
            return
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
        if chat_id == ADMIN_CHAT_ID:
            if message.reply_to_message_id:
                found_user = None
                found_info = None
                for uid, info in last_invoice_for_admin.items():
                    if info['message_id'] == message.reply_to_message_id:
                        found_user = uid
                        found_info = info
                        break
                if found_user and found_info:
                    amount = extract_amount(text)
                    if amount:
                        current_debt = customer_debts.get(found_user, 0)
                        new_debt = current_debt - amount
                        customer_debts[found_user] = new_debt
                        data["customer_debts"] = customer_debts
                        save_data(data)
                        if new_debt < 0:
                            debt_status = f"بستانکاری: {format_price(abs(new_debt))} تومان"
                        else:
                            debt_status = f"بدهی: {format_price(new_debt)} تومان"
                        await message.reply(
                            f"✅ **تسویه حساب انجام شد!**\n👤 کاربر: {found_info['user_name']}\n💰 مبلغ واریز: {format_price(amount)} تومان\n💳 وضعیت حساب: {debt_status}"
                        )
                        try:
                            await bot.send_message(
                                chat_id=found_user,
                                text=f"✅ **تسویه حساب شما تایید شد!**\n💰 مبلغ واریز: {format_price(amount)} تومان\n💳 وضعیت حساب: {debt_status}"
                            )
                        except Exception as e:
                            print(f"⚠️ خطا در ارسال پیام به کاربر: {e}")
                        result, msg = به‌روزرسانی_واریزی_در_شیت(found_info.get('invoice_number', ''), amount)
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
            amount = extract_amount(text)
            if amount and user_id in last_invoice_for_admin:
                invoice_info = last_invoice_for_admin[user_id]
                try:
                    await bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"📱 **پیامک تراکنش از مشتری:**\n👤 کاربر: {invoice_info['user_name']}\n💰 مبلغ: {format_price(amount)} تومان\n📝 شماره تراکنش: {text[:100]}",
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
# 🎯 هندلر کلیک‌ها
# ============================================================

@bot.on_callback()
async def handle_callback(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.author_guid
    data = message.data
    cart = get_cart(user_id)

    if data == 'back_to_menu':
        await show_main_menu(message, user_id)
        return
    
    # ✅ جستجو فعال شد
    if data == 'search':
        cart['search_query'] = ''
        await show_search_keypad(message, user_id, bot)
        return

    if data.startswith('search_letter_'):
        letter = data.replace('search_letter_', '')
        cart['search_query'] += letter
        await show_search_keypad(message, user_id, bot)
        return

    if data == 'search_backspace':
        cart['search_query'] = cart['search_query'][:-1]
        await show_search_keypad(message, user_id, bot)
        return

    if data == 'search_clear':
        cart['search_query'] = ''
        await show_search_keypad(message, user_id, bot)
        return

    if data == 'search_exit':
        cart['search_query'] = ''
        await show_main_menu(message, user_id)
        return

    if data == 'search_show_more':
        query = cart.get('search_query', '')
        filtered = [p for p in all_products if query.lower() in p['name'].lower()] if query else []
        if filtered:
            text = f"🔍 **نتایج جستجو برای `{query}`**\n\n"
            for i, prod in enumerate(filtered, 1):
                text += f"{i}. {prod['name']} - {format_price(prod['price'])} تومان\n"
            text += "\nبرای سفارش، روی دکمه محصول کلیک کنید."
            keypad_builder = ChatKeypadBuilder()
            for prod in filtered[:20]:
                keypad_builder.row(
                    ChatKeypadBuilder().button(
                        id=f"select_{prod['name']}",
                        text=f"➕ {prod['name']}"
                    )
                )
            keypad_builder.row(ChatKeypadBuilder().button(id="search_exit", text="🔙 بازگشت"))
            keypad = keypad_builder.build()
            await message.reply_keypad(text, keypad)
        else:
            await message.reply("❌ هیچ محصولی یافت نشد.")
        return

    if data == 'show_products':
        await show_categories_menu(message, user_id, bot)
        return
    
    if data.startswith('cat_'):
        category = data.replace('cat_', '')
        cart['current_category'] = category
        cart['current_page'] = 1
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
    if data == 'help':
        await message.reply(
            "📋 **راهنمای فروشگاه:**\n"
            "1️⃣ از منوی اصلی، **مشاهده محصولات** یا **جستجو** را انتخاب کنید.\n"
            "2️⃣ در جستجو، حروف را انتخاب کنید تا محصولات فیلتر شوند.\n"
            "3️⃣ روی محصول مورد نظر کلیک کنید و تعداد کارتن را وارد کنید.\n"
            "4️⃣ **بدون برگشت به منو**، محصول بعدی را انتخاب کنید.\n"
            "5️⃣ در انتها **سبد خرید** را باز کنید و **نهایی‌سازی** را بزنید.\n"
            "6️⃣ برای تسویه حساب، پیامک تراکنش را همراه با مبلغ به این حساب ارسال کنید."
        )
        return
    await message.reply("❌ دکمه نامعتبر!")

# ============================================================
# 🌐 Flask برای Keep-Alive
# ============================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ ربات فروشگاه فعال است!", 200

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
    print("✅ ربات فروشگاه در حال راه‌اندازی...")
    os.makedirs('invoices', exist_ok=True)
    os.makedirs('payments', exist_ok=True)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ ربات با Polling اجرا شد...")
    bot.run()
