import os
import sys
import time
import socket
import tldextract
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import cloudscraper
import requests
import random
import ssl
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Configure logging
import logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Web Scanning Definitions
PAYMENT_GATEWAYS = {
    "stripe": "Stripe", "adyen": "Adyen", "paypal": "PayPal", "braintree": "Braintree",
    "authorize.net": "Authorize.Net", "squareup": "Square", "klarna": "Klarna",
    "checkout.com": "Checkout.com", "razorpay": "Razorpay", "paytm": "Paytm",
    "shopify": "Shopify", "kindful": "Kindful", "worldpay": "Worldpay",
    "2checkout": "2Checkout", "merchant": "Merchant e-Solutions"
}

GATEWAYS_3D_NAMES = {
    "stripe": "Stripe", "adyen": "Adyen", "braintree": "Braintree",
    "authorize.net": "Authorize.Net", "checkout.com": "Checkout.com",
    "worldpay": "Worldpay", "paypal": "PayPal"
}

GATEWAY_KEYWORDS = {
    "stripe": ["stripe.com", "js.stripe.com", "api.stripe.com", "payment_methods", "charges", "payment_intent", "client_secret", "pi_", "stripe.js", "v1/", "3dsecure", "three_d_secure"],
    "paypal": ["paypal.com", "www.paypal.com", "zoid.paypal.com", "buttons", "paypal-sdk", "checkout.js", "three_d_secure"],
    "braintree": ["braintreepayments.com", "client_token", "braintree.dropin", "hosted_fields", "braintree.js", "three_d_secure"],
    "adyen": ["checkoutshopper-live.adyen.com", "adyen.js", "adyenEncrypted", "three_d_secure", "adyen-checkout"],
    "authorize.net": ["authorize.net/gateway/transact.dll", "transact.dll", "anet.js"],
    "squareup": ["squareup.com", "sqpaymentform", "square.js"],
    "klarna": ["klarna.com", "x.klarnacdn.net", "klarna_checkout", "klarna-payments"],
    "checkout.com": ["checkout.com", "cko.js", "three_d_secure"],
    "razorpay": ["checkout.razorpay.com", "razorpay.js", "razorpay-checkout"],
    "paytm": ["securegw.paytm.in", "paytm.js", "paytm-pg"],
    "shopify": ["cdn.shopify.com", "shopify_payments", "shopify-checkout"],
    "kindful": ["kindful.com", "kindful.js", "donation-form"],
    "worldpay": ["worldpay.com", "worldpay.js", "three_d_secure"],
    "2checkout": ["2checkout.com", "2co.js", "checkout-2co"],
    "merchant": ["merchant-esolutions.com", "mes.js", "payment-gateway"]
}

CAPTCHA_GROUPS = {
    "reCAPTCHA": ["gstatic.com/recaptcha", "recaptcha.net", "recaptcha"],
    "hCaptcha": ["hcaptcha.com", "hcaptcha.com/api.js", "hcaptcha_token"],
    "Cloudflare": ["cf-ray", "cf-cache-status", "cloudflare"],
    "Turnstile": ["turnstile"],
    "Arkose Labs": ["arkose.com", "arkose-labs"],
    "FunCaptcha": ["funcaptcha"],
    "Geetest": ["geetest.com", "challenge", "radar_options"]
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Mobile Safari/537.36',
]

# Telegram Bot Configurations
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_KEY = "Honda125786"
SPECIAL_KEY = "Honda125786"
PRIVATE_CHANNEL_ID = "@f2m3mm2euiaooplneh3eudj"
RESPONSE_CHANNEL_ID = "@mddj77273jdjdjd838383"
registered_users = {}
start_messages_shown = {}
credit_codes = {}
admin_authorized = False

requests.adapters.DEFAULT_POOLSIZE = 20
requests.adapters.DEFAULT_RETRIES = 5
requests.adapters.DEFAULT_POOL_TIMEOUT = 5.0

# Web Scanning Functions
def create_scraper():
    try:
        scraper = cloudscraper.create_scraper(browser={'custom': random.choice(USER_AGENTS)})
        scraper.mount('https://', requests.adapters.HTTPAdapter(max_retries=3))
        scraper.ssl_context = ssl.create_default_context()
        scraper.ssl_context.check_hostname = False
        scraper.ssl_context.verify_mode = ssl.CERT_NONE
        return scraper
    except Exception as e:
        logger.error(f"Error creating scraper: {str(e)}")
        return None

def fetch_url(url, max_retries=3):
    try:
        scraper = create_scraper()
        if not scraper:
            return None, url
        for attempt in range(max_retries):
            try:
                response = scraper.get(url, timeout=30)
                response.raise_for_status()
                html_content = response.text
                if not html_content.strip():
                    return None, url
                return html_content, url
            except requests.RequestException as e:
                logger.warning(f"[!] Error on attempt {attempt + 1} for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
        return None, url
    except Exception as e:
        logger.error(f"Unexpected error in fetch_url for {url}: {str(e)}")
        return None, url

def get_all_sources(url, html_content):
    try:
        if not html_content or not html_content.strip():
            return []
        soup = BeautifulSoup(html_content, 'html.parser')
        sources = []
        for script in soup.find_all('script'):
            src = script.get('src')
            if src:
                full_url = urljoin(url, src)
                sources.append(full_url)
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href:
                full_url = urljoin(url, href)
                sources.append(full_url)
        return sources
    except Exception as e:
        logger.error(f"Error parsing sources for {url}: {str(e)}")
        return []

def crawl(url, max_depth=2, visited=None):
    try:
        if visited is None:
            visited = set()
        if url in visited or max_depth < 0:
            return []
        visited.add(url)
        html_content, fetched_url = fetch_url(url)
        resources = []
        if html_content:
            resources.append((html_content, fetched_url))
            sources = get_all_sources(fetched_url, html_content)
            for source in sources:
                if urlparse(source).netloc:
                    sub_resources = crawl(source, max_depth - 1, visited)
                    resources.extend(sub_resources)
        return resources
    except Exception as e:
        logger.error(f"Error crawling {url}: {str(e)}")
        return []

def detect_gateways_and_captcha(html_content, file_url):
    try:
        if not html_content or not html_content.strip():
            return set(), set(), set(), False
        detected_gateways = set()
        detected_3d = set()
        detected_captcha_types = set()
        cf_detected = False

        for keyword, name in PAYMENT_GATEWAYS.items():
            for signal in GATEWAY_KEYWORDS.get(keyword, []):
                if signal in html_content.lower():
                    detected_gateways.add(name)
                    if any(three_d_signal in html_content.lower() for three_d_signal in ["3dsecure", "three_d_secure", "acs"]):
                        detected_3d.add(name)
                    break

        for captcha_type, indicators in CAPTCHA_GROUPS.items():
            if any(indicator in html_content.lower() for indicator in indicators):
                detected_captcha_types.add(captcha_type)

        cloudflare_identifiers = ['cloudflare', '__cfduid', '__cfruid', 'cf-ray', 'cf-chl-bypass', 'rocket-loader']
        if any(identifier in html_content.lower() for identifier in cloudflare_identifiers):
            cf_detected = True

        return detected_gateways, detected_3d, detected_captcha_types, cf_detected
    except Exception as e:
        logger.error(f"Error detecting gateways/captcha for {file_url}: {str(e)}")
        return set(), set(), set(), False

def get_ip(domain):
    try:
        return socket.gethostbyname(domain)
    except Exception:
        return "Unknown"

# Telegram Utility Functions
def format_time(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

def save_registered_users():
    try:
        pass  # Placeholder for saving to file or database
    except Exception as e:
        logger.error(f"Error saving registered users: {str(e)}")

def load_registered_users():
    try:
        pass  # Placeholder for loading from file or database
    except Exception as e:
        logger.error(f"Error loading registered users: {str(e)}")

# Telegram Bot Functions
async def start(update: Update, context: CallbackContext):
    try:
        chat_id = update.effective_chat.id
        if chat_id in start_messages_shown:
            return
        start_messages_shown[chat_id] = True

        if chat_id in registered_users:
            credits_left = registered_users[chat_id]['credits']
            active_time = format_time(time.time() - registered_users[chat_id]['start_time'])
            message = (
                f"Official Gateway Hunter Version 3.0\n[Send URL to hunt gateway]\n"
                f"use /cmds command to get help!\n\n"
                f"<b>User Info ℹ️</b>\nActive: {active_time}\nID: {chat_id}\n\n"
                f"Credits left: {credits_left}")
            buttons = [[InlineKeyboardButton("Credits", callback_data='credits')],
                       [InlineKeyboardButton("Owner", url="https://t.me/thewitchleak")]]
        else:
            message = (
                "Official Gateway Hunter Version 3.0\n[Send URL to hunt gateway]\n"
                "use /cmds command to get help!\n\n"
                "Please register to start using the bot.")
            buttons = [[InlineKeyboardButton("Register", callback_data='register')],
                       [InlineKeyboardButton("Owner", url="https://t.me/thewitchleak")]]

        reply_markup = InlineKeyboardMarkup(buttons)
        await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred. Please try again later.")

async def cmds(update: Update, context: CallbackContext):
    try:
        chat_id = update.effective_chat.id
        message = ("Redeem credits with credits code\n"
                   "/redeem {credit_code}\n"
                   "/credits to check credits information")
        await context.bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        logger.error(f"Error in cmds command: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred. Please try again later.")

async def button_click(update: Update, context: CallbackContext):
    try:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id

        if query.data == 'register':
            await register_user(chat_id, context)
        elif query.data == 'credits':
            await send_credits_info(chat_id, context)
    except Exception as e:
        logger.error(f"Error in button_click: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred. Please try again later.")

async def register_user(chat_id, context: CallbackContext):
    try:
        if chat_id in registered_users:
            await context.bot.send_message(chat_id=chat_id, text="Already Registered")
        else:
            registered_users[chat_id] = {'start_time': time.time(), 'credits': 10}
            save_registered_users()
            await send_user_info(chat_id, context)
            await context.bot.send_message(
                chat_id=chat_id,
                text="You have successfully registered\nSend URL to hunt gateway\n\nCredits left: 10")
    except Exception as e:
        logger.error(f"Error in register_user: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred during registration.")

async def send_user_info(chat_id, context: CallbackContext):
    try:
        active_time = format_time(time.time() - registered_users[chat_id]['start_time'])
        username = (await context.bot.get_chat(chat_id)).username
        message = (f"<b>User Info ℹ️</b>\nActive: {active_time}\nID: {chat_id}\n\n"
                   f"Credits left: 10\n"
                   f"User: @{username}")
        await context.bot.send_message(chat_id=PRIVATE_CHANNEL_ID, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error sending user info: {str(e)}")

async def echo(update: Update, context: CallbackContext):
    try:
        user_input = update.message.text.strip()
        chat_id = update.effective_chat.id

        if chat_id not in registered_users:
            await context.bot.send_message(chat_id=chat_id, text="Kindly register first")
            await start(update, context)
            return
        elif registered_users[chat_id]['credits'] <= 0:
            await context.bot.send_message(chat_id=chat_id, text="0 Credits left", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Owner", url="https://t.me/thewitchleak")]]))
            return

        normalized_url = user_input if user_input.startswith(('http://', 'https://')) else 'https://' + user_input
        parsed = tldextract.extract(normalized_url)
        if not (parsed.domain and parsed.suffix) or normalized_url.isdigit() or not any(c.isalpha() for c in normalized_url):
            await context.bot.send_message(chat_id=chat_id, text="Invalid URL! Please enter a valid website URL.")
            return

        start_time = time.time()
        resources = crawl(normalized_url)
        if not resources:
            if "discord.com" in normalized_url.lower():
                await context.bot.send_message(chat_id=chat_id, text="This site requires manual verification. Please check manually.")
            else:
                await context.bot.send_message(chat_id=chat_id, text="Failed to scan the website or no valid content retrieved.")
            return

        detected_gateways = set()
        detected_3d = set()
        detected_captcha_types = set()
        cf_detected = False
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(detect_gateways_and_captcha, html, file_url): file_url for html, file_url in resources}
            for future in as_completed(futures):
                gateways, gateways_3d, captcha_types, cf = future.result()
                detected_gateways.update(gateways)
                detected_3d.update(gateways_3d)
                detected_captcha_types.update(captcha_types)
                if cf:
                    cf_detected = True

        gateways_2d = detected_gateways - detected_3d
        elapsed = round(time.time() - start_time, 2)
        ip_address = get_ip(urlparse(normalized_url).netloc)

        result = (
            f"<b>Scan Results:</b>\n"
            f"<b>🟢Website URL:</b> {normalized_url}\n"
            f"<b>🌐Website IP:</b> {ip_address}\n"
            f"<b>⏱️Time Taken:</b> {elapsed} seconds\n"
            f"<b>🗿3D Gateway:</b> {', '.join(sorted(detected_3d)) if detected_3d else 'None'}\n"
            f"<b>🔥2D Gateway:</b> {', '.join(sorted(gateways_2d)) if gateways_2d else 'None'}\n"
            f"<b>🤖CAPTCHA Found:</b> {', '.join(sorted(detected_captcha_types)) if detected_captcha_types else 'None'}\n"
            f"<b>☁️Cloudflare Detected:</b> {'Yes' if cf_detected else 'No'}\n"
        )
        # Checked By and Credits left
        username = (await context.bot.get_chat(chat_id)).username
        credits_left = registered_users[chat_id]['credits']
        if username:
            result += f"<b>🆔Checked By ~</b> <a href='https://t.me/{username}'>{username}</a>\n"
            result += f"<b>💳Credits left:</b> {credits_left}"

        await context.bot.send_message(chat_id=chat_id, text=result, parse_mode=ParseMode.HTML)
        await context.bot.send_message(chat_id=RESPONSE_CHANNEL_ID, text=result, parse_mode=ParseMode.HTML)
        registered_users[chat_id]['credits'] -= 1
        save_registered_users()
    except Exception as e:
        logger.error(f"Error in echo command: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred while processing your request.")

async def redeem(update: Update, context: CallbackContext):
    try:
        chat_id = update.effective_chat.id
        if chat_id not in registered_users:
            await context.bot.send_message(chat_id=chat_id, text="Kindly register first")
            return

        if len(context.args) != 1:
            await context.bot.send_message(chat_id=chat_id, text="💳 Please provide a valid code 💳\n/redeem <credit code>")
            return

        code = context.args[0]
        if code in credit_codes:
            credits = credit_codes.pop(code)
            registered_users[chat_id]['credits'] += credits
            save_registered_users()
            await context.bot.send_message(chat_id=chat_id, text=f"🎉 Successfully redeemed {credits} credits 🎉")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Invalid code or Already Redeemed.")
    except Exception as e:
        logger.error(f"Error in redeem command: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred while redeeming the code.")

async def credits(update: Update, context: CallbackContext):
    try:
        await send_credits_info(update.effective_chat.id, context)
    except Exception as e:
        logger.error(f"Error in credits command: {str(e)}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="An error occurred while checking credits.")

async def send_credits_info(chat_id, context: CallbackContext):
    try:
        if chat_id in registered_users:
            credits_left = registered_users[chat_id]['credits']
            active_time = format_time(time.time() - registered_users[chat_id]['start_time'])
            message = (f"<b>👨‍✈️ User Info ℹ️</b>\nActive: {active_time}\nID: {chat_id}\n\n"
                       f"<b>💳 Credits left:</b> {credits_left}")
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=chat_id, text="Kindly register first")
    except Exception as e:
        logger.error(f"Error sending credits info: {str(e)}")

async def owner(update: Update, context: CallbackContext):
    try:
        owner_profile = "https://t.me/thewitchleak"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Owner profile: {owner_profile}")
    except Exception as e:
        logger.error(f"Error in owner command: {str(e)}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="An error occurred while fetching owner info.")

async def gen_code786(update: Update, context: CallbackContext):
    try:
        chat_id = update.effective_chat.id
        if not admin_authorized:
            await context.bot.send_message(chat_id=chat_id, text="Unauthorized access")
            return
        if len(context.args) != 2:
            await context.bot.send_message(chat_id=chat_id, text="Invalid arguments. Use /gen_code786 <code> <credits>")
            return
        code, credits = context.args[0], context.args[1]
        try:
            credits = int(credits)
            credit_codes[code] = credits
            await context.bot.send_message(chat_id=chat_id, text=f"Code {code} \n💳 generated with {credits} credits 💳")
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Invalid credits value")
    except Exception as e:
        logger.error(f"Error in gen_code command: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred while generating the code.")

async def authorize786(update: Update, context: CallbackContext):
    try:
        chat_id = update.effective_chat.id
        if len(context.args) != 1:
            await context.bot.send_message(chat_id=chat_id, text="Invalid arguments. Use /authorize <admin_key>")
            return
        admin_key = context.args[0]
        if admin_key == ADMIN_KEY:
            global admin_authorized
            admin_authorized = True
            await context.bot.send_message(chat_id=chat_id, text="Admin privileges granted")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Invalid admin key")
    except Exception as e:
        logger.error(f"Error in authorize command: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred during authorization.")

async def special(update: Update, context: CallbackContext):
    try:
        chat_id = update.effective_chat.id
        if len(context.args) != 1:
            await context.bot.send_message(chat_id=chat_id, text="Invalid arguments. Use /special <special_key>")
            return
        special_key = context.args[0]
        if special_key == SPECIAL_KEY:
            await context.bot.send_message(chat_id=chat_id, text="Special privileges granted")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Invalid special key")
    except Exception as e:
        logger.error(f"Error in special command: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text="An error occurred while processing special command.")

# Initialize the bot
try:
    load_registered_users()
    application = Application.builder().token(TOKEN).build()

    # Add handlers directly to the application
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cmds", cmds))
    application.add_handler(CommandHandler("redeem", redeem))
    application.add_handler(CommandHandler("credits", credits))
    application.add_handler(CommandHandler("owner", owner))
    application.add_handler(CommandHandler("gen_code786", gen_code786))
    application.add_handler(CommandHandler("authorize786", authorize786))
    application.add_handler(CommandHandler("special", special))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Start the bot with basic error handling
    application.run_polling()
except Exception as e:
    logger.error(f"Bot failed to start: {str(e)}")
    sys.exit(1)

if __name__ == "__main__":
    pass
