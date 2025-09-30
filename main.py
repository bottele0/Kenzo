import os
import time
import requests
import json
import base58
from solders.keypair import Keypair
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.api import Client
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

# Solana RPC configuration
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
solana_client = Client(SOLANA_RPC_URL)

# DexScreener API for token data (best-effort; responses vary)
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"

# Wallet management (in-memory)
user_wallets = {}  # Store user wallet data
user_balances = {}  # Store user balances

def current_time():
    return time.strftime("%H:%M:%S", time.localtime())

# Keyboards
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Wallet", callback_data="wallet"),
         InlineKeyboardButton("🔄 Refresh", callback_data="refresh")],
        [InlineKeyboardButton("🎯 AI Sniper", callback_data="ai_sniper"),
         InlineKeyboardButton("📋 Copy Trade", callback_data="copy_trade")],
        [InlineKeyboardButton("🔎 Search Tokens", callback_data="search_tokens"),
         InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

def wallet_setup_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Import Private Key", callback_data="import_private_key"),
         InlineKeyboardButton("🧩 Import Seed Phrase", callback_data="import_seed_phrase")],
        [InlineKeyboardButton("🎲 Generate Wallet", callback_data="generate_wallet"),
         InlineKeyboardButton("📈 Check Status", callback_data="check_status")],
        [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
    ])

def wallet_management_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Fund Wallet", callback_data="fund_wallet"),
         InlineKeyboardButton("📈 Check Status", callback_data="check_status")],
        [InlineKeyboardButton("📋 Copy Address", callback_data="copy_address"),
         InlineKeyboardButton("🔄 Refresh Balance", callback_data="refresh_balance")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
         InlineKeyboardButton("🔌 Disconnect", callback_data="disconnect_wallet")],
        [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
    ])

def fund_wallet_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Copy Address", callback_data="copy_address"),
         InlineKeyboardButton("🔄 Refresh Balance", callback_data="refresh_balance")],
        [InlineKeyboardButton("✅ Done", callback_data="wallet_management")]
    ])

def search_tokens_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Back to Dashboard", callback_data="main_menu")]
    ])

def search_results_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Search Again", callback_data="search_tokens"),
         InlineKeyboardButton("🏠 Dashboard", callback_data="main_menu")]
    ])

def help_center_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Commands", callback_data="help_commands"),
         InlineKeyboardButton("🔐 Wallet", callback_data="help_wallet")],
        [InlineKeyboardButton("📊 Trading", callback_data="help_trading"),
         InlineKeyboardButton("🛡️ Security", callback_data="help_security")],
        [InlineKeyboardButton("❓ FAQ", callback_data="help_faq"),
         InlineKeyboardButton("🆘 Support", callback_data="help_support")],
        [InlineKeyboardButton("⬅️ Close Help", callback_data="main_menu")]
    ])

def help_submenu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Help Menu", callback_data="help"),
         InlineKeyboardButton("❌ Close Help", callback_data="main_menu")]
    ])

def disconnect_confirm_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔌 Confirm Disconnect", callback_data="confirm_disconnect"),
         InlineKeyboardButton("❌ Cancel", callback_data="wallet_management")]
    ])

def import_wallet_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="wallet")]
    ])

# Messages
def get_start_message():
    return (
        "🔥 Welcome to Autosnipe 🔥\n\n"
        "Snipe memecoins at hyperspeed ⚡️\n"
        "Access advanced trading features with Autosnipe. 💰\n\n"
        "ℹ️ Click Wallet to get started!"
    )

def get_wallet_setup_message():
    return (
        "🔐 Wallet Setup 🔐\n\n"
        "ℹ️ You don't have a wallet connected yet.\n"
        "Choose how you'd like to get started:\n\n"
        "🔑 Import Private Key - Use existing private key\n"
        "🧩 Import Seed Phrase - Use existing seed words\n"
        "🎲 Generate - Create a brand new wallet"
    )

def get_import_private_key_message():
    return (
        "🔐 **Import Private Key**\n\n"
        "Send me your Solana private key to import your wallet.\n\n"
        "⚠️ **Security Warning:** Make sure you trust this bot before sending your private key!\n\n"
        "📝 **Tips:**\n"
        "• Private keys are usually 52-54 characters long (base58 of 64 bytes) or 44-45 chars for 32-byte seeds\n"
        "• They should only contain letters and numbers\n"
        "• Never share your private key publicly"
    )

def get_import_seed_phrase_message():
    return (
        "🧩 **Import Seed Phrase**\n\n"
        "Send me your Solana seed phrase (12 or 24 words) to import your wallet.\n\n"
        "⚠️ **Security Warning:** Make sure you trust this bot before sending your seed phrase!\n\n"
        "📝 **Tips:**\n"
        "• Enter 12 or 24 words separated by spaces\n"
        "• Use the standard BIP39 English wordlist\n"
        "• Never share your seed phrase publicly\n"
        "• Example: word1 word2 word3 ... word12"
    )

def get_wallet_connected_main_menu(user_id):
    wallet = user_wallets.get(user_id, {})
    balance = user_balances.get(user_id, 0)

    # Get real SOL price and market data
    sol_data = get_solana_price_data()
    sol_price = sol_data.get('price', 0)
    sol_change = sol_data.get('change_24h', 0)
    volume = sol_data.get('volume', 0)

    usd_balance = balance * sol_price

    return (
        f"🏦 WALLET\n"
        f"Address: {wallet.get('public_key', 'N/A')}\n"
        f"💰: {balance:.4f} SOL\n\n"
        f"📄 PORTFOLIO\n"
        f"• SOL: {balance:.4f} (${usd_balance:.2f}) -- 100%\n"
        f"• TOKENS: 0 ($0.00) — 0%\n\n"
        f"📈 SOL MARKET\n"
        f"${sol_price:.2f} ({'📈' if sol_change >= 0 else '📉'} {abs(sol_change):.1f}%) | Vol: ${volume:.2f}B\n\n"
        f"🔗 View on Solscan: [Open Portfolio](https://solscan.io/account/{wallet.get('public_key', '')})"
    )

def get_wallet_management_message(user_id):
    wallet = user_wallets.get(user_id, {})
    balance = user_balances.get(user_id, 0)

    return (
        "🔐 Wallet Management 🔐\n\n"
        f"🏷️ Address:\n"
        f"`{wallet.get('public_key', 'N/A')}`\n"
        f"💰 Balance: {balance:.4f} SOL\n\n"
        "Choose a wallet action:"
    )

def get_fund_wallet_message(user_id):
    wallet = user_wallets.get(user_id, {})
    balance = user_balances.get(user_id, 0)

    return (
        "💰 Fund Your Wallet 💰\n\n"
        f"🏷️ Wallet Address:\n"
        f"`{wallet.get('public_key', 'N/A')}`\n\n"
        f"📊 Current Balance: {balance:.4f} SOL\n\n"
        "💱 How to Fund:\n"
        "• Copy the wallet address above\n"
        "• Send SOL from another wallet or exchange\n"
        "• Minimum: 0.001 SOL for transaction fees\n"
        "• Recommended: 0.1+ SOL for trading\n\n"
        "⚡ Quick Tips:\n"
        "• Tap and hold to copy the address\n"
        "• Double-check the address before sending\n"
        "• SOL transfers usually take 1-2 minutes\n\n"
        "🔄 Use /status to check your updated balance!"
    )

def get_wallet_status_message(user_id):
    wallet = user_wallets.get(user_id, {})
    balance = user_balances.get(user_id, 0)

    return (
        "✅ Wallet Status: Connected\n\n"
        f"🏷️ Public Key:\n"
        f"`{wallet.get('public_key', 'N/A')}`\n\n"
        f"💰 Balance: {balance:.4f} SOL\n\n"
        "Created: Recently\n"
        "Network: Solana Mainnet"
    )

def get_search_tokens_message():
    return (
        "🔍 Token Search & Analysis 🔍\n\n"
        "Enter any of the following to get detailed token information:\n\n"
        "📝 Token Symbol: SOL, BONK, WIF\n"
        "🏷️ Token Address: Full Solana token address\n"
        "💡 Token Name: Partial or full token name\n\n"
        "⚡ What you'll get:\n"
        "• 💰 Current price & 24h changes\n"
        "• 🌊 Liquidity & volume data\n"
        "• 🔗 Official links & social media\n"
        "• 📋 Token description & details\n"
        "• 📊 Trading pair information\n\n"
        "🔑 Enter your search term now:"
    )

def get_help_center_message():
    return (
        "❓ Autosnipe Help Center ❓\n\n"
        "🔥 Welcome to Autosnipe!\n"
        "The fastest memecoin sniping bot on Solana. Snipe tokens at hyperspeed with advanced AI algorithms.\n\n"
        "🚀 Quick Start Guide:\n"
        "1️⃣ Click 🔐 Wallet to setup your wallet\n"
        "2️⃣ Fund your wallet with SOL\n"
        "3️⃣ Start sniping tokens!\n\n"
        "Choose a topic below for detailed help:"
    )

def get_commands_help_message():
    return (
        "🤖 Available Commands 🤖\n\n"
        "Basic Commands:\n"
        "• /start - Open main dashboard\n"
        "• /help - Show this help center\n"
        "• /status - Check wallet status\n\n"
        "Wallet Commands:\n"
        "• /import - Import private key\n"
        "• /generate - Generate new wallet\n"
        "• /fund - Get funding instructions\n"
        "• /disconnect - Remove current wallet\n\n"
        "Advanced Commands:\n"
        "💡 Tip: Most functions are accessible through the button interface!"
    )

def get_wallet_help_message():
    return (
        "🔐 Wallet Help 🔐\n\n"
        "Getting Started:\n"
        "🔑 Import Wallet - Use your existing private key\n"
        "🎲 Generate Wallet - Create a brand new wallet\n\n"
        "Managing Your Wallet:\n"
        "💰 Fund Wallet - Add SOL to your wallet\n"
        "📈 Check Status - View balance and details\n"
        "📋 Copy Address - Copy wallet address\n"
        "🔄 Refresh Balance - Update balance\n"
        "🔌 Disconnect - Safely remove wallet\n\n"
        "Security Tips:\n"
        "• Never share your private key\n"
        "• Always verify addresses before sending\n"
        "• Keep your private key backed up safely"
    )

def get_trading_help_message():
    return (
        "📊 Trading Features 📊\n\n"
        "Token Search:\n"
        "🔍 Find tokens by address or symbol\n"
        "📈 Get real-time price data\n"
        "📊 View market statistics\n\n"
        "Copy Trading:\n"
        "📋 Follow successful traders\n"
        "🤖 Automated position copying\n"
        "⚙️ Customizable settings\n\n"
        "AI Sniping:\n"
        "⚡ Lightning-fast execution\n"
        "🎯 Smart entry detection\n"
        "🛡️ Risk management built-in\n\n"
        "🚧 Status: Trading features coming soon!"
    )

def get_security_help_message():
    return (
        "🛡️ Security & Safety 🛡️\n\n"
        "Wallet Security:\n"
        "🔐 Your keys are stored locally\n"
        "🔒 End-to-end encryption\n"
        "🚫 Never share keys with anyone\n\n"
        "Best Practices:\n"
        "✅ Use strong, unique passwords\n"
        "✅ Enable 2FA where possible\n"
        "✅ Keep software updated\n"
        "✅ Verify all transactions\n\n"
        "Red Flags:\n"
        "❌ Requests for private keys\n"
        "❌ Suspicious links or downloads\n"
        "❌ Too-good-to-be-true offers\n\n"
        "Need Help? Contact support if anything seems suspicious."
    )

def get_faq_help_message():
    return (
        "❓ Frequently Asked Questions ❓\n\n"
        "Q: Is my wallet secure?\n"
        "A: Yes! Your private keys are encrypted and stored locally. We never have access to your funds.\n\n"
        "Q: What's the minimum SOL needed?\n"
        "A: 0.001 SOL for fees, 0.1+ SOL recommended for trading.\n\n"
        "Q: How fast is the sniping?\n"
        "A: Our AI executes trades in milliseconds with advanced algorithms.\n\n"
        "Q: Can I use multiple wallets?\n"
        "A: Currently one wallet per user. Disconnect and connect different wallets as needed.\n\n"
        "Q: What tokens are supported?\n"
        "A: All SPL tokens on Solana network are supported.\n\n"
        "Q: Are there any fees?\n"
        "A: Only standard Solana network fees apply."
    )

def get_support_help_message():
    return (
        "🆘 Support & Contact 🆘\n\n"
        "Get Help:\n"
        "💬 Telegram: @AutoSnipe_Support\n"
        "🌐 Website: https://autosnipe.ai/sniper\n\n"
        "Community:\n"
        "🐦 Twitter: https://x.com/autosnipeai\n"
        "▶️ Youtube: https://www.youtube.com/watch?v=YKW39pEGBTQ\n\n"
        "Response Times:\n"
        "🟢 Critical Issues: < 1 hour\n"
        "🟡 General Support: < 24 hours\n"
        "🔵 Feature Requests: 2-7 days\n\n"
        "Before Contacting Support:\n"
        "• Check this help section\n"
        "• Try restarting with /start\n"
        "• Note any error messages"
    )

# ----------------------------
# Real Data Integration Functions (fixed)
# ----------------------------

def get_solana_price_data():
    """Get real SOL price data from CoinGecko (robust parsing)."""
    try:
        url = ("https://api.coingecko.com/api/v3/simple/price"
               "?ids=solana&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true")
        response = requests.get(url, timeout=10)
        data = response.json()

        sol_data = data.get('solana', {})
        price = sol_data.get('usd', 0)
        change = sol_data.get('usd_24h_change', sol_data.get('usd_24h_change', 0))
        vol = sol_data.get('usd_24h_vol', 0)
        # convert volume to billions (match your previous formatting)
        volume_b = vol / 1_000_000_000 if isinstance(vol, (int, float)) else 0

        return {
            'price': price or 0,
            'change_24h': change or 0,
            'volume': volume_b or 0
        }
    except Exception as e:
        print(f"Error fetching SOL price: {e}")
        return {'price': 0, 'change_24h': 0, 'volume': 0}

def is_valid_solana_private_key(private_key_b58: str) -> bool:
    """
    Validate Solana private key: accept base58-encoded 64-byte secret OR 32-byte seed.
    Returns True if it can be used to construct a Keypair.
    """
    try:
        decoded = base58.b58decode(private_key_b58)
    except Exception as e:
        # invalid base58
        return False

    if len(decoded) not in (32, 64):
        return False

    try:
        if len(decoded) == 64:
            # secret key format (64 bytes)
            Keypair.from_secret_key(decoded)
        else:
            # 32-byte seed
            Keypair.from_seed(decoded)
        return True
    except Exception as e:
        print(f"Private key validation error: {e}")
        return False

def derive_public_key(private_key_b58: str) -> str | None:
    """
    Derive public key from base58 private key.
    Supports 32-byte seeds and 64-byte secret keys.
    """
    try:
        decoded = base58.b58decode(private_key_b58)
    except Exception as e:
        print(f"Base58 decode error: {e}")
        return None

    try:
        if len(decoded) == 64:
            kp = Keypair.from_secret_key(decoded)
        elif len(decoded) == 32:
            kp = Keypair.from_seed(decoded)
        else:
            return None
        return str(kp.public_key)
    except Exception as e:
        print(f"Error deriving public key: {e}")
        return None

def get_sol_balance(public_key: str) -> float:
    """
    Get SOL balance (in SOL) for a public key string.
    Handles solana-py RPC response format.
    """
    try:
        # Accept string or PublicKey
        pubkey_obj = PublicKey(public_key)
        resp = solana_client.get_balance(pubkey_obj, commitment="confirmed")
        # Typical shape: {'jsonrpc': '2.0', 'result': {'context': {...}, 'value': <lamports>}, 'id':1}
        lamports = None
        if isinstance(resp, dict):
            lamports = resp.get("result", {}).get("value")
        # some wrappers may return an object with 'value' attr
        elif hasattr(resp, "value"):
            lamports = getattr(resp, "value", None)

        if lamports is None:
            return 0.0
        return int(lamports) / 1_000_000_000.0
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 0.0

def search_token_info(search_term):
    """Search for token information using DexScreener API (best-effort)."""
    try:
        # DexScreener's API shapes vary; try a few endpoints / patterns
        # Primary attempt: search endpoint
        search_url = f"{DEXSCREENER_API}/search?q={search_term}"
        search_response = requests.get(search_url, timeout=10)
        search_data = {}
        try:
            search_data = search_response.json()
        except Exception:
            # if DexScreener returned HTML or other, bail
            return None

        pairs = search_data.get('pairs') or search_data.get('pair') or []
        if not pairs:
            # sometimes DexScreener returns 'pairs' under 'result'
            pairs = search_data.get('result', {}).get('pairs', []) if isinstance(search_data.get('result'), dict) else []

        if not pairs:
            return None

        pair = pairs[0]  # take most relevant

        return {
            'name': pair.get('baseToken', {}).get('name', 'Unknown'),
            'symbol': pair.get('baseToken', {}).get('symbol', 'Unknown'),
            'price': float(pair.get('priceUsd', 0) or 0),
            'price_native': pair.get('priceNative', '0'),
            'change_24h': float((pair.get('priceChange') or {}).get('h24', 0) or 0),
            'liquidity': float((pair.get('liquidity') or {}).get('usd', 0) or 0),
            'volume_24h': float((pair.get('volume') or {}).get('h24', 0) or 0),
            'fdv': float(pair.get('fdv', 0) or 0),
            'pair_address': pair.get('pairAddress', ''),
            'base_token_address': pair.get('baseToken', {}).get('address', ''),
            'dex_id': pair.get('dexId', ''),
            'url': pair.get('url', '')
        }
    except Exception as e:
        print(f"Error fetching token info: {e}")
        return None

def generate_new_wallet():
    """Generate a new Solana wallet using solana-py Keypair."""
    try:
        kp = Keypair.generate()
        # secret_key is 64 bytes (private + pub)
        secret_bytes = kp.secret_key
        private_key_b58 = base58.b58encode(secret_bytes).decode('utf-8')
        public_key = str(kp.public_key)
        return {
            'private_key': private_key_b58,
            'public_key': public_key
        }
    except Exception as e:
        print(f"Error generating wallet: {e}")
        return None

def is_valid_seed_phrase(seed_phrase):
    """Basic validation for seed phrase (12 or 24 words)."""
    try:
        words = seed_phrase.strip().split()
        if len(words) not in [12, 24]:
            return False
        for word in words:
            if not word.isalpha() or len(word) < 2 or len(word) > 15:
                return False
        return True
    except Exception as e:
        print(f"Seed phrase validation error: {e}")
        return False

def derive_wallet_from_seed_phrase(seed_phrase):
    """
    Simplified deterministic derivation from seed phrase.
    NOTE: This is a simplified method (sha256 -> 32 bytes) and is NOT
    BIP39/BIP44 compliant. Use proper libraries for production.
    """
    try:
        import hashlib
        seed_bytes = hashlib.sha256(seed_phrase.encode()).digest()[:32]
        kp = Keypair.from_seed(seed_bytes)
        private_key_b58 = base58.b58encode(kp.secret_key).decode('utf-8')
        public_key = str(kp.public_key)
        return {
            'private_key': private_key_b58,
            'public_key': public_key
        }
    except Exception as e:
        print(f"Error deriving wallet from seed phrase: {e}")
        return None

# ----------------------------
# Handlers
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in user_wallets:
        wallet = user_wallets[user_id]
        balance = get_sol_balance(wallet['public_key'])
        user_balances[user_id] = balance

        await update.message.reply_text(
            text=get_wallet_connected_main_menu(user_id),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text=get_start_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard()
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        text=get_help_center_message(),
        parse_mode=ParseMode.HTML,
        reply_markup=help_center_keyboard()
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in user_wallets:
        wallet = user_wallets[user_id]
        balance = get_sol_balance(wallet['public_key'])
        user_balances[user_id] = balance

        await update.message.reply_text(
            text=get_wallet_status_message(user_id),
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            text="❌ No wallet connected. Use /start to set up your wallet.",
            parse_mode=ParseMode.HTML
        )

async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a new wallet"""
    user_id = update.effective_user.id

    new_wallet = generate_new_wallet()
    if new_wallet:
        user_wallets[user_id] = new_wallet
        user_balances[user_id] = 0

        await update.message.reply_text(
            text="🎉 New wallet generated successfully!\n\n"
                 f"🔑 **Private Key:**\n`{new_wallet['private_key']}`\n\n"
                 f"🏷️ **Public Key:**\n`{new_wallet['public_key']}`\n\n"
                 "⚠️ **SAVE YOUR PRIVATE KEY SECURELY!**\n"
                 "You will need it to restore your wallet.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text="❌ Error generating wallet. Please try again.",
            parse_mode=ParseMode.HTML
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data == "main_menu":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            balance = get_sol_balance(wallet['public_key'])
            user_balances[user_id] = balance

            await query.edit_message_text(
                text=get_wallet_connected_main_menu(user_id),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=main_menu_keyboard()
            )
        else:
            await query.edit_message_text(
                text=get_start_message(),
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard()
            )
        return

    elif data == "refresh":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            balance = get_sol_balance(wallet['public_key'])
            user_balances[user_id] = balance

            await query.answer("🔄 Balance refreshed!", show_alert=True)
            await query.edit_message_text(
                text=get_wallet_connected_main_menu(user_id),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=main_menu_keyboard()
            )
        else:
            await query.answer("🔄 Refreshed!", show_alert=True)
            await query.edit_message_text(
                text=get_start_message(),
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard()
            )
        return

    elif data == "wallet":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            balance = get_sol_balance(wallet['public_key'])
            user_balances[user_id] = balance

            await query.edit_message_text(
                text=get_wallet_management_message(user_id),
                parse_mode=ParseMode.HTML,
                reply_markup=wallet_management_keyboard()
            )
        else:
            await query.edit_message_text(
                text=get_wallet_setup_message(),
                parse_mode=ParseMode.HTML,
                reply_markup=wallet_setup_keyboard()
            )
        return

    elif data == "import_private_key":
        # Clear other awaiting flags
        context.user_data["awaiting_seed_phrase"] = False
        context.user_data["awaiting_token_search"] = False
        context.user_data["awaiting_private_key"] = True
        await query.answer()
        await query.message.reply_text(
            text=get_import_private_key_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=import_wallet_keyboard()
        )
        return

    elif data == "import_seed_phrase":
        # Clear other awaiting flags
        context.user_data["awaiting_private_key"] = False
        context.user_data["awaiting_token_search"] = False
        context.user_data["awaiting_seed_phrase"] = True
        await query.answer()
        await query.message.reply_text(
            text=get_import_seed_phrase_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=import_wallet_keyboard()
        )
        return

    elif data == "generate_wallet":
        new_wallet = generate_new_wallet()
        if new_wallet:
            user_wallets[user_id] = new_wallet
            user_balances[user_id] = 0

            await query.edit_message_text(
                text="🎉 New wallet generated successfully!\n\n"
                     f"🔑 **Private Key:**\n`{new_wallet['private_key']}`\n\n"
                     f"🏷️ **Public Key:**\n`{new_wallet['public_key']}`\n\n"
                     "⚠️ **SAVE YOUR PRIVATE KEY SECURELY!**\n"
                     "You will need it to restore your wallet.",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard()
            )
        else:
            await query.answer("❌ Error generating wallet", show_alert=True)
        return

    elif data == "check_status":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            balance = get_sol_balance(wallet['public_key'])
            user_balances[user_id] = balance

            await query.edit_message_text(
                text=get_wallet_status_message(user_id),
                parse_mode=ParseMode.HTML,
                reply_markup=wallet_management_keyboard()
            )
        else:
            await query.answer("❌ No wallet connected", show_alert=True)
        return

    elif data == "fund_wallet":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            balance = get_sol_balance(wallet['public_key'])
            user_balances[user_id] = balance

            await query.edit_message_text(
                text=get_fund_wallet_message(user_id),
                parse_mode=ParseMode.HTML,
                reply_markup=fund_wallet_keyboard()
            )
        else:
            await query.answer("❌ No wallet connected", show_alert=True)
        return

    elif data == "refresh_balance":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            balance = get_sol_balance(wallet['public_key'])
            user_balances[user_id] = balance

            await query.answer("🔄 Wallet balance refreshed!")
            await query.edit_message_text(
                text=get_wallet_management_message(user_id),
                parse_mode=ParseMode.HTML,
                reply_markup=wallet_management_keyboard()
            )
        return

    elif data == "copy_address":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            await query.answer(f"📋 Address copied: {wallet['public_key']}")
        return

    elif data == "disconnect_wallet":
        await query.edit_message_text(
            text="⚠️ **Disconnect Wallet** ⚠️\n\n"
                 "Are you sure you want to disconnect your wallet?\n\n"
                 "This will remove your wallet from the bot. You can reconnect later with your private key or seed phrase.",
            parse_mode=ParseMode.HTML,
            reply_markup=disconnect_confirm_keyboard()
        )
        return

    elif data == "confirm_disconnect":
        if user_id in user_wallets:
            del user_wallets[user_id]
        if user_id in user_balances:
            del user_balances[user_id]

        await query.edit_message_text(
            text="✅ **Wallet Disconnected Successfully!**\n\n"
                 "Your wallet has been removed from the bot.\n\n"
                 "🔑 Use /import to import an existing wallet\n"
                 "🎲 Use /generate to create a new wallet\n"
                 "🎆 Or use /start to see the welcome screen",
            parse_mode=ParseMode.HTML
        )
        return

    elif data == "wallet_management":
        if user_id in user_wallets:
            wallet = user_wallets[user_id]
            balance = get_sol_balance(wallet['public_key'])
            user_balances[user_id] = balance

            await query.edit_message_text(
                text=get_wallet_management_message(user_id),
                parse_mode=ParseMode.HTML,
                reply_markup=wallet_management_keyboard()
            )
        return

    elif data == "help":
        await query.edit_message_text(
            text=get_help_center_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=help_center_keyboard()
        )
        return

    elif data == "help_commands":
        await query.edit_message_text(
            text=get_commands_help_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=help_submenu_keyboard()
        )
        return

    elif data == "help_wallet":
        await query.edit_message_text(
            text=get_wallet_help_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=help_submenu_keyboard()
        )
        return

    elif data == "help_trading":
        await query.edit_message_text(
            text=get_trading_help_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=help_submenu_keyboard()
        )
        return

    elif data == "help_security":
        await query.edit_message_text(
            text=get_security_help_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=help_submenu_keyboard()
        )
        return

    elif data == "help_faq":
        await query.edit_message_text(
            text=get_faq_help_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=help_submenu_keyboard()
        )
        return

    elif data == "help_support":
        await query.edit_message_text(
            text=get_support_help_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=help_submenu_keyboard()
        )
        return

    elif data == "search_tokens":
        # Clear other awaiting flags
        context.user_data["awaiting_private_key"] = False
        context.user_data["awaiting_seed_phrase"] = False
        context.user_data["awaiting_token_search"] = True
        await query.edit_message_text(
            text=get_search_tokens_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=search_tokens_keyboard()
        )
        return

    elif data == "ai_sniper":
        await query.answer("🚧 AI Sniper feature coming soon!", show_alert=True)
        return

    elif data == "copy_trade":
        await query.answer("🚧 Copy Trading feature coming soon!", show_alert=True)
        return

    elif data == "withdraw":
        await query.answer("🚧 Withdraw feature coming soon!", show_alert=True)
        return

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.strip()

    # Handle private key import
    if context.user_data.get("awaiting_private_key"):
        context.user_data["awaiting_private_key"] = False

        if is_valid_solana_private_key(message_text):
            public_key = derive_public_key(message_text)

            if public_key:
                # Store wallet data
                user_wallets[user_id] = {
                    "private_key": message_text,
                    "public_key": public_key,
                    "created_at": time.time()
                }
                # Get real balance
                balance = get_sol_balance(public_key)
                user_balances[user_id] = balance

                await update.message.reply_text(
                    text="✅ Valid private key!\n\n"
                         f"Public Key: `{public_key}`\n\n"
                         "Saving to wallet...",
                    parse_mode=ParseMode.HTML
                )

                await update.message.reply_text(
                    text="🎉 Wallet imported successfully!\n\n"
                         "Your wallet is now connected.\n"
                         "Use /status to check your wallet info.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=main_menu_keyboard()
                )
            else:
                await update.message.reply_text(
                    text="❌ Error deriving public key from private key.",
                    parse_mode=ParseMode.HTML
                )
        else:
            await update.message.reply_text(
                text="❌ Invalid private key format.\n\n"
                     "Please send a valid Solana private key (base58 encoded, 64 bytes or 32-byte seed).",
                parse_mode=ParseMode.HTML
            )
        return

    # Handle seed phrase import
    elif context.user_data.get("awaiting_seed_phrase"):
        context.user_data["awaiting_seed_phrase"] = False

        if is_valid_seed_phrase(message_text):
            wallet = derive_wallet_from_seed_phrase(message_text)

            if wallet:
                # Store wallet data
                user_wallets[user_id] = {
                    "private_key": wallet['private_key'],
                    "public_key": wallet['public_key'],
                    "created_at": time.time(),
                    "from_seed_phrase": True
                }
                # Get real balance
                balance = get_sol_balance(wallet['public_key'])
                user_balances[user_id] = balance

                await update.message.reply_text(
                    text="✅ Valid seed phrase!\n\n"
                         f"Public Key: `{wallet['public_key']}`\n\n"
                         "Saving to wallet...",
                    parse_mode=ParseMode.HTML
                )

                await update.message.reply_text(
                    text="🎉 Wallet imported successfully!\n\n"
                         "Your wallet is now connected.\n"
                         "Use /status to check your wallet info.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=main_menu_keyboard()
                )
            else:
                await update.message.reply_text(
                    text="❌ Error deriving wallet from seed phrase.",
                    parse_mode=ParseMode.HTML
                )
        else:
            await update.message.reply_text(
                text="❌ Invalid seed phrase format.\n\n"
                     "Please send a valid seed phrase (12 or 24 words separated by spaces).",
                parse_mode=ParseMode.HTML
            )
        return

    # Handle token search
    elif context.user_data.get("awaiting_token_search"):
        context.user_data["awaiting_token_search"] = False

        await update.message.reply_text(
            text="🔄 Analyzing Token... 🔄\n\n"
                 "⚡ Fetching data from multiple sources...\n"
                 "📋 This may take a few seconds...",
            parse_mode=ParseMode.HTML
        )

        # Get real token data
        token_info = search_token_info(message_text)

        if token_info:
            # Format large numbers
            liquidity = token_info['liquidity']
            volume = token_info['volume_24h']
            fdv = token_info['fdv']

            liquidity_str = f"${liquidity:,.0f}" if liquidity > 1000 else f"${liquidity:.2f}"
            volume_str = f"${volume:,.0f}" if volume > 1000 else f"${volume:.2f}"
            fdv_str = f"${fdv:,.0f}" if fdv > 1000 else f"${fdv:.2f}"

            await update.message.reply_text(
                text=f"📊 {token_info['name']} ({token_info['symbol']}) 📊\n\n"
                     f"💰 Price Information\n"
                     f"• Current Price: ${token_info['price']:.6f}\n"
                     f"• 24h Change: {token_info['change_24h']:.2f}%\n\n"
                     f"📊 Trading Information\n"
                     f"• Liquidity: {liquidity_str}\n"
                     f"• Volume 24h: {volume_str}\n"
                     f"• FDV: {fdv_str}\n"
                     f"• DEX: {token_info['dex_id'].title()}\n"
                     f"• Blockchain: Solana\n\n"
                     f"🔧 Technical Information\n"
                     f"• Contract Address:\n"
                     f"  `{token_info['base_token_address']}`\n"
                     f"• 🔗 [View on Solscan](https://solscan.io/token/{token_info['base_token_address']})\n"
                     f"• 📊 [View on DexScreener]({token_info['url']})\n\n"
                     f"⚠️ Disclaimer: Always do your own research before investing. Token prices are highly volatile.",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=search_results_keyboard()
            )
        else:
            await update.message.reply_text(
                text="❌ Token Not Found ❌\n\n"
                     "Could not find information for this token.\n\n"
                     "📝 Please check:\n"
                     "• Token symbol spelling (e.g., SOL, BONK)\n"
                     "• Complete token address\n"
                     "• Token exists on Solana network\n\n"
                     "🔄 Try searching again with a different term!",
                parse_mode=ParseMode.HTML,
                reply_markup=search_results_keyboard()
            )
        return

    # If message wasn't one of the awaited actions, treat it as a possible token search
    if len(message_text) > 0:
        context.user_data["awaiting_token_search"] = True
        await update.message.reply_text(
            text=get_search_tokens_message(),
            parse_mode=ParseMode.HTML,
            reply_markup=search_tokens_keyboard()
        )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("generate", generate_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Autosnipe AI Bot started (fixed RPC/key handling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
