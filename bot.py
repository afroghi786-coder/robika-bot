# ============================================================
# 🤖 ربات فروشگاهی - نسخه نهایی با ذخیره‌سازی و به‌روزرسانی قیمت
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

# ============================================================
# 📦 ذخیره‌سازی دائمی محصولات (با قابلیت به‌روزرسانی قیمت)
# ============================================================

PRODUCTS_FILE = "products.json"

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

TOKEN = ""
BOT_USERNAME = "FroghiShopBot"
ADMIN_CHAT_ID = "b0HWCJJ0xHE0e4e078b6c5228504866a"

# ============================================================
# 📦 حافظه
# ============================================================

all_products = load_products()  # ← بارگذاری از فایل
carts = {}
customer_debts = {}
customer_codes = {}
invoice_counter = 0
customer_counter = 3000
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
    return f"{num:,}".replace(',', '٬')

def generate_invoice_number():
    global invoice_counter
    invoice_counter += 1
    now = datetime.now()
    return f"M_{now.strftime('%Y%m%d')}{invoice_counter:04d}"

def get_or_create_customer_code(phone):
    global customer_counter
    phone = phone.replace(' ', '').replace('-', '')
    if phone in customer_codes:
        return customer_codes[phone]
    customer_counter += 1
    code = f"MO_{customer_counter}"
    customer_codes[phone] = code
    return code

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
# 🖼️ تولید فاکتور
# ============================================================

def create_invoice_image(customer, items, total, previous_debt, invoice_number, customer_code):
    width = 1400
    height = 250 + len(items) * 80 + 350
    if previous_debt > 0:
        height += 80
    
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    font_paths = [
        "C:/Windows/Fonts/B_Nazanin.ttf",
        "C:/Windows/Fonts/B_Titr.ttf",
        "C:/Windows/Fonts/B_Yas.ttf",
        "C:/Windows/Fonts/B_Mitra.ttf",
        "C:/Windows/Fonts/B_Koodak.ttf",
        "C:/Windows/Fonts/arial.ttf"
    ]
    
    font_found = None
    for path in font_paths:
        if os.path.exists(path):
            font_found = path
            break
    
    if font_found:
        try:
            font_title = ImageFont.truetype(font_found, 44)
            font_header = ImageFont.truetype(font_found, 32)
            font_normal = ImageFont.truetype(font_found, 24)
            font_bold = ImageFont.truetype(font_found, 28)
            font_footer = ImageFont.truetype(font_found, 34)
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
    
    y = 30
    
    if os.path.exists("logo.png"):
        try:
            logo = Image.open("logo.png")
            logo = logo.resize((180, 140))
            image.paste(logo, (30, 15))
        except:
            pass
    
    draw.text((350, 30), get_display(arabic_reshaper.reshape("🧾 فاکتور فروش")), fill=(0, 0, 0), font=font_title)
    draw.text((350, 85), get_display(arabic_reshaper.reshape(f"تاریخ: {datetime.now().strftime('%Y/%m/%d')}")), fill=(80, 80, 80), font=font_header)
    draw.text((950, 30), get_display(arabic_reshaper.reshape(f"شماره فاکتور: {invoice_number}")), fill=(0, 0, 0), font=font_header)
    draw.text((950, 75), get_display(arabic_reshaper.reshape(f"کد مشتری: {customer_code}")), fill=(0, 0, 150), font=font_header)
    
    y = 170
    
    draw.rectangle([(30, y), (1370, y+110)], outline=(200, 200, 200), width=2)
    draw.text((40, y+25), get_display(arabic_reshaper.reshape(f"👤 مشتری: {customer.get('name', 'نامشخص')}")), fill=(0, 0, 0), font=font_normal)
    draw.text((40, y+65), get_display(arabic_reshaper.reshape(f"📞 تلفن: {customer.get('phone', 'نامشخص')}")), fill=(0, 0, 0), font=font_normal)
    draw.text((600, y+25), get_display(arabic_reshaper.reshape(f"📍 آدرس: {customer.get('address', 'نامشخص')}")), fill=(0, 0, 0), font=font_normal)
    draw.text((600, y+65), get_display(arabic_reshaper.reshape(f"🚚 باربری: {customer.get('shipping', 'نامشخص')}")), fill=(0, 0, 0), font=font_normal)
    
    y += 150
    
    draw.rectangle([(30, y), (1370, y+60)], fill=(50, 50, 50))
    draw.text((40, y+15), get_display(arabic_reshaper.reshape("ردیف")), fill=(255, 255, 255), font=font_bold)
    draw.text((150, y+15), get_display(arabic_reshaper.reshape("نام محصول")), fill=(255, 255, 255), font=font_bold)
    draw.text((700, y+15), get_display(arabic_reshaper.reshape("تعداد")), fill=(255, 255, 255), font=font_bold)
    draw.text((850, y+15), get_display(arabic_reshaper.reshape("قیمت واحد")), fill=(255, 255, 255), font=font_bold)
    draw.text((1100, y+15), get_display(arabic_reshaper.reshape("مبلغ کل")), fill=(255, 255, 255), font=font_bold)
    
    y += 60
    
    for i, item in enumerate(items, 1):
        if i % 2 == 0:
            draw.rectangle([(30, y), (1370, y+65)], fill=(240, 240, 240))
        draw.text((40, y+20), str(i), fill=(0, 0, 0), font=font_normal)
        draw.text((150, y+20), get_display(arabic_reshaper.reshape(item['name'][:30])), fill=(0, 0, 0), font=font_normal)
        draw.text((700, y+20), str(item['quantity']), fill=(0, 0, 0), font=font_normal)
        draw.text((850, y+20), format_price(item['price_per_pair']), fill=(0, 0, 0), font=font_normal)
        draw.text((1100, y+20), format_price(item['subtotal']), fill=(0, 0, 0), font=font_normal)
        y += 65
    
    draw.line([(30, y), (1370, y)], fill=(200, 200, 200), width=3)
    y += 35
    
    draw.text((800, y), get_display(arabic_reshaper.reshape(f"💰 جمع سفارش جدید: {format_price(total)} تومان")), fill=(0, 0, 200), font=font_bold)
    y += 60
    
    if previous_debt > 0:
        draw.text((800, y), get_display(arabic_reshaper.reshape(f"💳 بدهی قبلی: {format_price(previous_debt)} تومان")), fill=(200, 0, 0), font=font_bold)
        y += 60
        draw.text((800, y), get_display(arabic_reshaper.reshape(f"💳 مبلغ قابل پرداخت: {format_price(total + previous_debt)} تومان")), fill=(0, 150, 0), font=font_bold)
    else:
        draw.text((800, y), get_display(arabic_reshaper.reshape(f"💰 مبلغ قابل پرداخت: {format_price(total)} تومان")), fill=(0, 150, 0), font=font_bold)
    
    y += 100
    draw.text((40, y), get_display(arabic_reshaper.reshape("🙏 از اعتماد شما سپاسگزاریم!")), fill=(100, 100, 100), font=font_footer)
    
    filename = f"invoices/invoice_{invoice_number}.png"
    os.makedirs("invoices", exist_ok=True)
    image.save(filename, "PNG", quality=95, dpi=(300, 300))
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
# 📤 نمایش لیست محصولات (عادی)
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
# 🔍 جستجوی زنده (Live Search)
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
            'total_payable': total_payable
        }
        print(f"✅ فاکتور به حسابدار ارسال شد برای کاربر {user_id} با message_id: {admin_msg.message_id}")
    except Exception as e:
        print(f"⚠️ خطا در ارسال فاکتور به حسابدار: {e}")
    
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
# 🤖 ساخت ربات
# ============================================================

bot = Robot(token=TOKEN)

# ============================================================
# 📩 وقتی پیام میاد
# ============================================================

@bot.on_message()
async def handle_message(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.author_guid
    text = message.text if message.text else ''
    
    print(f"📩 پیام از: {chat_id}")
    print(f"📝 متن: {text[:100] if text else '(خالی)'}")
    
    if chat_id.startswith('c0'):
        product = detect_product(text)
        if not product:
            print("❌ محصول تشخیص داده نشد!")
            return
        
        # ✅ بخش جدید: به‌روزرسانی قیمت در صورت تکراری بودن
        found = False
        for i, p in enumerate(all_products):
            if p['name'] == product['name']:
                # به‌روزرسانی قیمت و تعداد جفت
                all_products[i]['price'] = product['price']
                all_products[i]['pairCount'] = product.get('pairCount', 0)
                save_products(all_products)
                print(f"🔄 قیمت محصول {product['name']} به {format_price(product['price'])} تومان به‌روز شد!")
                found = True
                break
        
        if not found:
            all_products.append(product)
            save_products(all_products)
            print(f"✅ محصول جدید: {product['name']} - قیمت: {format_price(product['price'])}")
        
        await send_link_to_channel(chat_id, product)
        return
    
    if chat_id.startswith('b0'):
        cart = get_cart(user_id)
        
        if text == '/start' or text == 'start':
            menu_keypad = ChatKeypadBuilder() \
                .row(ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات")) \
                .row(ChatKeypadBuilder().button(id="search", text="🔍 جستجو")) \
                .row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید")) \
                .row(ChatKeypadBuilder().button(id="help", text="📋 راهنما")) \
                .build()
            await message.reply_keypad(
                "🏠 **به فروشگاه خوش آمدید!**\n\nاز منوی زیر انتخاب کنید:",
                menu_keypad
            )
            return
        
        if text == '/myid':
            await message.reply(f"🆔 **آیدی عددی شما:**\n`{user_id}`\n\n🔹 شناسه چت شما: `{chat_id}`")
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
                await show_products_list(message, user_id)
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
            print(f"🔍 پیام از حسابدار با reply_to_message_id: {message.reply_to_message_id}")
            
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
                        new_debt = max(0, current_debt - amount)
                        customer_debts[found_user] = new_debt
                        
                        await message.reply(
                            f"✅ **تسویه حساب انجام شد!**\n\n"
                            f"👤 کاربر: {found_info['user_name']}\n"
                            f"💰 مبلغ واریز: {format_price(amount)} تومان\n"
                            f"💳 بدهی جدید: {format_price(new_debt)} تومان"
                        )
                        
                        try:
                            await bot.send_message(
                                chat_id=found_user,
                                text=f"✅ **تسویه حساب شما تایید شد!**\n"
                                     f"💰 مبلغ واریز: {format_price(amount)} تومان\n"
                                     f"💳 بدهی جدید: {format_price(new_debt)} تومان"
                            )
                        except Exception as e:
                            print(f"⚠️ خطا در ارسال پیام به کاربر: {e}")
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
                        text=f"📱 **پیامک تراکنش از مشتری:**\n"
                             f"👤 کاربر: {invoice_info['user_name']}\n"
                             f"💰 مبلغ: {format_price(amount)} تومان\n"
                             f"📝 شماره تراکنش: {text[:100]}",
                        reply_to_message_id=invoice_info['message_id']
                    )
                    await message.reply("✅ پیامک تراکنش شما به حسابدار ارسال شد. پس از تایید، بدهی شما به‌روزرسانی می‌شود.")
                    print(f"✅ پیامک تراکنش به فاکتور حسابدار ریپلای شد برای کاربر {user_id}")
                except Exception as e:
                    print(f"⚠️ خطا در ارسال ریپلای: {e}")
                    await message.reply("⚠️ خطا در ارسال پیامک به حسابدار. لطفاً دوباره تلاش کنید.")
                return
            else:
                await message.reply(
                    "📋 **منوی اصلی:**\n"
                    "از دکمه‌های زیر استفاده کنید.\n"
                    "برای جستجو، روی 🔍 جستجو کلیک کنید."
                )
                return

# ============================================================
# 🎯 پردازش کلیک دکمه‌ها
# ============================================================

@bot.on_callback()
async def handle_callback(bot: Robot, message: Message):
    chat_id = message.chat_id
    user_id = message.author_guid
    data = message.data
    
    cart = get_cart(user_id)
    
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
        menu_keypad = ChatKeypadBuilder() \
            .row(ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات")) \
            .row(ChatKeypadBuilder().button(id="search", text="🔍 جستجو")) \
            .row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید")) \
            .row(ChatKeypadBuilder().button(id="help", text="📋 راهنما")) \
            .build()
        await message.reply_keypad("🏠 **منوی اصلی:**", menu_keypad)
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
        await show_products_list(message, user_id)
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
            f"📦 **{product['name']}**\n"
            f"💰 قیمت هر جفت: {format_price(product['price'])} تومان\n"
            f"📦 تعداد جفت: {product.get('pairCount', 'نامشخص')}\n\n"
            f"🔢 **تعداد کارتن مورد نظر را وارد کنید:**"
        )
        return
    
    if data == 'show_cart':
        if len(cart['items']) == 0:
            await message.reply("🛒 سبد خرید شما خالی است!")
            return
        
        text = "🛒 **سبد خرید شما:**\n\n"
        total = 0
        for i, item in enumerate(cart['items'], 1):
            pair_count = item.get('pairCount', 1)
            subtotal = item['price'] * pair_count * item['quantity']
            total += subtotal
            text += f"{i}. {item['name']}\n"
            text += f"   تعداد کارتن: {item['quantity']}\n"
            text += f"   تعداد جفت: {pair_count}\n"
            text += f"   قیمت هر جفت: {format_price(item['price'])} تومان\n"
            text += f"   مجموع: {format_price(subtotal)} تومان\n\n"
        
        text += f"━━━━━━━━━━━━━━━━\n"
        text += f"💰 **جمع کل: {format_price(total)} تومان**\n\n"
        
        keypad_builder = ChatKeypadBuilder()
        for i, item in enumerate(cart['items'], 1):
            keypad_builder.row(ChatKeypadBuilder().button(id=f"remove_{item['name']}", text=f"🗑️ حذف {item['name']}"))
        keypad_builder.row(ChatKeypadBuilder().button(id="checkout", text="✅ نهایی‌سازی سفارش"))
        keypad_builder.row(ChatKeypadBuilder().button(id="clear_cart", text="🗑️ خالی کردن سبد"))
        keypad_builder.row(ChatKeypadBuilder().button(id="back_menu", text="🔙 بازگشت به منو"))
        
        keypad = keypad_builder.build()
        await message.reply_keypad(text, keypad)
        return
    
    if data.startswith('remove_'):
        product_name = data.replace('remove_', '')
        cart['items'] = [item for item in cart['items'] if item['name'] != product_name]
        await message.reply(f"🗑️ {product_name} از سبد خرید حذف شد.")
        await handle_callback(bot, message)
        return
    
    if data == 'clear_cart':
        cart['items'] = []
        await message.reply("🗑️ سبد خرید شما خالی شد.")
        menu_keypad = ChatKeypadBuilder() \
            .row(ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات")) \
            .row(ChatKeypadBuilder().button(id="search", text="🔍 جستجو")) \
            .row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید")) \
            .row(ChatKeypadBuilder().button(id="help", text="📋 راهنما")) \
            .build()
        await message.reply_keypad("🏠 **منوی اصلی:**", menu_keypad)
        return
    
    if data == 'checkout':
        if len(cart['items']) == 0:
            await message.reply("❌ سبد خرید خالی است!")
            return
        cart['step'] = 'waiting_customer_name'
        await message.reply(
            "✅ **مرحله نهایی‌سازی سفارش**\n\n"
            "لطفاً اطلاعات زیر را وارد کنید:\n\n"
            "1️⃣ **نام و نام خانوادگی:**"
        )
        return
    
    if data == 'back_menu':
        menu_keypad = ChatKeypadBuilder() \
            .row(ChatKeypadBuilder().button(id="show_products", text="📦 مشاهده محصولات")) \
            .row(ChatKeypadBuilder().button(id="search", text="🔍 جستجو")) \
            .row(ChatKeypadBuilder().button(id="show_cart", text="🛒 سبد خرید")) \
            .row(ChatKeypadBuilder().button(id="help", text="📋 راهنما")) \
            .build()
        await message.reply_keypad("🏠 **منوی اصلی:**", menu_keypad)
        return
    
    if data == 'help':
        await message.reply(
            "📋 **راهنمای فروشگاه:**\n\n"
            "1️⃣ از منوی اصلی، **مشاهده محصولات** یا **جستجو** را انتخاب کنید.\n"
            "2️⃣ در جستجو، حروف را انتخاب کنید تا محصولات فیلتر شوند.\n"
            "3️⃣ روی محصول مورد نظر کلیک کنید و تعداد کارتن را وارد کنید.\n"
            "4️⃣ **بدون برگشت به منو**، محصول بعدی را انتخاب کنید.\n"
            "5️⃣ در انتها **سبد خرید** را باز کنید.\n"
            "6️⃣ می‌توانید هر محصول را حذف کنید یا سبد را خالی کنید.\n"
            "7️⃣ **نهایی‌سازی** را بزنید و مشخصات خود را وارد کنید.\n"
            "8️⃣ فاکتور تصویری با کیفیت بالا نمایش داده می‌شود.\n"
            "9️⃣ برای تسویه حساب، پیامک تراکنش را همراه با مبلغ به این حساب ارسال کنید."
        )
        return
    
    await message.reply("❌ دکمه نامعتبر!")

# ============================================================
# 🚀 اجرا
# ============================================================

if __name__ == "__main__":
    print("✅ ربات فروشگاه روشن شد...")
    os.makedirs('invoices', exist_ok=True)
    os.makedirs('payments', exist_ok=True)
    bot.run()
