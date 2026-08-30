# ============================================================
# 🤖 ربات فروشگاهی - نسخه نهایی با اصلاح شماره فاکتور و کد مشتری
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

# ============================================================
# 📦 فایل‌های ذخیره‌سازی
# ============================================================

PRODUCTS_FILE = "products.json"
DATA_FILE = "data.json"
CREDENTIALS_FILE = "credentials.json"   # ← فایل credentials.json را در پروژه قرار دهید
SHEET_ID = "شناسه_شیت_خود_را_اینجا_وارد_کنید"  # ← شناسه فایل گوگل‌شیت

# ============================================================
# 📊 اتصال به گوگل‌شیت برای خواندن داده‌های موجود
# ============================================================

def get_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet("فروش")

def get_last_invoice_number_from_sheet():
    """بزرگترین شماره فاکتور موجود در شیت فروش را برمی‌گرداند"""
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_values()
        if len(records) < 2:
            return 0
        # پیدا کردن ستون شماره_فاکتور
        header = records[0]
        col_invoice = None
        for i, h in enumerate(header):
            if "شماره_فاکتور" in h or "شماره فاکتور" in h:
                col_invoice = i
                break
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
        print(f"⚠️ خطا در خواندن شماره فاکتور از شیت: {e}")
        return 0

def get_existing_customer_data():
    """خواندن شماره تماس و کد مشتری از شیت فروش"""
    try:
        sheet = get_google_sheet()
        records = sheet.get_all_values()
        if len(records) < 2:
            return {}, 3000
        header = records[0]
        col_phone = None
        col_code = None
        for i, h in enumerate(header):
            if "تلفن" in h or "شماره تماس" in h:
                col_phone = i
            if "کد_مشتری" in h or "کد مشتری" in h:
                col_code = i
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
        print(f"⚠️ خطا در خواندن کد مشتری: {e}")
        return {}, 3000

# ============================================================
# 📦 مدیریت داده‌های پایدار (شمارنده‌ها)
# ============================================================

def load_data():
    default_data = {
        "invoice_counter": 0,
        "customer_counter": 3000,
        "customer_codes": {}
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # اطمینان از وجود کلیدها
                data.setdefault("invoice_counter", 0)
                data.setdefault("customer_counter", 3000)
                data.setdefault("customer_codes", {})
                return data
        except:
            return default_data
    return default_data

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# بارگذاری داده‌ها در شروع
data = load_data()
# تنظیم شمارنده فاکتور بر اساس بزرگترین شماره موجود در شیت
last_invoice = get_last_invoice_number_from_sheet()
if last_invoice > data.get("invoice_counter", 0):
    data["invoice_counter"] = last_invoice
    save_data(data)

invoice_counter = data.get("invoice_counter", 0)
customer_counter = data.get("customer_counter", 3000)
customer_codes = data.get("customer_codes", {})

# ============================================================
# 📦 توابع تولید شماره فاکتور و کد مشتری (اصلاح‌شده)
# ============================================================

def generate_invoice_number():
    global invoice_counter, data
    invoice_counter += 1
    data["invoice_counter"] = invoice_counter
    save_data(data)
    now = datetime.now()
    return f"M_{now.strftime('%Y%m%d')}{invoice_counter:04d}"

def get_or_create_customer_code(phone):
    global customer_counter, customer_codes, data
    phone = phone.replace(' ', '').replace('-', '')
    
    # ابتدا از دیکشنری محلی چک کن
    if phone in customer_codes:
        return customer_codes[phone]
    
    # از شیت فروش بخوان
    phone_to_code, max_code = get_existing_customer_data()
    if phone in phone_to_code:
        code = phone_to_code[phone]
        customer_codes[phone] = code
        data["customer_codes"] = customer_codes
        save_data(data)
        return code
    
    # شماره جدید است → کد جدید بساز
    # از max_code استفاده کن (بزرگترین کد موجود در شیت)
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

# ============================================================
# 🤖 تنظیمات اولیه
# ============================================================

TOKEN = os.environ.get("TOKEN", "")
BOT_USERNAME = "FroghiShopBot"
ADMIN_CHAT_ID = "b0HWCJJ0xHE0e4e078b6c5228504866a"  # ← شناسه چت حسابدار

# ============================================================
# 📊 تنظیمات گوگل‌شیت (Webhook)
# ============================================================

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzp6NTuFqIxEGa7vcb35tGtGALEe230nvkVT-TZVdOFw0PBGrQAL6Yl71ge8QvJyGiLPg/exec"  # ← آدرس Webhook خود را قرار دهید

def ثبت_سفارش_در_شیت(customer, items, total, invoice_number, customer_code):
    """ارسال سفارش به Webhook - هر محصول یک ردیف"""
    try:
        payload = {
            "action": "register",
            "timestamp": datetime.now().isoformat(),
            "invoice_number": invoice_number,
            "customer_code": customer_code,
            "customer_name": customer.get('name', ''),
            "customer_phone": customer.get('phone', ''),
            "customer_address": customer.get('address', ''),
            "customer_shipping": customer.get('shipping', ''),
            "total": total,
            "items": items
        }
        print(f"📤 ارسال به Webhook: {WEBHOOK_URL}")
        print(f"📦 Payload: {json.dumps(payload, ensure_ascii=False)}")
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"✅ سفارش {invoice_number} در گوگل‌شیت ثبت شد.")
                return True
            else:
                print(f"⚠️ خطا از سمت Webhook: {result.get('message')}")
                return False
        else:
            print(f"⚠️ خطا در ارتباط با Webhook: {response.text}")
            return False
    except Exception as e:
        print(f"❌ خطا در ثبت سفارش: {e}")
        return False

def به‌روزرسانی_واریزی_در_شیت(invoice_number, payment_amount, account_number="", account_holder=""):
    """ارسال واریزی به Webhook (هر واریزی یک ردیف)"""
    try:
        payload = {
            "action": "update_payment",
            "invoice_number": invoice_number,
            "payment_amount": payment_amount,
            "account_number": account_number,
            "account_holder": account_holder
        }
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"✅ واریزی {invoice_number} ثبت شد.")
                return True, result.get("message", "")
            else:
                return False, result.get("message", "❌ خطا در ثبت واریزی")
        else:
            return False, f"❌ خطا: {response.text}"
    except Exception as e:
        return False, f"❌ خطا: {e}"

# ============================================================
# 📦 حافظه موقت (سبد خرید، بدهی‌ها و ...)
# ============================================================

all_products = load_products()
carts = {}
customer_debts = {}
last_invoice_for_admin = {}

PERSIAN_LETTERS = [
    'ا', 'ب', 'پ', 'ت', 'ث', 'ج', 'چ', 'ح', 'خ', 'د', 'ذ', 'ر', 'ز', 'ژ',
    'س', 'ش', 'ص', 'ض', 'ط', 'ظ', 'ع', 'غ', 'ف', 'ق', 'ک', 'گ', 'ل', 'م',
    'ن', 'و', 'ه', 'ی'
]
NUMBERS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']

def get_cart(user_id):
    if user_id not in carts:
        carts[user_id] = {
            'items': [],
            'step': 'idle',
            'selected_product': None,
            'customer': {},
            'search_query': ''
        }
    return carts[user_id]

# ============================================================
# 🔍 توابع کمکی
# ============================================================

def convert_persian_number(text):
    mapping = {'۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
               '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9'}
    for p, e in mapping.items():
        text = text.replace(p, e)
    return text

def detect_product(text):
    if not text:
        return None
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
    return {'name': name, 'price': price, 'pairCount': pair_count}

def extract_amount(text):
    if not text:
        return None
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
        'name': product['name'],
        'price': product['price'],
        'quantity': quantity,
        'pairCount': product.get('pairCount', 0)
    })
    return True, f"✅ {product['name']} به سبد خرید اضافه شد!"

# ============================================================
# 🖼️ تولید فاکتور (بدون تغییر)
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
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf"
    ]
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
            font_title = ImageFont.load_default()
            font_header = ImageFont.load_default()
            font_normal = ImageFont.load_default()
            font_bold = ImageFont.load_default()
            font_footer = ImageFont.load_default()
    else:
        font_title = ImageFont.load_default()
        font_header = ImageFont.load_default()
        font_normal = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font_footer = ImageFont.load_default()
    y = margin + 40
    right_x = width - margin - 40
    if os.path.exists("logo.png"):
        try:
            logo = Image.open("logo.png")
            logo = logo.resize((240, 180))
            image.paste(logo, (margin + 20, y - 20))
        except:
            pass
    draw.text((right_x - 600, y), persian_text("فاکتور فروش"), fill=(25, 70, 160), font=font_title)
    draw.text((right_x - 650, y + 100), persian_text(f"تاریخ: {datetime.now().strftime('%Y/%m/%d')}"), fill=(100, 100, 100), font=font_header)
    draw.text((right_x - 750, y), persian_text(f"شماره: {invoice_number}"), fill=(0, 0, 0), font=font_header)
    draw.text((right_x - 650, y + 100), persian_text(f"کد مشتری: {customer_code}"), fill=(25, 70, 160), font=font_header)
    y += 260
    draw.rectangle([(margin + 20, y), (width - margin - 20, y + 200)], fill=(245, 248, 250), outline=(200, 210, 220), width=2)
    draw.text((right_x - 450, y + 40), persian_text(f"مشتری: {customer.get('name', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal)
    draw.text((right_x - 520, y + 105), persian_text(f"تلفن: {customer.get('phone', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal)
    draw.text((right_x - 520, y + 170), persian_text(f"آدرس: {customer.get('address', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal)
    draw.text((600, y + 40), persian_text(f"باربری: {customer.get('shipping', 'نامشخص')}"), fill=(0, 0, 0), font=font_normal)
    y += 250
    col_widths = [100, 1200, 180, 180, 450, 600]
    col_pos = []
    current = right_x
    for w in col_widths:
        col_pos.append(current - w)
        current -= w
    draw.rectangle([(margin + 20, y), (width - margin - 20, y + 100)], fill=(25, 70, 160))
    draw.text((col_pos[0] + 20, y + 30), persian_text("ردیف"), fill=(255, 255, 255), font=font_bold)
    draw.text((col_pos[1] + 20, y + 30), persian_text("نام مدل"), fill=(255, 255, 255), font=font_bold)
    draw.text((col_pos[2] + 20, y + 30), persian_text("کارتن"), fill=(255, 255, 255), font=font_bold)
    draw.text((col_pos[3] + 20, y + 30), persian_text("جفت"), fill=(255, 255, 255), font=font_bold)
    draw.text((col_pos[4] + 20, y + 30), persian_text("قیمت هر جفت"), fill=(255, 255, 255), font=font_bold)
    draw.text((col_pos[5] + 20, y + 30), persian_text("مبلغ کل"), fill=(255, 255, 255), font=font_bold)
    y += 100
    for i, item in enumerate(items, 1):
        if i % 2 == 0:
            draw.rectangle([(margin + 20, y), (width - margin - 20, y + 110)], fill=(248, 250, 252))
        draw.text((col_pos[0] + 20, y + 35), str(i), fill=(0, 0, 0), font=font_normal)
        draw.text((col_pos[1] + 20, y + 35), persian_text(item['name'][:50]), fill=(0, 0, 0), font=font_normal)
        draw.text((col_pos[2] + 20, y + 35), str(item['quantity']), fill=(0, 0, 0), font=font_normal)
        draw.text((col_pos[3] + 20, y + 35), str(item['pairCount']), fill=(0, 0, 0), font=font_normal)
        draw.text((col_pos[4] + 20, y + 35), format_price(item['price_per_pair']), fill=(0, 0, 0), font=font_normal)
        draw.text((col_pos[5] + 20, y + 35), format_price(item['subtotal']), fill=(0, 0, 0), font=font_normal)
        y += 110
    draw.line([(margin + 20, y), (width - margin - 20, y)], fill=(200, 210, 220), width=4)
    y += 80
    draw.text((right_x - 700, y), persian_text(f"جمع سفارش جدید: {format_price(total)} تومان"), fill=(25, 70, 160), font=font_bold)
    y += 110
    if previous_debt > 0:
        draw.text((right_x - 700, y), persian_text(f"بدهی قبلی: {format_price(previous_debt)} تومان"), fill=(200, 50, 50), font=font_bold)
        y += 110
        draw.text((right_x - 750, y), persian_text(f"مبلغ قابل پرداخت: {format_price(total + previous_debt)} تومان"), fill=(0, 150, 0), font=font_bold)
    else:
        draw.text((right_x - 700, y), persian_text(f"مبلغ قابل پرداخت: {format_price(total)} تومان"), fill=(0, 150, 0), font=font_bold)
    y += 200
    draw.text((right_x - 500, y), persian_text("🙏 از اعتماد شما سپاسگزاریم!"), fill=(150, 150, 150), font=font_footer)
    filename = f"invoices/invoice_{invoice_number}.png"
    os.makedirs("invoices", exist_ok=True)
    image.save(filename, "PNG", quality=100, dpi=(300, 300))
    return filename

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
# 📤 نمایش لیست محصولات
# ============================================================

async def show_products_list(message: Message, user_id: str):
    if not all_products:
        await message.reply("❌ هنوز محصولی در فروشگاه ثبت نشده است.")
        return
    text = "📦 **لیست محصولات:**\n\n"
    for i, product in enumerate(all_products, 1):
        text += f"{i}. {product['name']}\n"
        text += f"   💰 قیمت هر جفت: {format_price(product['price'])} تومان\n"
        text += f"   📦 تعداد جفت: {product.get('pairCount', 'نامشخص')}\n\n"
    text += f"\n🔢 **برای سفارش، روی نام محصول کلیک کنید.**"
    keypad_builder = ChatKeypadBuilder()
    row = []
    for i, product in enumerate(all_products, 1):
        row.append(ChatKeypadBuilder().button(id=f"select_{product['name']}", text=f"{i}. {product['name']}"))
        if len(row) == 2:
            keypad_builder.row(*row)
            row = []
    if row:
        keypad_builder.row(*row)
    keypad_builder.row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید"))
    keypad_builder.row(ChatKeypadBuilder().button(id="back_menu", text="🔙 بازگشت به منو"))
    keypad = keypad_builder.build()
    await message.reply_keypad(text, keypad)

# ============================================================
# 🔍 جستجوی زنده
# ============================================================

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

# ============================================================
# 💾 نهایی‌سازی سفارش
# ============================================================

async def finalize_order(message: Message, user_id: str, bot: Robot):
    global customer_debts, last_invoice_for_admin
    cart = get_cart(user_id)
    customer = cart['customer']
    if len(cart['items']) == 0:
        await message.reply("❌ سبد خرید خالی است!")
        return
    phone = customer.get('phone', '')
    if len(phone.replace(' ', '').replace('-', '')) < 11:
        await message.reply("❌ شماره تماس معتبر نیست. حداقل ۱۱ رقم وارد کنید.")
        return
    customer_code = get_or_create_customer_code(phone)
    total = 0
    items_list = []
    for item in cart['items']:
        pair_count = item.get('pairCount', 1)
        subtotal = item['price'] * pair_count * item['quantity']
        total += subtotal
        items_list.append({
            'name': item['name'],
            'quantity': item['quantity'],
            'pairCount': pair_count,
            'price_per_pair': item['price'],
            'subtotal': subtotal
        })
    previous_debt = customer_debts.get(user_id, 0)
    total_payable = previous_debt + total
    invoice_number = generate_invoice_number()
    try:
        image_path = create_invoice_image(
            customer=customer,
            items=items_list,
            total=total,
            previous_debt=previous_debt,
            invoice_number=invoice_number,
            customer_code=customer_code
        )
        await bot.send_photo(
            chat_id=message.chat_id,
            photo=image_path,
            caption=f"🧾 فاکتور شماره: {invoice_number}\n🆔 کد مشتری: {customer_code}"
        )
        if os.path.exists(image_path):
            os.remove(image_path)
    except Exception as e:
        print(f"⚠️ خطا در تولید فاکتور: {e}")
        await message.reply("⚠️ خطا در تولید فاکتور، لطفاً دوباره تلاش کنید.")
        return
    try:
        image_path = create_invoice_image(
            customer=customer,
            items=items_list,
            total=total,
            previous_debt=previous_debt,
            invoice_number=invoice_number,
            customer_code=customer_code
        )
        admin_msg = await bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=image_path,
            caption=f"📬 فاکتور جدید از مشتری: {customer.get('name', 'نامشخص')}\n🆔 کد مشتری: {customer_code}\n💳 بدهی فعلی: {format_price(total_payable)} تومان"
        )
        if os.path.exists(image_path):
            os.remove(image_path)
        last_invoice_for_admin[user_id] = {
            'message_id': admin_msg.message_id,
            'chat_id': ADMIN_CHAT_ID,
            'user_name': customer.get('name', 'نامشخص'),
            'total_payable': total_payable,
            'invoice_number': invoice_number
        }
        print(f"✅ فاکتور به حسابدار ارسال شد برای کاربر {user_id} با message_id: {admin_msg.message_id}")
    except Exception as e:
        print(f"⚠️ خطا در ارسال فاکتور به حسابدار: {e}")
    ثبت_سفارش_در_شیت(customer, items_list, total, invoice_number, customer_code)
    customer_debts[user_id] = total_payable
    cart['items'] = []
    cart['customer'] = {}
    cart['step'] = 'idle'
    menu_keypad = ChatKeypadBuilder() \
        .row(ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات")) \
        .row(ChatKeypadBuilder().button(id="search", text="🔍 جستجو")) \
        .row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید")) \
        .row(ChatKeypadBuilder().button(id="help", text="📋 راهنما")) \
        .build()
    await message.reply_keypad(
        "✅ **سفارش شما با موفقیت ثبت شد!**\n\n"
        f"🆔 **کد مشتری شما: {customer_code}**\n"
        "🔄 برای سفارش جدید، از منوی زیر استفاده کنید.\n"
        f"💳 **بدهی شما: {format_price(total_payable)} تومان**\n\n"
        "📱 **برای تسویه حساب، پیامک تراکنش را همراه با مبلغ به این حساب ارسال کنید.**",
        menu_keypad
    )

# ============================================================
# 🤖 ساخت ربات و هندلرها (بدون تغییر)
# ============================================================

bot = Robot(token=TOKEN)

@bot.on_message()
async def handle_message(bot: Robot, message: Message):
    # (بدون تغییر، از کد قبلی استفاده کنید)
    pass

@bot.on_callback()
async def handle_callback(bot: Robot, message: Message):
    # (بدون تغییر، از کد قبلی استفاده کنید)
    pass

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
