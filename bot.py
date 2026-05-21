import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import asyncio
import random
from datetime import datetime, timedelta
import aiohttp

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("z!", "Z!", "!"), intents=intents, help_command=None)

DATA_FILE = "settings.json"
MC_IP = "zernoxcraft.novara.com.tr"
MC_PORT = 25565

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_guild_settings(guild_id: int) -> dict:
    data = load_data()
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {
            "kufur_filtre": True,
            "reklam_filtre": True,
            "destek_kanal": None,
            "log_kanal": None,
            "hosgeldin_kanal": None,
            "otomatik_mesajlar": [],
            "kara_liste": [],
            "muaf_roller": [],
            "reklam_liste": [],
        }
        save_data(data)
    return data[gid]

def save_guild_settings(guild_id: int, settings: dict):
    data = load_data()
    data[str(guild_id)] = settings
    save_data(data)

KUFUR_LISTESI = [
    "amk", "orospu", "sik", "göt", "oç", "piç", "amına", "sikerim",
    "bok", "yarrak", "gerizekalı", "salak", "aptal", "orospu çocuğu"
]

VARSAYILAN_REKLAM = [
    r"discord\.gg/\S+",
    r"discord\.com/invite/\S+",
    r"\.gg/\S+",
    r"@everyone.*join",
    r"free\s*nitro",
]

def kufur_var_mi(metin: str, kara_liste: list) -> bool:
    metin_lower = metin.lower()
    return any(k in metin_lower for k in KUFUR_LISTESI + kara_liste)

def reklam_var_mi(metin: str, ekstra_liste: list) -> bool:
    metin_lower = metin.lower()
    for pattern in VARSAYILAN_REKLAM:
        if re.search(pattern, metin_lower):
            return True
    if re.search(r"https?://\S+", metin_lower):
        return True
    for kelime in ekstra_liste:
        if kelime.lower() in metin_lower:
            return True
    return False

def muaf_mi(member: discord.Member, muaf_roller: list) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(str(role.id) in muaf_roller for role in member.roles)

def sure_parse(sure_str: str) -> int:
    sure_str = sure_str.lower().strip()
    try:
        if sure_str.endswith("d"):
            return int(sure_str[:-1]) * 86400
        elif sure_str.endswith("h"):
            return int(sure_str[:-1]) * 3600
        elif sure_str.endswith("m"):
            return int(sure_str[:-1]) * 60
        elif sure_str.endswith("s"):
            return int(sure_str[:-1])
        else:
            return int(sure_str) * 60
    except:
        return 0

def sure_format(saniye: int) -> str:
    if saniye >= 86400:
        return f"{saniye // 86400} gün"
    elif saniye >= 3600:
        return f"{saniye // 3600} saat"
    elif saniye >= 60:
        return f"{saniye // 60} dakika"
    else:
        return f"{saniye} saniye"

def admin_kontrol():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        await ctx.send("❌ Bu komutu kullanmak için **Yönetici** yetkisi gerekli.", delete_after=5)
        return False
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} aktif!")
    await bot.change_presence(
        activity=discord.Game(name=f"🎮 {MC_IP}")
    )
    try:
        synced = await bot.tree.sync()
        print(f"📋 {len(synced)} slash komutu senkronize edildi.")
    except Exception as e:
        print(f"❌ Senkronizasyon hatası: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.guild:
        return

    s = get_guild_settings(message.guild.id)

    if not muaf_mi(message.author, s.get("muaf_roller", [])):
        if s.get("kufur_filtre", True) and kufur_var_mi(message.content, s.get("kara_liste", [])):
            try:
                await message.delete()
                uyari = await message.channel.send(f"⚠️ {message.author.mention}, uygunsuz kelime kullandın! Mesajın silindi.")
                await uyari.delete(delay=5)
                await log_gonder(message.guild, s, f"🚫 **Küfür** | {message.author} | {message.channel.mention} | ||{message.content}||")
            except discord.Forbidden:
                pass
            return

        if s.get("reklam_filtre", True) and reklam_var_mi(message.content, s.get("reklam_liste", [])):
            try:
                await message.delete()
                uyari = await message.channel.send(f"📢 {message.author.mention}, reklam/link paylaşmak yasaktır! Mesajın silindi.")
                await uyari.delete(delay=5)
                await log_gonder(message.guild, s, f"🔗 **Reklam** | {message.author} | {message.channel.mention} | ||{message.content}||")
            except discord.Forbidden:
                pass
            return

    for om in s.get("otomatik_mesajlar", []):
        if om["anahtar"].lower() in message.content.lower():
            await message.channel.send(om["cevap"])
            break

    await bot.process_commands(message)

@bot.event
async def on_member_join(member: discord.Member):
    s = get_guild_settings(member.guild.id)
    kanal_id = s.get("hosgeldin_kanal")
    if not kanal_id:
        return
    kanal = member.guild.get_channel(int(kanal_id))
    if not kanal:
        return
    embed = discord.Embed(
        description=f"👋 Hoş geldin {member.mention}! Seninle birlikte **{member.guild.member_count}** kişiyiz.\n📋 Kurallara göz atmayı unutma!",
        color=0x57F287
    )
    await kanal.send(embed=embed)

@bot.event
async def on_member_remove(member: discord.Member):
    s = get_guild_settings(member.guild.id)
    kanal_id = s.get("hosgeldin_kanal")
    if not kanal_id:
        return
    kanal = member.guild.get_channel(int(kanal_id))
    if not kanal:
        return
    embed = discord.Embed(
        description=f"👋 **{member.name}** aramızdan ayrıldı. Görüşmek üzere!",
        color=0xFF4444
    )
    await kanal.send(embed=embed)

async def log_gonder(guild: discord.Guild, settings: dict, metin: str):
    kanal_id = settings.get("log_kanal")
    if kanal_id:
        kanal = guild.get_channel(int(kanal_id))
        if kanal:
            embed = discord.Embed(description=metin, color=0xFF4444, timestamp=datetime.utcnow())
            try:
                await kanal.send(embed=embed)
            except discord.Forbidden:
                pass

async def mc_sunucu_durumu():
    """Minecraft sunucu durumunu kontrol eder."""
    try:
        import socket
        import struct
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((MC_IP, MC_PORT))
        # Ping paketi gönder
        sock.send(b'\xfe\x01')
        data = sock.recv(1024)
        sock.close()
        if data and len(data) > 3:
            raw = data[3:].decode('utf-16-be', errors='ignore')
            parts = raw.split('\x00')
            if len(parts) >= 5:
                return {"online": True, "oyuncular": int(parts[3]), "max": int(parts[4])}
        return {"online": True, "oyuncular": "?", "max": "?"}
    except:
        return {"online": False, "oyuncular": 0, "max": 0}

# ══════════════════════════════════
#  PREFIX KOMUTLARI (z!, Z!, !)
# ══════════════════════════════════

@bot.command(name="owner")
async def owner(ctx):
    embed = discord.Embed(title="👑 Sunucu Kurucusu", description="**FelxeTheGreat**", color=0xFFD700)
    embed.set_footer(text="ZernoxCraft")
    await ctx.send(embed=embed)

@bot.command(name="yardım", aliases=["yardim", "komutlar"])
async def yardim(ctx):
    embed = discord.Embed(title="📋 ZernoxCraft Bot Komutları", color=0x5865F2)
    embed.add_field(
        name="🛡️ Moderasyon",
        value="`z!sil` `z!ban` `z!mute` `z!lock` `z!unlock` `z!yavaşmod` `z!warn` `z!uyarılar`",
        inline=False
    )
    embed.add_field(
        name="⚙️ Ayarlar",
        value="`/kufur-ayarla` `/reklam-ayarla` `/muaf-rol-ekle` `/otomatikmesaj-ayarla` `/hosgeldin-ayarla` `/log-kanal-ayarla` `/destek-kanal-ayarla`",
        inline=False
    )
    embed.add_field(
        name="🎮 Sunucu",
        value="`z!sunucudurum` `z!sunucu` `z!owner`",
        inline=False
    )
    embed.add_field(
        name="🎉 Eğlence",
        value="`/çekiliş` `/çekiliş-bitir`",
        inline=False
    )
    embed.add_field(
        name="🔧 Diğer",
        value="`/yaziyaz` `/ayarlar`",
        inline=False
    )
    embed.set_footer(text=f"ZernoxCraft • {MC_IP}")
    await ctx.send(embed=embed)

@bot.command(name="sunucudurum", aliases=["durum", "mcdurum"])
async def sunucudurum(ctx):
    async with ctx.typing():
        durum = await mc_sunucu_durumu()
    if durum["online"]:
        embed = discord.Embed(title="🟢 Sunucu Çevrimiçi", color=0x57F287)
        embed.add_field(name="🌐 IP", value=f"`{MC_IP}`", inline=True)
        embed.add_field(name="👥 Oyuncular", value=f"{durum['oyuncular']}/{durum['max']}", inline=True)
    else:
        embed = discord.Embed(title="🔴 Sunucu Çevrimdışı", color=0xFF4444)
        embed.add_field(name="🌐 IP", value=f"`{MC_IP}`", inline=True)
        embed.add_field(name="👥 Oyuncular", value="0/0", inline=True)
    embed.set_footer(text="ZernoxCraft")
    await ctx.send(embed=embed)

@bot.command(name="sunucu", aliases=["serverinfo", "si"])
async def sunucu(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"📊 {guild.name}", color=0x5865F2)
    embed.add_field(name="👑 Kurucu", value="FelxeTheGreat", inline=True)
    embed.add_field(name="👥 Üye Sayısı", value=str(guild.member_count), inline=True)
    embed.add_field(name="📅 Kuruluş", value=guild.created_at.strftime("%d.%m.%Y"), inline=True)
    embed.add_field(name="💬 Kanal Sayısı", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="🎭 Rol Sayısı", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="🌐 MC IP", value=f"`{MC_IP}`", inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="ZernoxCraft")
    await ctx.send(embed=embed)

@bot.command(name="sil")
@admin_kontrol()
async def sil(ctx, miktar: int):
    if miktar < 1 or miktar > 100:
        await ctx.send("⚠️ 1 ile 100 arasında bir sayı gir.", delete_after=5)
        return
    await ctx.message.delete()
    silinen = await ctx.channel.purge(limit=miktar)
    bilgi = await ctx.send(f"🗑️ {len(silinen)} mesaj silindi.")
    await bilgi.delete(delay=4)

@bot.command(name="ban")
@admin_kontrol()
async def ban(ctx, uye: discord.Member, sure_str: str = None, *, sebep: str = "Belirtilmedi"):
    sure_metin = sure_format(sure_parse(sure_str)) if sure_str else "Kalıcı"
    try:
        dm = discord.Embed(title="🔨 Sunucudan Uzaklaştırıldınız", color=0xFF4444)
        dm.add_field(name="Sunucu", value="ZernoxCraft", inline=True)
        dm.add_field(name="Süre", value=sure_metin, inline=True)
        dm.add_field(name="Sebep", value=sebep, inline=False)
        dm.set_footer(text=f"ZernoxCraft • {MC_IP}")
        await uye.send(embed=dm)
    except:
        pass
    await uye.ban(reason=sebep)
    embed = discord.Embed(title="🔨 Kullanıcı Banlandı", color=0xFF4444)
    embed.add_field(name="Kullanıcı", value=str(uye), inline=True)
    embed.add_field(name="Süre", value=sure_metin, inline=True)
    embed.add_field(name="Sebep", value=sebep, inline=True)
    embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
    await ctx.send(embed=embed)
    await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"🔨 **Ban** | {uye} | {sure_metin} | {sebep} | {ctx.author}")

@bot.command(name="unban")
@admin_kontrol()
async def unban(ctx, *, kullanici: str):
    banned = [entry async for entry in ctx.guild.bans()]
    for entry in banned:
        if str(entry.user) == kullanici or str(entry.user.id) == kullanici:
            await ctx.guild.unban(entry.user)
            embed = discord.Embed(title="✅ Ban Kaldırıldı", description=f"**{entry.user}** sunucuya geri alındı.", color=0x57F287)
            await ctx.send(embed=embed)
            return
    await ctx.send("⚠️ Kullanıcı bulunamadı.", delete_after=5)

@bot.command(name="mute")
@admin_kontrol()
async def mute(ctx, uye: discord.Member, sure_str: str = None, *, sebep: str = "Belirtilmedi"):
    saniye = sure_parse(sure_str) if sure_str else 600
    sure_metin = sure_format(saniye)
    try:
        dm = discord.Embed(title="🔇 Zaman Aşımı Aldınız", color=0xFFA500)
        dm.add_field(name="Sunucu", value="ZernoxCraft", inline=True)
        dm.add_field(name="Süre", value=sure_metin, inline=True)
        dm.add_field(name="Sebep", value=sebep, inline=False)
        dm.set_footer(text=f"ZernoxCraft • {MC_IP}")
        await uye.send(embed=dm)
    except:
        pass
    until = discord.utils.utcnow() + timedelta(seconds=saniye)
    await uye.timeout(until, reason=sebep)
    embed = discord.Embed(title="🔇 Kullanıcı Susturuldu", color=0xFFA500)
    embed.add_field(name="Kullanıcı", value=str(uye), inline=True)
    embed.add_field(name="Süre", value=sure_metin, inline=True)
    embed.add_field(name="Sebep", value=sebep, inline=True)
    embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
    await ctx.send(embed=embed)
    await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"🔇 **Mute** | {uye} | {sure_metin} | {sebep} | {ctx.author}")

@bot.command(name="warn")
@admin_kontrol()
async def warn(ctx, uye: discord.Member, *, sebep: str = "Belirtilmedi"):
    data = load_data()
    gid = str(ctx.guild.id)
    uid = str(uye.id)
    if "uyarilar" not in data:
        data["uyarilar"] = {}
    if gid not in data["uyarilar"]:
        data["uyarilar"][gid] = {}
    if uid not in data["uyarilar"][gid]:
        data["uyarilar"][gid][uid] = []
    data["uyarilar"][gid][uid].append({"sebep": sebep, "tarih": datetime.utcnow().strftime("%d.%m.%Y %H:%M"), "yetkili": str(ctx.author)})
    save_data(data)
    uyari_sayisi = len(data["uyarilar"][gid][uid])
    embed = discord.Embed(title="⚠️ Uyarı Verildi", color=0xFFA500)
    embed.add_field(name="Kullanıcı", value=uye.mention, inline=True)
    embed.add_field(name="Uyarı", value=f"{uyari_sayisi}. uyarı", inline=True)
    embed.add_field(name="Sebep", value=sebep, inline=False)
    await ctx.send(embed=embed)
    try:
        dm = discord.Embed(title="⚠️ Uyarı Aldınız", color=0xFFA500)
        dm.add_field(name="Sunucu", value="ZernoxCraft", inline=True)
        dm.add_field(name="Uyarı", value=f"{uyari_sayisi}. uyarı", inline=True)
        dm.add_field(name="Sebep", value=sebep, inline=False)
        dm.set_footer(text=f"ZernoxCraft • {MC_IP}")
        await uye.send(embed=dm)
    except:
        pass
    if uyari_sayisi >= 3:
        await uye.ban(reason="3 uyarı limitine ulaşıldı")
        await ctx.send(f"🔨 {uye.mention} **3 uyarı** aldığı için otomatik olarak banlandı!")

@bot.command(name="uyarılar", aliases=["uyarilar", "warnings"])
@admin_kontrol()
async def uyarilar(ctx, uye: discord.Member):
    data = load_data()
    gid = str(ctx.guild.id)
    uid = str(uye.id)
    liste = data.get("uyarilar", {}).get(gid, {}).get(uid, [])
    if not liste:
        await ctx.send(f"✅ {uye.mention} hiç uyarı almamış.", delete_after=8)
        return
    embed = discord.Embed(title=f"⚠️ {uye.name} — Uyarılar", color=0xFFA500)
    for i, u in enumerate(liste, 1):
        embed.add_field(name=f"{i}. Uyarı", value=f"Sebep: {u['sebep']}\nTarih: {u['tarih']}\nYetkili: {u['yetkili']}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="yavaşmod", aliases=["yavasmod", "slowmode"])
@admin_kontrol()
async def yavasmod(ctx, sure_veya_kapat: str, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    if sure_veya_kapat.lower() == "kapat":
        await hedef.edit(slowmode_delay=0)
        embed = discord.Embed(title="✅ Yavaş Mod Kapatıldı", description=f"{hedef.mention} kanalında yavaş mod kapatıldı.", color=0x57F287)
    else:
        try:
            saniye = int(sure_veya_kapat)
        except:
            await ctx.send("❌ Kullanım: `z!yavaşmod 5 #kanal` veya `z!yavaşmod kapat #kanal`", delete_after=5)
            return
        await hedef.edit(slowmode_delay=saniye)
        embed = discord.Embed(title="🐢 Yavaş Mod Açıldı", description=f"{hedef.mention} kanalında **{saniye} saniye** yavaş mod aktif.", color=0xFFA500)
    await ctx.send(embed=embed)

@bot.command(name="lock", aliases=["kilit"])
@admin_kontrol()
async def lock(ctx, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    overwrites = hedef.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = False
    await hedef.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    embed = discord.Embed(title="🔒 Kanal Kilitlendi", description=f"{hedef.mention} kilitlendi.", color=0xFF4444)
    await ctx.send(embed=embed)
    await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"🔒 **Lock** | {hedef.mention} | {ctx.author}")

@bot.command(name="unlock", aliases=["kilitsiz"])
@admin_kontrol()
async def unlock(ctx, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    overwrites = hedef.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = None
    await hedef.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    embed = discord.Embed(title="🔓 Kanal Açıldı", description=f"{hedef.mention} açıldı.", color=0x57F287)
    await ctx.send(embed=embed)
    await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"🔓 **Unlock** | {hedef.mention} | {ctx.author}")

# ══════════════════════════════════
#  SLASH KOMUTLARI
# ══════════════════════════════════

@bot.tree.command(name="yardım", description="Tüm bot komutlarını listeler.")
async def slash_yardim(interaction: discord.Interaction):
    embed = discord.Embed(title="📋 ZernoxCraft Bot Komutları", color=0x5865F2)
    embed.add_field(name="🛡️ Moderasyon", value="`z!sil` `z!ban` `z!unban` `z!mute` `z!lock` `z!unlock` `z!yavaşmod` `z!warn` `z!uyarılar`", inline=False)
    embed.add_field(name="⚙️ Ayarlar", value="`/kufur-ayarla` `/reklam-ayarla` `/muaf-rol-ekle` `/otomatikmesaj-ayarla` `/hosgeldin-ayarla` `/log-kanal-ayarla` `/destek-kanal-ayarla`", inline=False)
    embed.add_field(name="🎮 Sunucu", value="`z!sunucudurum` `z!sunucu` `z!owner`", inline=False)
    embed.add_field(name="🎉 Eğlence", value="`/çekiliş` `/çekiliş-bitir`", inline=False)
    embed.add_field(name="🔧 Diğer", value="`/yaziyaz` `/ayarlar`", inline=False)
    embed.set_footer(text=f"ZernoxCraft • {MC_IP}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="sunucudurum", description="Minecraft sunucusunun durumunu gösterir.")
async def slash_sunucudurum(interaction: discord.Interaction):
    await interaction.response.defer()
    durum = await mc_sunucu_durumu()
    if durum["online"]:
        embed = discord.Embed(title="🟢 Sunucu Çevrimiçi", color=0x57F287)
        embed.add_field(name="🌐 IP", value=f"`{MC_IP}`", inline=True)
        embed.add_field(name="👥 Oyuncular", value=f"{durum['oyuncular']}/{durum['max']}", inline=True)
    else:
        embed = discord.Embed(title="🔴 Sunucu Çevrimdışı", color=0xFF4444)
        embed.add_field(name="🌐 IP", value=f"`{MC_IP}`", inline=True)
        embed.add_field(name="👥 Oyuncular", value="0/0", inline=True)
    embed.set_footer(text="ZernoxCraft")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="sunucu", description="Discord sunucu istatistiklerini gösterir.")
async def slash_sunucu(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"📊 {guild.name}", color=0x5865F2)
    embed.add_field(name="👑 Kurucu", value="FelxeTheGreat", inline=True)
    embed.add_field(name="👥 Üye Sayısı", value=str(guild.member_count), inline=True)
    embed.add_field(name="📅 Kuruluş", value=guild.created_at.strftime("%d.%m.%Y"), inline=True)
    embed.add_field(name="💬 Kanal Sayısı", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="🎭 Rol Sayısı", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="🌐 MC IP", value=f"`{MC_IP}`", inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="ZernoxCraft")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="yaziyaz", description="Botun ağzından mesaj gönderir.")
@app_commands.describe(yazi="Botun göndereceği mesaj")
@app_commands.checks.has_permissions(administrator=True)
async def yaziyaz(interaction: discord.Interaction, yazi: str):
    await interaction.response.send_message("✅ Mesaj gönderildi.", ephemeral=True)
    await interaction.channel.send(yazi)

@bot.tree.command(name="hosgeldin-ayarla", description="Hoşgeldin/Hoşçakal kanalını ayarlar.")
@app_commands.checks.has_permissions(administrator=True)
async def hosgeldin_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    s = get_guild_settings(interaction.guild.id)
    s["hosgeldin_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Hoşgeldin kanalı {kanal.mention} olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="log-kanal-ayarla", description="Log kanalını ayarlar.")
@app_commands.checks.has_permissions(administrator=True)
async def log_kanal_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    s = get_guild_settings(interaction.guild.id)
    s["log_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Log kanalı {kanal.mention} olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="kufur-ayarla", description="Küfür filtresini açar veya kapatır.")
@app_commands.choices(durum=[app_commands.Choice(name="Açık", value="ac"), app_commands.Choice(name="Kapalı", value="kapat")])
@app_commands.checks.has_permissions(administrator=True)
async def kufur_ayarla(interaction: discord.Interaction, durum: app_commands.Choice[str]):
    s = get_guild_settings(interaction.guild.id)
    s["kufur_filtre"] = (durum.value == "ac")
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"{'✅' if s['kufur_filtre'] else '❌'} Küfür filtresi **{'açıldı' if s['kufur_filtre'] else 'kapatıldı'}**.", ephemeral=True)

@bot.tree.command(name="kufur-kelime-ekle", description="Küfür listesine kelime ekler.")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_kelime_ekle(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() not in s["kara_liste"]:
        s["kara_liste"].append(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten listede.", ephemeral=True)

@bot.tree.command(name="kufur-kelime-sil", description="Küfür listesinden kelime siler.")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_kelime_sil(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() in s["kara_liste"]:
        s["kara_liste"].remove(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Bulunamadı.", ephemeral=True)

@bot.tree.command(name="kufur-kelime-liste", description="Kara listeyi gösterir.")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_kelime_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    liste = s.get("kara_liste", [])
    if not liste:
        await interaction.response.send_message("📭 Kara liste boş.", ephemeral=True)
        return
    embed = discord.Embed(title="📝 Kara Liste", color=0xFF4444, description="\n".join([f"`{k}`" for k in liste]))
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="reklam-ayarla", description="Reklam filtresini açar veya kapatır.")
@app_commands.choices(durum=[app_commands.Choice(name="Açık", value="ac"), app_commands.Choice(name="Kapalı", value="kapat")])
@app_commands.checks.has_permissions(administrator=True)
async def reklam_ayarla(interaction: discord.Interaction, durum: app_commands.Choice[str]):
    s = get_guild_settings(interaction.guild.id)
    s["reklam_filtre"] = (durum.value == "ac")
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"{'✅' if s['reklam_filtre'] else '❌'} Reklam filtresi **{'açıldı' if s['reklam_filtre'] else 'kapatıldı'}**.", ephemeral=True)

@bot.tree.command(name="reklam-ekle", description="Reklam listesine kelime/link ekler.")
@app_commands.checks.has_permissions(administrator=True)
async def reklam_ekle(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() not in s["reklam_liste"]:
        s["reklam_liste"].append(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten listede.", ephemeral=True)

@bot.tree.command(name="reklam-sil", description="Reklam listesinden kelime/link siler.")
@app_commands.checks.has_permissions(administrator=True)
async def reklam_sil(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() in s["reklam_liste"]:
        s["reklam_liste"].remove(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Bulunamadı.", ephemeral=True)

@bot.tree.command(name="reklam-liste", description="Reklam listesini gösterir.")
@app_commands.checks.has_permissions(administrator=True)
async def reklam_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    liste = s.get("reklam_liste", [])
    if not liste:
        await interaction.response.send_message("📭 Reklam listesi boş.", ephemeral=True)
        return
    embed = discord.Embed(title="📢 Reklam Listesi", color=0xFFA500, description="\n".join([f"`{k}`" for k in liste]))
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="muaf-rol-ekle", description="Rolü filtreden muaf yapar.")
@app_commands.checks.has_permissions(administrator=True)
async def muaf_rol_ekle(interaction: discord.Interaction, rol: discord.Role):
    s = get_guild_settings(interaction.guild.id)
    if str(rol.id) not in s["muaf_roller"]:
        s["muaf_roller"].append(str(rol.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {rol.mention} muaf listeye eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten listede.", ephemeral=True)

@bot.tree.command(name="muaf-rol-sil", description="Rolü muaf listesinden çıkarır.")
@app_commands.checks.has_permissions(administrator=True)
async def muaf_rol_sil(interaction: discord.Interaction, rol: discord.Role):
    s = get_guild_settings(interaction.guild.id)
    if str(rol.id) in s["muaf_roller"]:
        s["muaf_roller"].remove(str(rol.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {rol.mention} çıkarıldı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Bulunamadı.", ephemeral=True)

@bot.tree.command(name="muaf-rol-liste", description="Muaf rolleri listeler.")
@app_commands.checks.has_permissions(administrator=True)
async def muaf_rol_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    muaf = s.get("muaf_roller", [])
    if not muaf:
        await interaction.response.send_message("📭 Muaf rol listesi boş.", ephemeral=True)
        return
    roller = [interaction.guild.get_role(int(r)).mention if interaction.guild.get_role(int(r)) else f"({r})" for r in muaf]
    embed = discord.Embed(title="🛡️ Muaf Roller", color=0x57F287, description="\n".join(roller))
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="otomatikmesaj-ayarla", description="Anahtar kelimeye otomatik cevap ekler.")
@app_commands.describe(anahtar="Tetiklenecek kelime", cevap="Botun göndereceği cevap")
@app_commands.checks.has_permissions(administrator=True)
async def otomatikmesaj_ayarla(interaction: discord.Interaction, anahtar: str, cevap: str):
    s = get_guild_settings(interaction.guild.id)
    for om in s["otomatik_mesajlar"]:
        if om["anahtar"].lower() == anahtar.lower():
            om["cevap"] = cevap
            save_guild_settings(interaction.guild.id, s)
            await interaction.response.send_message(f"🔄 Güncellendi.", ephemeral=True)
            return
    s["otomatik_mesajlar"].append({"anahtar": anahtar.lower(), "cevap": cevap})
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ **{anahtar}** → {cevap}", ephemeral=True)

@bot.tree.command(name="otomatikmesaj-sil", description="Otomatik mesajı siler.")
@app_commands.checks.has_permissions(administrator=True)
async def otomatikmesaj_sil(interaction: discord.Interaction, anahtar: str):
    s = get_guild_settings(interaction.guild.id)
    onceki = len(s["otomatik_mesajlar"])
    s["otomatik_mesajlar"] = [om for om in s["otomatik_mesajlar"] if om["anahtar"].lower() != anahtar.lower()]
    if len(s["otomatik_mesajlar"]) < onceki:
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ Silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Bulunamadı.", ephemeral=True)

@bot.tree.command(name="otomatikmesaj-liste", description="Otomatik mesajları listeler.")
@app_commands.checks.has_permissions(administrator=True)
async def otomatikmesaj_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    mesajlar = s.get("otomatik_mesajlar", [])
    if not mesajlar:
        await interaction.response.send_message("📭 Otomatik mesaj yok.", ephemeral=True)
        return
    embed = discord.Embed(title="🤖 Otomatik Mesajlar", color=0x5865F2)
    for i, om in enumerate(mesajlar, 1):
        embed.add_field(name=f"{i}. `{om['anahtar']}`", value=om["cevap"], inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="destek-kanal-ayarla", description="Destek panelini gönderir.")
@app_commands.checks.has_permissions(administrator=True)
async def destek_kanal_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    s = get_guild_settings(interaction.guild.id)
    s["destek_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    embed = discord.Embed(title="🎫 Destek Talebi Oluştur", description="Aşağıdaki butona tıklayarak destek talebi oluşturabilirsiniz.", color=0x57F287)
    await kanal.send(embed=embed, view=DestekView())
    await interaction.response.send_message(f"✅ Destek paneli {kanal.mention} kanalına gönderildi.", ephemeral=True)

@bot.tree.command(name="ayarlar", description="Bot ayarlarını gösterir.")
@app_commands.checks.has_permissions(administrator=True)
async def ayarlar(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    guild = interaction.guild
    destek_k = guild.get_channel(int(s["destek_kanal"])).mention if s.get("destek_kanal") else "❌"
    log_k    = guild.get_channel(int(s["log_kanal"])).mention if s.get("log_kanal") else "❌"
    hg_k     = guild.get_channel(int(s["hosgeldin_kanal"])).mention if s.get("hosgeldin_kanal") else "❌"
    embed = discord.Embed(title="⚙️ Bot Ayarları", color=0xFEE75C)
    embed.add_field(name="🚫 Küfür", value="✅" if s["kufur_filtre"] else "❌", inline=True)
    embed.add_field(name="📢 Reklam", value="✅" if s["reklam_filtre"] else "❌", inline=True)
    embed.add_field(name="🎫 Destek", value=destek_k, inline=True)
    embed.add_field(name="📋 Log", value=log_k, inline=True)
    embed.add_field(name="👋 Hoşgeldin", value=hg_k, inline=True)
    embed.add_field(name="🤖 Oto. Mesaj", value=f"{len(s['otomatik_mesajlar'])} adet", inline=True)
    embed.add_field(name="🛡️ Muaf Rol", value=f"{len(s.get('muaf_roller', []))} rol", inline=True)
    embed.add_field(name="📝 Kara Liste", value=f"{len(s['kara_liste'])} kelime", inline=True)
    embed.add_field(name="📢 Reklam L.", value=f"{len(s.get('reklam_liste', []))} kelime", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════
#  ÇEKİLİŞ SİSTEMİ
# ══════════════════════════════════

aktif_cekilisler = {}

@bot.tree.command(name="çekiliş", description="Çekiliş başlatır.")
@app_commands.describe(ödül="Çekilişin ödülü", süre="Süre (1d, 12h, 30m)", kazanan="Kazanan sayısı")
@app_commands.checks.has_permissions(administrator=True)
async def cekilis(interaction: discord.Interaction, ödül: str, süre: str, kazanan: int = 1):
    saniye = sure_parse(süre)
    if saniye <= 0:
        await interaction.response.send_message("❌ Geçerli süre gir. Örnek: `1d`, `12h`, `30m`", ephemeral=True)
        return
    bitis = discord.utils.utcnow() + timedelta(seconds=saniye)
    embed = discord.Embed(title="🎉 ÇEKİLİŞ 🎉", description=f"**{ödül}** için çekiliş!\n\n🎉 emojisine tıkla!", color=0xFF73FA)
    embed.add_field(name="🏆 Ödül", value=ödül, inline=True)
    embed.add_field(name="👑 Kazanan", value=str(kazanan), inline=True)
    embed.add_field(name="⏱️ Bitiş", value=f"<t:{int(bitis.timestamp())}:R>", inline=True)
    embed.add_field(name="📢 Başlatan", value=interaction.user.mention, inline=True)
    embed.set_footer(text=f"ZernoxCraft • {MC_IP}")
    await interaction.response.send_message("✅ Çekiliş başlatıldı!", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("🎉")
    aktif_cekilisler[msg.id] = {"kanal_id": interaction.channel.id, "odul": ödül, "kazanan_sayisi": kazanan}
    bot.loop.create_task(cekilis_sayaci(msg.id, interaction.channel.id, saniye, ödül, kazanan, interaction.user))

async def cekilis_sayaci(mesaj_id, kanal_id, saniye, odul, kazanan_sayisi, baslatan):
    await asyncio.sleep(saniye)
    kanal = bot.get_channel(kanal_id)
    if not kanal:
        return
    try:
        msg = await kanal.fetch_message(mesaj_id)
    except:
        return
    katilimcilar = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    katilimcilar.append(user)
    if not katilimcilar:
        embed = discord.Embed(title="🎉 Çekiliş Bitti", description=f"**{odul}**\n\n❌ Kimse katılmadı.", color=0xFF4444)
        await msg.edit(embed=embed)
        await kanal.send("😔 Kimse katılmadığı için kazanan yok.")
        return
    kazananlar = random.sample(katilimcilar, min(kazanan_sayisi, len(katilimcilar)))
    kazanan_mentions = " ".join([k.mention for k in kazananlar])
    embed = discord.Embed(title="🎉 Çekiliş Bitti!", description=f"**{odul}**\n\n🏆 **Kazanan:** {kazanan_mentions}", color=0xFFD700)
    embed.add_field(name="👥 Katılımcı", value=str(len(katilimcilar)), inline=True)
    embed.set_footer(text=f"ZernoxCraft • {MC_IP}")
    await msg.edit(embed=embed)
    await kanal.send(f"🎊 Tebrikler {kazanan_mentions}! **{odul}** kazandın!")
    for kazanan in kazananlar:
        try:
            dm = discord.Embed(title="🏆 Çekiliş Kazandınız!", color=0xFFD700)
            dm.add_field(name="Ödül", value=odul, inline=True)
            dm.add_field(name="Sunucu", value="ZernoxCraft", inline=True)
            dm.set_footer(text=f"ZernoxCraft • {MC_IP}")
            await kazanan.send(embed=dm)
        except:
            pass
    if mesaj_id in aktif_cekilisler:
        del aktif_cekilisler[mesaj_id]

# ══════════════════════════════════
#  DESTEK TALEBİ
# ══════════════════════════════════

class DestekModal(discord.ui.Modal, title="Destek Talebi"):
    konu = discord.ui.TextInput(label="Konu", placeholder="Sorununuzu kısaca yazın...", max_length=100)
    aciklama = discord.ui.TextInput(label="Açıklama", style=discord.TextStyle.paragraph, placeholder="Detaylı açıklayın...", max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        s = get_guild_settings(guild.id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        kanal_adi = f"ticket-{interaction.user.name[:15]}".lower().replace(" ", "-")
        try:
            ticket_kanal = await guild.create_text_channel(kanal_adi, overwrites=overwrites)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Kanal oluşturma iznim yok.", ephemeral=True)
            return
        embed = discord.Embed(title="🎫 Destek Talebi", color=0x5865F2, timestamp=datetime.utcnow())
        embed.add_field(name="👤 Kullanıcı", value=interaction.user.mention, inline=True)
        embed.add_field(name="📌 Konu", value=self.konu.value, inline=True)
        embed.add_field(name="📝 Açıklama", value=self.aciklama.value, inline=False)
        await ticket_kanal.send(f"{interaction.user.mention} hoş geldin!", embed=embed, view=KapatView())
        await interaction.response.send_message(f"✅ Kanalın: {ticket_kanal.mention}", ephemeral=True)
        await log_gonder(guild, s, f"🎫 **Ticket** | {interaction.user.mention} | {self.konu.value} | {ticket_kanal.mention}")

class DestekView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Destek Talebi Oluştur", style=discord.ButtonStyle.primary, custom_id="destek_ac")
    async def destek_ac(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DestekModal())

class KapatView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Talebi Kapat", style=discord.ButtonStyle.danger, custom_id="ticket_kapat")
    async def ticket_kapat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Kanal 5 saniye içinde kapanıyor...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.Forbidden:
            pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Yönetici yetkisi gerekli.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Hata: {error}", ephemeral=True)

bot.run(TOKEN)
