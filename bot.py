"""
Discord Moderasyon Botu
========================
Ozellikler:
- Spam engelleme (alt alta 3 mesaj VE 1 saniyede 3 mesaj)
- Reklam/link engelleme (mesaj silinir, uye susturulur, uyari 2 dakika sonra silinir)
- Yetkisiz rol/izin degisikligi koruma sistemi (otomatik geri alma)
- "/" ile baslayan mesajlarin silinmesi
- "yaz gir" ifadesinin (leetspeak varyasyonlari dahil, orn: y@z g!r) silinmesi
- 100 kelimeden uzun mesajlarin silinmesi
- !owner komutu
- Bot normalde emoji KULLANMAZ, sadece owner'in ozel komutuyla emoji icerebilir

KURULUM
-------
1) pip install -r requirements.txt
2) Asagidaki TOKEN / OWNER_ID / LOG_CHANNEL_ID degerlerini doldurun
   (veya bunlarin yerine bir .env dosyasi olusturup ortam degiskeni olarak verin)
3) Discord Developer Portal -> Bot -> Privileged Gateway Intents bolumunden
   "SERVER MEMBERS INTENT" ve "MESSAGE CONTENT INTENT" secimlerini ACIN
4) Botun sunucuda su yetkilere ihtiyaci var:
   Mesajlari Yonet, Uyeleri Zaman Asimina Ugrat (Timeout/Moderate Members),
   Rolleri Yonet, Denetim Gunlugunu Goruntule
5) python bot.py
"""

import os
import re
import asyncio
from datetime import timedelta, datetime, timezone
from collections import deque

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ====================== AYARLAR (BURAYI DOLDURUN) ======================

TOKEN = os.getenv("DISCORD_TOKEN") or "BOT_TOKENINIZI_BURAYA_YAZIN"
OWNER_ID = int(os.getenv("OWNER_ID") or "0")          # Owner'in Discord kullanici ID'si
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID") or "0")  # Log mesajlarinin gidecegi kanal ID'si

PREFIX = "!"

# Bir role/uyeye eklenmeye calisildiginda otomatik geri alinacak "tehlikeli" izinler
DANGEROUS_PERMS = [
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "manage_webhooks", "kick_members", "ban_members", "mention_everyone",
    "manage_messages", "manage_nicknames", "manage_emojis", "ban_members",
]

WORD_LIMIT = 100                 # 100 kelimeden fazla mesaj silinir
SPAM_TIME_WINDOW = 1.0           # saniye
SPAM_TIME_LIMIT = 3              # 1 saniyede 3 mesaj
SPAM_ROW_LIMIT = 3                # alt alta 3 mesaj
TIMEOUT_DURATION = timedelta(minutes=1)
LINK_TIMEOUT_DURATION = timedelta(minutes=1)
LINK_WARNING_DELETE_AFTER = 120  # saniye (2 dakika)

LINK_REGEX = re.compile(
    r"(https?://|www\.|discord\.gg/|discordapp\.com/invite/|\.com\b|\.net\b|\.org\b|\.gg\b)",
    re.IGNORECASE,
)

LEET_MAP = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
    "7": "t", "8": "b", "@": "a", "!": "i", "$": "s",
})


def normalize_text(text: str) -> str:
    text = text.lower().translate(LEET_MAP)
    text = re.sub(r"[^a-zçğıöşü\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def contains_yazgir(content: str) -> bool:
    normalized = normalize_text(content).replace(" ", "")
    return "yazgir" in normalized


# ====================== BOT KURULUMU ======================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Durum takibi
last_channel_author = {}     # channel_id -> {"author_id", "count", "messages"}
user_message_times = {}      # user_id -> deque[datetime]
role_perm_snapshot = {}      # role_id -> discord.Permissions (son bilinen guvenli durum)


async def send_log(guild: discord.Guild, content: str):
    if guild is None:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        return
    try:
        await channel.send(content)
    except discord.HTTPException:
        pass


async def get_audit_responsible(guild: discord.Guild, action, target_id: int):
    try:
        async for entry in guild.audit_logs(action=action, limit=5):
            if entry.target is not None and getattr(entry.target, "id", None) == target_id:
                return entry.user
    except discord.Forbidden:
        return None
    except discord.HTTPException:
        return None
    return None


async def timeout_member(member: discord.Member, duration: timedelta, reason: str = ""):
    if member is None or member.id == OWNER_ID:
        return
    try:
        await member.timeout(duration, reason=reason)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def delete_after(message: discord.Message, seconds: int):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except discord.HTTPException:
        pass


# ====================== ICERIK FILTRELERI ======================

async def handle_slash_text(message: discord.Message) -> bool:
    if message.content.startswith("/"):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await send_log(
            message.guild,
            f"{message.author.mention} {message.channel.mention} kanalinda '/' ile baslayan "
            f"mesaj yazdi, mesaj silindi.\nIcerik: {message.content}",
        )
        return True
    return False


async def handle_yazgir(message: discord.Message) -> bool:
    if contains_yazgir(message.content):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await send_log(
            message.guild,
            f"{message.author.mention} {message.channel.mention} kanalinda yasakli ifade "
            f"kullandi, mesaj silindi.\nIcerik: {message.content}",
        )
        return True
    return False


async def handle_word_limit(message: discord.Message) -> bool:
    word_count = len(message.content.split())
    if word_count > WORD_LIMIT:
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await send_log(
            message.guild,
            f"{message.author.mention} {message.channel.mention} kanalinda {word_count} "
            f"kelimelik mesaj yazdi (limit {WORD_LIMIT}), mesaj silindi.",
        )
        return True
    return False


async def handle_link(message: discord.Message) -> bool:
    if LINK_REGEX.search(message.content):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        await timeout_member(message.author, LINK_TIMEOUT_DURATION, reason="Reklam/link paylasimi")

        try:
            warning = await message.channel.send(
                f"{message.author.mention} reklam/link paylastigin icin mesajin silindi ve susturuldun."
            )
            asyncio.create_task(delete_after(warning, LINK_WARNING_DELETE_AFTER))
        except discord.HTTPException:
            pass

        await send_log(
            message.guild,
            f"{message.author.mention} {message.channel.mention} kanalinda link/reklam "
            f"paylasti. Mesaj silindi, kullanici susturuldu.\nIcerik: {message.content}",
        )
        return True
    return False


# ====================== SPAM FILTRELERI ======================

async def handle_rate_spam(message: discord.Message) -> bool:
    now = datetime.now(timezone.utc)
    times = user_message_times.setdefault(message.author.id, deque(maxlen=10))
    times.append(now)
    recent = [t for t in times if (now - t).total_seconds() <= SPAM_TIME_WINDOW]

    if len(recent) >= SPAM_TIME_LIMIT:
        try:
            await message.channel.send(f"{message.author.mention} Yavaş Yaz Qehben Balası")
        except discord.HTTPException:
            pass

        await timeout_member(message.author, TIMEOUT_DURATION, reason="Hizli mesaj spami")

        await send_log(
            message.guild,
            f"{message.author.mention} 1 saniye icinde {SPAM_TIME_LIMIT} mesaj yazdi, "
            f"{int(TIMEOUT_DURATION.total_seconds() // 60)} dakika susturuldu.",
        )

        user_message_times[message.author.id].clear()
        last_channel_author[message.channel.id] = {"author_id": None, "count": 0, "messages": []}
        return True
    return False


async def handle_consecutive_spam(message: discord.Message) -> bool:
    channel_id = message.channel.id
    author_id = message.author.id

    data = last_channel_author.get(channel_id)
    if data and data["author_id"] == author_id:
        data["count"] += 1
        data["messages"].append(message)
    else:
        data = {"author_id": author_id, "count": 1, "messages": [message]}
        last_channel_author[channel_id] = data

    if data["count"] >= SPAM_ROW_LIMIT:
        for m in data["messages"][-SPAM_ROW_LIMIT:]:
            try:
                await m.delete()
            except discord.HTTPException:
                pass

        await timeout_member(message.author, TIMEOUT_DURATION, reason="Alt alta spam mesaj")

        await send_log(
            message.guild,
            f"{message.author.mention} alt alta {SPAM_ROW_LIMIT} mesaj yazdi, mesajlar silindi "
            f"ve {int(TIMEOUT_DURATION.total_seconds() // 60)} dakika susturuldu.",
        )

        last_channel_author[channel_id] = {"author_id": None, "count": 0, "messages": []}
        return True
    return False


# ====================== EVENTLER ======================

@bot.event
async def on_ready():
    for guild in bot.guilds:
        for role in guild.roles:
            role_perm_snapshot[role.id] = role.permissions
    print(f"{bot.user} aktif ve hazir.")


@bot.event
async def on_guild_role_create(role: discord.Role):
    role_perm_snapshot[role.id] = role.permissions


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    await bot.process_commands(message)

    if message.content.startswith(PREFIX):
        return

    if message.author.id == OWNER_ID:
        return

    if await handle_slash_text(message):
        return
    if await handle_yazgir(message):
        return
    if await handle_word_limit(message):
        return
    if await handle_link(message):
        return
    if await handle_rate_spam(message):
        return
    await handle_consecutive_spam(message)


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    before_perms = role_perm_snapshot.get(before.id, before.permissions)
    added_perms = [perm for perm, value in after.permissions if value and not getattr(before_perms, perm)]

    if not added_perms:
        role_perm_snapshot[after.id] = after.permissions
        return

    responsible = await get_audit_responsible(after.guild, discord.AuditLogAction.role_update, after.id)

    if responsible and responsible.id == OWNER_ID:
        role_perm_snapshot[after.id] = after.permissions
        return

    try:
        await after.edit(permissions=before_perms, reason="Yetkisiz izin degisikligi geri alindi")
    except discord.Forbidden:
        await send_log(
            after.guild,
            f"UYARI: {after.mention} rolune yetki eklenmeye calisildi fakat bot bu islemi "
            f"geri alamadi (yetki/rol hiyerarsisi eksik).",
        )
        return
    except discord.HTTPException:
        return

    mention = responsible.mention if responsible else "Bilinmeyen kullanici"
    await send_log(
        after.guild,
        f"{mention}, {after.mention} rolune yetki eklemeye calisti. Islem bot tarafindan "
        f"geri alindi ve tamamlanmadi.\nEklenen yetkiler: {', '.join(added_perms)}",
    )


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.roles == after.roles:
        return

    added_roles = [r for r in after.roles if r not in before.roles]
    dangerous_added = [
        r for r in added_roles
        if any(getattr(r.permissions, p, False) for p in DANGEROUS_PERMS)
    ]

    if not dangerous_added or after.id == OWNER_ID:
        return

    responsible = await get_audit_responsible(
        after.guild, discord.AuditLogAction.member_role_update, after.id
    )

    if responsible and responsible.id == OWNER_ID:
        return

    try:
        await after.remove_roles(*dangerous_added, reason="Yetkisiz rol atamasi geri alindi")
    except discord.Forbidden:
        await send_log(
            after.guild,
            f"UYARI: {after.mention} kullanicisina yetkili rol verilmeye calisildi fakat bot "
            f"geri alamadi (yetki/rol hiyerarsisi eksik).",
        )
        return
    except discord.HTTPException:
        return

    mention = responsible.mention if responsible else "Bilinmeyen kullanici"
    rol_isimleri = ", ".join(r.name for r in dangerous_added)
    await send_log(
        after.guild,
        f"{mention}, {after.mention} kullanicisina yetkili rol ({rol_isimleri}) vermeye "
        f"calisti. Islem bot tarafindan geri alindi ve tamamlanmadi.",
    )


# ====================== KOMUTLAR ======================

@bot.command(name="owner")
async def owner_cmd(ctx: commands.Context):
    member = ctx.guild.get_member(OWNER_ID)
    if member is None:
        try:
            member = await bot.fetch_user(OWNER_ID)
        except discord.HTTPException:
            await ctx.send("Owner bulunamadi.")
            return
    await ctx.send(f"{member.mention}")


@bot.command(name="emojilimesaj")
async def emoji_message_cmd(ctx: commands.Context, *, mesaj: str):
    # Bot normalde emoji kullanmaz. Bu komut SADECE owner tarafindan
    # cagrildiginda emoji icerebilen ozel bir mesaj gonderir.
    if ctx.author.id != OWNER_ID:
        return
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    await ctx.send(mesaj)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Komut hatasi: {error}")


# ====================== CALISTIR ======================

if __name__ == "__main__":
    if TOKEN == "BOT_TOKENINIZI_BURAYA_YAZIN" or not TOKEN:
        print("HATA: Lutfen bot.py dosyasinin ustundeki TOKEN degerini doldurun "
              "veya DISCORD_TOKEN ortam degiskenini ayarlayin.")
    else:
        bot.run(TOKEN)
