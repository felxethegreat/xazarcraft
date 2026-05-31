import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import asyncio
import random
from datetime import datetime, timedelta

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("e!", "E!"), intents=intents, help_command=None)

DATA_FILE = "settings.json"

# ══════════════════════════════════
#  VERİ YÖNETİMİ
# ══════════════════════════════════

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
            "kufur_filtre": False,
            "reklam_filtre": False,
            "kufur_liste": [],
            "reklam_liste": [],
            "kufur_muaf_roller": [],
            "reklam_muaf_roller": [],
            "log_kanal": None,
            "hosgeldin_kanal": None,
            "destek_kanal": None,
            "otorol": None,
            "yetkili_kullanicilar": [],
        }
        save_data(data)
    return data[gid]

def save_guild_settings(guild_id: int, settings: dict):
    data = load_data()
    data[str(guild_id)] = settings
    save_data(data)

# ══════════════════════════════════
#  YETKİ KONTROLÜ
# ══════════════════════════════════

def yetkili_mi(ctx_or_interaction):
    if isinstance(ctx_or_interaction, commands.Context):
        user = ctx_or_interaction.author
        guild = ctx_or_interaction.guild
    else:
        user = ctx_or_interaction.user
        guild = ctx_or_interaction.guild

    if guild.owner_id == user.id:
        return True

    s = get_guild_settings(guild.id)
    if str(user.id) in s.get("yetkili_kullanicilar", []):
        return True

    return False

def owner_check():
    async def predicate(ctx):
        if yetkili_mi(ctx):
            return True
        await ctx.send("❌ Bu komutu kullanma yetkin yok.", delete_after=5)
        return False
    return commands.check(predicate)

def slash_owner_check(interaction: discord.Interaction) -> bool:
    return yetkili_mi(interaction)

# ══════════════════════════════════
#  YARDIMCI FONKSİYONLAR
# ══════════════════════════════════

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

def kufur_var_mi(metin: str, liste: list) -> bool:
    metin_lower = metin.lower()
    return any(k in metin_lower for k in liste)

def reklam_var_mi(metin: str, liste: list) -> bool:
    metin_lower = metin.lower()
    if re.search(r"https?://\S+", metin_lower):
        return True
    if re.search(r"discord\.gg/\S+", metin_lower):
        return True
    if re.search(r"\.gg/\S+", metin_lower):
        return True
    for kelime in liste:
        if kelime.lower() in metin_lower:
            return True
    return False

def kufur_muaf_mi(member: discord.Member, muaf_roller: list) -> bool:
    if member.guild.owner_id == member.id:
        return True
    s = get_guild_settings(member.guild.id)
    if str(member.id) in s.get("yetkili_kullanicilar", []):
        return True
    return any(str(role.id) in muaf_roller for role in member.roles)

def reklam_muaf_mi(member: discord.Member, muaf_roller: list) -> bool:
    if member.guild.owner_id == member.id:
        return True
    s = get_guild_settings(member.guild.id)
    if str(member.id) in s.get("yetkili_kullanicilar", []):
        return True
    return any(str(role.id) in muaf_roller for role in member.roles)

async def log_gonder(guild: discord.Guild, settings: dict, metin: str):
    kanal_id = settings.get("log_kanal")
    if kanal_id:
        kanal = guild.get_channel(int(kanal_id))
        if kanal:
            embed = discord.Embed(description=metin, color=0xFF4444, timestamp=datetime.utcnow())
            try:
                await kanal.send(embed=embed)
            except:
                pass

# ══════════════════════════════════
#  BOT HAZIR
# ══════════════════════════════════

@bot.event
async def on_ready():
    print(f"✅ {bot.user} aktif!")
    try:
        synced = await bot.tree.sync()
        print(f"📋 {len(synced)} slash komutu senkronize edildi.")
    except Exception as e:
        print(f"❌ {e}")

# ══════════════════════════════════
#  MESAJ DİNLEYİCİ
# ══════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    s = get_guild_settings(message.guild.id)

    # KÜFÜR FİLTRE
    if s.get("kufur_filtre") and s.get("kufur_liste"):
        if not kufur_muaf_mi(message.author, s.get("kufur_muaf_roller", [])):
            if kufur_var_mi(message.content, s["kufur_liste"]):
                try:
                    await message.delete()
                    until = discord.utils.utcnow() + timedelta(hours=1)
                    await message.author.timeout(until, reason="Küfür filtresi")
                    uyari = await message.channel.send(f"⚠️ {message.author.mention}, uygunsuz kelime kullandın! **1 saat** mute aldın.")
                    await uyari.delete(delay=5)
                    try:
                        dm = discord.Embed(title="🔇 Zaman Aşımı", color=0xFFA500)
                        dm.add_field(name="Sebep", value="Küfür kullanımı", inline=True)
                        dm.add_field(name="Süre", value="1 saat", inline=True)
                        await message.author.send(embed=dm)
                    except:
                        pass
                    await log_gonder(message.guild, s, f"🚫 **Küfür** | {message.author} | {message.channel.mention} | ||{message.content}||")
                except:
                    pass
                return

    # REKLAM FİLTRE
    if s.get("reklam_filtre"):
        if not reklam_muaf_mi(message.author, s.get("reklam_muaf_roller", [])):
            if reklam_var_mi(message.content, s.get("reklam_liste", [])):
                try:
                    await message.delete()
                    until = discord.utils.utcnow() + timedelta(days=1)
                    await message.author.timeout(until, reason="Reklam filtresi")
                    uyari = await message.channel.send(f"📢 {message.author.mention}, reklam yaptığın için **1 gün** mute aldın!")
                    await uyari.delete(delay=5)
                    try:
                        dm = discord.Embed(title="🔇 Zaman Aşımı", color=0xFF4444)
                        dm.add_field(name="Sebep", value="Reklam/link paylaşımı", inline=True)
                        dm.add_field(name="Süre", value="1 gün", inline=True)
                        await message.author.send(embed=dm)
                    except:
                        pass
                    await log_gonder(message.guild, s, f"🔗 **Reklam** | {message.author} | {message.channel.mention} | ||{message.content}||")
                except:
                    pass
                return

    await bot.process_commands(message)

# ══════════════════════════════════
#  OTOROL
# ══════════════════════════════════

@bot.event
async def on_member_join(member: discord.Member):
    s = get_guild_settings(member.guild.id)

    # Otorol
    otorol_id = s.get("otorol")
    if otorol_id:
        rol = member.guild.get_role(int(otorol_id))
        if rol:
            try:
                await member.add_roles(rol)
            except:
                pass

    # Hoşgeldin
    kanal_id = s.get("hosgeldin_kanal")
    if kanal_id:
        kanal = member.guild.get_channel(int(kanal_id))
        if kanal:
            embed = discord.Embed(
                description=f"👋 Hoş geldin {member.mention}! Seninle birlikte **{member.guild.member_count}** kişiyiz.\n📋 Kurallara göz atmayı unutma!",
                color=0x57F287
            )
            await kanal.send(embed=embed)

@bot.event
async def on_member_remove(member: discord.Member):
    s = get_guild_settings(member.guild.id)
    kanal_id = s.get("hosgeldin_kanal")
    if kanal_id:
        kanal = member.guild.get_channel(int(kanal_id))
        if kanal:
            embed = discord.Embed(
                description=f"👋 **{member.name}** aramızdan ayrıldı. Görüşmek üzere!",
                color=0xFF4444
            )
            await kanal.send(embed=embed)

# ══════════════════════════════════
#  PREFIX KOMUTLARI (e! / E!)
# ══════════════════════════════════

@bot.command(name="yardım", aliases=["yardim"])
async def yardim(ctx):
    embed = discord.Embed(title="📋 Echo Project Bot Komutları", color=0x5865F2)
    embed.add_field(name="🛡️ Moderasyon", value="`e!ban` `e!kick` `e!mute` `e!unban` `e!kilit` `e!kilitac` `e!sil` `e!uyar` `e!uyarılar` `e!uyarısıfırla`", inline=False)
    embed.add_field(name="👤 Kullanıcı", value="`e!profil` `e!sunucu`", inline=False)
    embed.add_field(name="⚙️ Ayarlar", value="`/kufur-ayarla` `/reklam-ayarla` `/kufur-mesaj-ekle` `/reklam-mesaj-ekle` `/muaf-rol-ekle` `/otorol` `/hosgeldin-ayarla` `/log-kanal-ayarla` `/destek-ayarla`", inline=False)
    embed.add_field(name="🎉 Eğlence", value="`/çekiliş` `/çekiliş-bitir`", inline=False)
    embed.add_field(name="🔧 Diğer", value="`/yaziyaz` `/duyuru` `/kanal-toplu-sil` `/toplu-mesaj-gonder` `/yetki-ver` `/ayarlar`", inline=False)
    embed.set_footer(text="Echo Project")
    await ctx.send(embed=embed)

@bot.command(name="ban")
@owner_check()
async def ban(ctx, uye: discord.Member, sure_str: str = None, *, sebep: str = "Belirtilmedi"):
    sure_metin = sure_format(sure_parse(sure_str)) if sure_str else "Kalıcı"
    try:
        dm = discord.Embed(title="🔨 Sunucudan Uzaklaştırıldınız", color=0xFF4444)
        dm.add_field(name="Süre", value=sure_metin, inline=True)
        dm.add_field(name="Sebep", value=sebep, inline=True)
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

@bot.command(name="kick")
@owner_check()
async def kick(ctx, uye: discord.Member, *, sebep: str = "Belirtilmedi"):
    try:
        dm = discord.Embed(title="👢 Sunucudan Atıldınız", color=0xFF4444)
        dm.add_field(name="Sebep", value=sebep, inline=True)
        await uye.send(embed=dm)
    except:
        pass
    await uye.kick(reason=sebep)
    embed = discord.Embed(title="👢 Kullanıcı Atıldı", color=0xFF4444)
    embed.add_field(name="Kullanıcı", value=str(uye), inline=True)
    embed.add_field(name="Sebep", value=sebep, inline=True)
    embed.add_field(name="Yetkili", value=ctx.author.mention, inline=True)
    await ctx.send(embed=embed)
    await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"👢 **Kick** | {uye} | {sebep} | {ctx.author}")

@bot.command(name="mute")
@owner_check()
async def mute(ctx, uye: discord.Member, sure_str: str = None, *, sebep: str = "Belirtilmedi"):
    saniye = sure_parse(sure_str) if sure_str else 600
    sure_metin = sure_format(saniye)
    try:
        dm = discord.Embed(title="🔇 Zaman Aşımı Aldınız", color=0xFFA500)
        dm.add_field(name="Süre", value=sure_metin, inline=True)
        dm.add_field(name="Sebep", value=sebep, inline=True)
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

@bot.command(name="unban")
@owner_check()
async def unban(ctx, *, kullanici: str):
    banned = [entry async for entry in ctx.guild.bans()]
    for entry in banned:
        if str(entry.user) == kullanici or str(entry.user.id) == kullanici:
            await ctx.guild.unban(entry.user)
            embed = discord.Embed(title="✅ Ban Kaldırıldı", description=f"**{entry.user}** geri alındı.", color=0x57F287)
            await ctx.send(embed=embed)
            return
    await ctx.send("⚠️ Kullanıcı bulunamadı.", delete_after=5)

@bot.command(name="kilit")
@owner_check()
async def kilit(ctx, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    overwrites = hedef.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = False
    await hedef.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    embed = discord.Embed(title="🔒 Kanal Kilitlendi", description=f"{hedef.mention} kilitlendi.", color=0xFF4444)
    await ctx.send(embed=embed)

@bot.command(name="kilitac")
@owner_check()
async def kilitac(ctx, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    overwrites = hedef.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = None
    await hedef.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    embed = discord.Embed(title="🔓 Kanal Açıldı", description=f"{hedef.mention} açıldı.", color=0x57F287)
    await ctx.send(embed=embed)

@bot.command(name="sil")
@owner_check()
async def sil(ctx, miktar: int):
    if miktar < 1 or miktar > 100:
        await ctx.send("⚠️ 1-100 arası bir sayı gir.", delete_after=5)
        return
    await ctx.message.delete()
    silinen = await ctx.channel.purge(limit=miktar)
    bilgi = await ctx.send(f"☑️ **{len(silinen)} mesaj başarıyla silindi!**")
    await bilgi.delete(delay=3)

@bot.command(name="uyar")
@owner_check()
async def uyar(ctx, uye: discord.Member, *, sebep: str = "Belirtilmedi"):
    data = load_data()
    gid = str(ctx.guild.id)
    uid = str(uye.id)
    if "uyarilar" not in data:
        data["uyarilar"] = {}
    if gid not in data["uyarilar"]:
        data["uyarilar"][gid] = {}
    if uid not in data["uyarilar"][gid]:
        data["uyarilar"][gid][uid] = []
    data["uyarilar"][gid][uid].append({
        "sebep": sebep,
        "tarih": datetime.utcnow().strftime("%d.%m.%Y %H:%M"),
        "yetkili": str(ctx.author)
    })
    save_data(data)
    sayi = len(data["uyarilar"][gid][uid])
    embed = discord.Embed(title="⚠️ Uyarı Verildi", color=0xFFA500)
    embed.add_field(name="Kullanıcı", value=uye.mention, inline=True)
    embed.add_field(name="Uyarı", value=f"{sayi}. uyarı", inline=True)
    embed.add_field(name="Sebep", value=sebep, inline=False)
    await ctx.send(embed=embed)
    try:
        dm = discord.Embed(title="⚠️ Uyarı Aldınız", color=0xFFA500)
        dm.add_field(name="Uyarı", value=f"{sayi}. uyarı", inline=True)
        dm.add_field(name="Sebep", value=sebep, inline=True)
        await uye.send(embed=dm)
    except:
        pass
    if sayi >= 3:
        await uye.ban(reason="3 uyarı limitine ulaşıldı")
        await ctx.send(f"🔨 {uye.mention} **3 uyarı** aldığı için otomatik banlandı!")
        await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"🔨 **Otomatik Ban** | {uye} | 3 uyarı")

@bot.command(name="uyarılar", aliases=["uyarilar"])
@owner_check()
async def uyarilar(ctx, uye: discord.Member):
    data = load_data()
    liste = data.get("uyarilar", {}).get(str(ctx.guild.id), {}).get(str(uye.id), [])
    if not liste:
        await ctx.send(f"✅ {uye.mention} hiç uyarı almamış.", delete_after=8)
        return
    embed = discord.Embed(title=f"⚠️ {uye.name} Uyarıları", color=0xFFA500)
    for i, u in enumerate(liste, 1):
        embed.add_field(name=f"{i}. Uyarı", value=f"Sebep: {u['sebep']}\nTarih: {u['tarih']}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="uyarısıfırla", aliases=["uyarisifirla"])
@owner_check()
async def uyari_sifirla(ctx, uye: discord.Member):
    data = load_data()
    gid = str(ctx.guild.id)
    uid = str(uye.id)
    if "uyarilar" in data and gid in data["uyarilar"] and uid in data["uyarilar"][gid]:
        data["uyarilar"][gid][uid] = []
        save_data(data)
    await ctx.send(f"✅ {uye.mention} uyarıları sıfırlandı.")

@bot.command(name="profil")
@owner_check()
async def profil(ctx, uye: discord.Member = None):
    uye = uye or ctx.author
    embed = discord.Embed(title=f"👤 {uye.name}", color=uye.color)
    embed.set_thumbnail(url=uye.display_avatar.url)
    embed.add_field(name="🆔 ID", value=str(uye.id), inline=True)
    embed.add_field(name="📅 Hesap Açılış", value=uye.created_at.strftime("%d.%m.%Y"), inline=True)
    embed.add_field(name="📥 Sunucuya Katılış", value=uye.joined_at.strftime("%d.%m.%Y"), inline=True)
    roller = [r.mention for r in uye.roles if r.name != "@everyone"]
    embed.add_field(name=f"🎭 Roller ({len(roller)})", value=" ".join(roller) if roller else "Yok", inline=False)
    data = load_data()
    uyari_sayi = len(data.get("uyarilar", {}).get(str(ctx.guild.id), {}).get(str(uye.id), []))
    embed.add_field(name="⚠️ Uyarı", value=str(uyari_sayi), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="sunucu")
async def sunucu(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"📊 {guild.name}", color=0x5865F2)
    embed.add_field(name="👥 Üye", value=str(guild.member_count), inline=True)
    embed.add_field(name="💬 Kanal", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="🎭 Rol", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="📅 Kuruluş", value=guild.created_at.strftime("%d.%m.%Y"), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="Echo Project")
    await ctx.send(embed=embed)

# ══════════════════════════════════
#  SLASH KOMUTLARI
# ══════════════════════════════════

@bot.tree.command(name="yardim", description="Tüm bot komutlarını listeler.")
async def slash_yardim(interaction: discord.Interaction):
    embed = discord.Embed(title="📋 Echo Project Bot Komutları", color=0x5865F2)
    embed.add_field(name="🛡️ Moderasyon", value="`e!ban` `e!kick` `e!mute` `e!unban` `e!kilit` `e!kilitac` `e!sil` `e!uyar` `e!uyarılar` `e!uyarısıfırla`", inline=False)
    embed.add_field(name="👤 Kullanıcı", value="`e!profil` `e!sunucu`", inline=False)
    embed.add_field(name="⚙️ Ayarlar", value="`/kufur-ayarla` `/reklam-ayarla` `/kufur-mesaj-ekle` `/reklam-mesaj-ekle` `/muaf-rol-ekle` `/otorol` `/hosgeldin-ayarla` `/log-kanal-ayarla` `/destek-ayarla`", inline=False)
    embed.add_field(name="🎉 Eğlence", value="`/çekiliş` `/çekiliş-bitir`", inline=False)
    embed.add_field(name="🔧 Diğer", value="`/yaziyaz` `/duyuru` `/kanal-toplu-sil` `/toplu-mesaj-gonder` `/yetki-ver` `/ayarlar`", inline=False)
    embed.set_footer(text="Echo Project")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ayarlar", description="Bot ayarlarını gösterir.")
async def ayarlar(interaction: discord.Interaction):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    guild = interaction.guild
    log_k = guild.get_channel(int(s["log_kanal"])).mention if s.get("log_kanal") else "❌"
    hg_k = guild.get_channel(int(s["hosgeldin_kanal"])).mention if s.get("hosgeldin_kanal") else "❌"
    dk_k = guild.get_channel(int(s["destek_kanal"])).mention if s.get("destek_kanal") else "❌"
    otorol = guild.get_role(int(s["otorol"])).mention if s.get("otorol") else "❌"
    embed = discord.Embed(title="⚙️ Bot Ayarları", color=0xFEE75C)
    embed.add_field(name="🚫 Küfür Filtresi", value="✅ Açık" if s["kufur_filtre"] else "❌ Kapalı", inline=True)
    embed.add_field(name="📢 Reklam Filtresi", value="✅ Açık" if s["reklam_filtre"] else "❌ Kapalı", inline=True)
    embed.add_field(name="📝 Küfür Listesi", value=f"{len(s['kufur_liste'])} kelime", inline=True)
    embed.add_field(name="🔗 Reklam Listesi", value=f"{len(s['reklam_liste'])} kelime", inline=True)
    embed.add_field(name="🛡️ Küfür Muaf", value=f"{len(s['kufur_muaf_roller'])} rol", inline=True)
    embed.add_field(name="🛡️ Reklam Muaf", value=f"{len(s['reklam_muaf_roller'])} rol", inline=True)
    embed.add_field(name="📋 Log Kanalı", value=log_k, inline=True)
    embed.add_field(name="👋 Hoşgeldin", value=hg_k, inline=True)
    embed.add_field(name="🎫 Destek", value=dk_k, inline=True)
    embed.add_field(name="🎭 Otorol", value=otorol, inline=True)
    embed.add_field(name="👑 Yetkili", value=f"{len(s.get('yetkili_kullanicilar', []))} kişi", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="kufur-ayarla", description="Küfür filtresini açar veya kapatır.")
@app_commands.choices(durum=[app_commands.Choice(name="Açık", value="ac"), app_commands.Choice(name="Kapalı", value="kapat")])
async def kufur_ayarla(interaction: discord.Interaction, durum: app_commands.Choice[str]):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    s["kufur_filtre"] = (durum.value == "ac")
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"{'✅' if s['kufur_filtre'] else '❌'} Küfür filtresi **{'açıldı' if s['kufur_filtre'] else 'kapatıldı'}**.", ephemeral=True)

@bot.tree.command(name="reklam-ayarla", description="Reklam filtresini açar veya kapatır.")
@app_commands.choices(durum=[app_commands.Choice(name="Açık", value="ac"), app_commands.Choice(name="Kapalı", value="kapat")])
async def reklam_ayarla(interaction: discord.Interaction, durum: app_commands.Choice[str]):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    s["reklam_filtre"] = (durum.value == "ac")
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"{'✅' if s['reklam_filtre'] else '❌'} Reklam filtresi **{'açıldı' if s['reklam_filtre'] else 'kapatıldı'}**.", ephemeral=True)

@bot.tree.command(name="kufur-mesaj-ekle", description="Küfür listesine kelime ekler.")
@app_commands.describe(kelime="Eklenecek kelime")
async def kufur_mesaj_ekle(interaction: discord.Interaction, kelime: str):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() not in s["kufur_liste"]:
        s["kufur_liste"].append(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` küfür listesine eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten listede.", ephemeral=True)

@bot.tree.command(name="kufur-mesaj-cikar", description="Küfür listesinden kelime çıkarır.")
@app_commands.describe(kelime="Çıkarılacak kelime")
async def kufur_mesaj_cikar(interaction: discord.Interaction, kelime: str):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() in s["kufur_liste"]:
        s["kufur_liste"].remove(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` çıkarıldı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Bulunamadı.", ephemeral=True)

@bot.tree.command(name="kufur-mesaj-liste", description="Küfür listesini gösterir.")
async def kufur_mesaj_liste(interaction: discord.Interaction):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    liste = s.get("kufur_liste", [])
    if not liste:
        await interaction.response.send_message("📭 Küfür listesi boş.", ephemeral=True)
        return
    embed = discord.Embed(title="📝 Küfür Listesi", color=0xFF4444, description="\n".join([f"`{k}`" for k in liste]))
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="reklam-mesaj-ekle", description="Reklam listesine kelime/link ekler.")
@app_commands.describe(kelime="Eklenecek kelime veya link")
async def reklam_mesaj_ekle(interaction: discord.Interaction, kelime: str):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() not in s["reklam_liste"]:
        s["reklam_liste"].append(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` reklam listesine eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten listede.", ephemeral=True)

@bot.tree.command(name="reklam-mesaj-cikar", description="Reklam listesinden kelime/link çıkarır.")
@app_commands.describe(kelime="Çıkarılacak kelime")
async def reklam_mesaj_cikar(interaction: discord.Interaction, kelime: str):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() in s["reklam_liste"]:
        s["reklam_liste"].remove(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` çıkarıldı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Bulunamadı.", ephemeral=True)

@bot.tree.command(name="reklam-mesaj-liste", description="Reklam listesini gösterir.")
async def reklam_mesaj_liste(interaction: discord.Interaction):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    liste = s.get("reklam_liste", [])
    if not liste:
        await interaction.response.send_message("📭 Reklam listesi boş.", ephemeral=True)
        return
    embed = discord.Embed(title="📢 Reklam Listesi", color=0xFFA500, description="\n".join([f"`{k}`" for k in liste]))
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="muaf-rol-ekle", description="Rolü küfür veya reklam filtresinden muaf yapar.")
@app_commands.describe(rol="Muaf yapılacak rol", filtre="Hangi filtreden muaf olsun?")
@app_commands.choices(filtre=[app_commands.Choice(name="Küfür", value="kufur"), app_commands.Choice(name="Reklam", value="reklam")])
async def muaf_rol_ekle(interaction: discord.Interaction, rol: discord.Role, filtre: app_commands.Choice[str]):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    key = "kufur_muaf_roller" if filtre.value == "kufur" else "reklam_muaf_roller"
    if str(rol.id) not in s[key]:
        s[key].append(str(rol.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {rol.mention} **{filtre.name}** filtresinden muaf yapıldı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten muaf listede.", ephemeral=True)

@bot.tree.command(name="muaf-rol-cikar", description="Rolü muaf listesinden çıkarır.")
@app_commands.describe(rol="Çıkarılacak rol", filtre="Hangi filtreden?")
@app_commands.choices(filtre=[app_commands.Choice(name="Küfür", value="kufur"), app_commands.Choice(name="Reklam", value="reklam")])
async def muaf_rol_cikar(interaction: discord.Interaction, rol: discord.Role, filtre: app_commands.Choice[str]):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    key = "kufur_muaf_roller" if filtre.value == "kufur" else "reklam_muaf_roller"
    if str(rol.id) in s[key]:
        s[key].remove(str(rol.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {rol.mention} çıkarıldı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Bulunamadı.", ephemeral=True)

@bot.tree.command(name="muaf-rol-liste", description="Muaf rolleri listeler.")
async def muaf_rol_liste(interaction: discord.Interaction):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    guild = interaction.guild
    embed = discord.Embed(title="🛡️ Muaf Roller", color=0x57F287)
    kufur = [guild.get_role(int(r)).mention if guild.get_role(int(r)) else f"({r})" for r in s["kufur_muaf_roller"]]
    reklam = [guild.get_role(int(r)).mention if guild.get_role(int(r)) else f"({r})" for r in s["reklam_muaf_roller"]]
    embed.add_field(name="🚫 Küfür Muaf", value="\n".join(kufur) if kufur else "Yok", inline=True)
    embed.add_field(name="📢 Reklam Muaf", value="\n".join(reklam) if reklam else "Yok", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="yavasmod", description="Kanalda yavaş mod açar veya kapatır.")
@app_commands.describe(saniye="Süre (0 = kapat)", kanal="Kanal seç (boş bırakırsan mevcut kanal)")
async def yavasmod(interaction: discord.Interaction, saniye: int, kanal: discord.TextChannel = None):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    hedef = kanal or interaction.channel
    await hedef.edit(slowmode_delay=saniye)
    if saniye == 0:
        await interaction.response.send_message(f"✅ {hedef.mention} yavaş mod kapatıldı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"🐢 {hedef.mention} kanalında **{saniye} saniye** yavaş mod açıldı.", ephemeral=True)

@bot.tree.command(name="otorol", description="Sunucuya giren herkese otomatik rol verir.")
@app_commands.describe(rol="Verilecek rol")
async def otorol(interaction: discord.Interaction, rol: discord.Role):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    s["otorol"] = str(rol.id)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Otorol **{rol.mention}** olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="hosgeldin-ayarla", description="Hoşgeldin/Hoşçakal kanalını ayarlar.")
@app_commands.describe(kanal="Kanal seç")
async def hosgeldin_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    s["hosgeldin_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Hoşgeldin kanalı {kanal.mention} olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="log-kanal-ayarla", description="Log kanalını ayarlar.")
@app_commands.describe(kanal="Kanal seç")
async def log_kanal_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    s["log_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Log kanalı {kanal.mention} olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="destek-ayarla", description="Destek panelini gönderir.")
@app_commands.describe(kanal="Kanal seç")
async def destek_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    s["destek_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    embed = discord.Embed(title="🎫 Destek Talebi Oluştur", description="Aşağıdaki butona tıklayarak destek talebi oluşturabilirsiniz.", color=0x57F287)
    await kanal.send(embed=embed, view=DestekView())
    await interaction.response.send_message(f"✅ Destek paneli {kanal.mention} kanalına gönderildi.", ephemeral=True)

@bot.tree.command(name="yaziyaz", description="Botun ağzından mesaj gönderir.")
@app_commands.describe(yazi="Gönderilecek mesaj")
async def yaziyaz(interaction: discord.Interaction, yazi: str):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Gönderildi.", ephemeral=True)
    await interaction.channel.send(yazi)

@bot.tree.command(name="duyuru", description="Belirtilen kanala duyuru gönderir.")
@app_commands.describe(kanal="Duyuru kanalı", mesaj="Duyuru metni")
async def duyuru(interaction: discord.Interaction, kanal: discord.TextChannel, mesaj: str):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    embed = discord.Embed(title="📢 Duyuru", description=mesaj, color=0xFEE75C, timestamp=datetime.utcnow())
    embed.set_footer(text=f"Duyuran: {interaction.user.name}")
    await kanal.send(embed=embed)
    await interaction.response.send_message(f"✅ Duyuru {kanal.mention} kanalına gönderildi.", ephemeral=True)

@bot.tree.command(name="kanal-toplu-sil", description="Birden fazla kanalı siler.")
@app_commands.describe(kanal1="1. kanal", kanal2="2. kanal", kanal3="3. kanal", kanal4="4. kanal", kanal5="5. kanal")
async def kanal_toplu_sil(interaction: discord.Interaction,
    kanal1: discord.TextChannel,
    kanal2: discord.TextChannel = None,
    kanal3: discord.TextChannel = None,
    kanal4: discord.TextChannel = None,
    kanal5: discord.TextChannel = None):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    kanallar = [k for k in [kanal1, kanal2, kanal3, kanal4, kanal5] if k is not None]
    silinen = []
    for k in kanallar:
        try:
            await k.delete()
            silinen.append(k.name)
        except:
            pass
    await interaction.followup.send(f"☑️ **{len(silinen)} kanal başarıyla silindi!**\n" + "\n".join([f"• #{n}" for n in silinen]), ephemeral=True)

@bot.tree.command(name="toplu-mesaj-gonder", description="Belirtilen kanala aynı mesajı birden fazla gönderir.")
@app_commands.describe(kanal="Hedef kanal", sayi="Kaç kez gönderilsin? (max 10)", mesaj="Gönderilecek mesaj")
async def toplu_mesaj_gonder(interaction: discord.Interaction, kanal: discord.TextChannel, sayi: int, mesaj: str):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    if sayi < 1 or sayi > 10:
        await interaction.response.send_message("⚠️ 1-10 arası bir sayı gir.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Mesaj {sayi} kez gönderiliyor...", ephemeral=True)
    for _ in range(sayi):
        await kanal.send(mesaj)
        await asyncio.sleep(0.5)

@bot.tree.command(name="yetki-ver", description="Kullanıcıya bot komutlarını kullanma yetkisi verir.")
@app_commands.describe(kullanici="Yetki verilecek kullanıcı")
async def yetki_ver(interaction: discord.Interaction, kullanici: discord.Member):
    if interaction.guild.owner_id != interaction.user.id:
        await interaction.response.send_message("❌ Sadece sunucu sahibi yetki verebilir.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    if str(kullanici.id) not in s["yetkili_kullanicilar"]:
        s["yetkili_kullanicilar"].append(str(kullanici.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {kullanici.mention} artık bot komutlarını kullanabilir.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten yetkili.", ephemeral=True)

@bot.tree.command(name="yetki-al", description="Kullanıcının bot yetkisini alır.")
@app_commands.describe(kullanici="Yetkisi alınacak kullanıcı")
async def yetki_al(interaction: discord.Interaction, kullanici: discord.Member):
    if interaction.guild.owner_id != interaction.user.id:
        await interaction.response.send_message("❌ Sadece sunucu sahibi yetki alabilir.", ephemeral=True)
        return
    s = get_guild_settings(interaction.guild.id)
    if str(kullanici.id) in s["yetkili_kullanicilar"]:
        s["yetkili_kullanicilar"].remove(str(kullanici.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {kullanici.mention} yetkisi alındı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ Zaten yetkisiz.", ephemeral=True)

# ══════════════════════════════════
#  ÇEKİLİŞ SİSTEMİ
# ══════════════════════════════════

aktif_cekilisler = {}

@bot.tree.command(name="çekiliş", description="Çekiliş başlatır.")
@app_commands.describe(ödül="Ödül", süre="Süre (1d, 12h, 30m)", kazanan="Kazanan sayısı")
async def cekilis(interaction: discord.Interaction, ödül: str, süre: str, kazanan: int = 1):
    if not slash_owner_check(interaction):
        await interaction.response.send_message("❌ Yetkin yok.", ephemeral=True)
        return
    saniye = sure_parse(süre)
    if saniye <= 0:
        await interaction.response.send_message("❌ Geçerli süre gir. Örn: `1d`, `12h`, `30m`", ephemeral=True)
        return
    bitis = discord.utils.utcnow() + timedelta(seconds=saniye)
    embed = discord.Embed(title="🎉 ÇEKİLİŞ 🎉", description=f"**{ödül}** için çekiliş!\n\n🎉 emojisine tıkla!", color=0xFF73FA)
    embed.add_field(name="🏆 Ödül", value=ödül, inline=True)
    embed.add_field(name="👑 Kazanan", value=str(kazanan), inline=True)
    embed.add_field(name="⏱️ Bitiş", value=f"<t:{int(bitis.timestamp())}:R>", inline=True)
    embed.set_footer(text="Echo Project")
    await interaction.response.send_message("✅ Çekiliş başlatıldı!", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("🎉")
    aktif_cekilisler[msg.id] = {"kanal_id": interaction.channel.id, "odul": ödül, "kazanan_sayisi": kazanan}
    bot.loop.create_task(cekilis_sayaci(msg.id, interaction.channel.id, saniye, ödül, kazanan))

async def cekilis_sayaci(mesaj_id, kanal_id, saniye, odul, kazanan_sayisi):
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
    embed.set_footer(text="Echo Project")
    await msg.edit(embed=embed)
    await kanal.send(f"🎊 Tebrikler {kazanan_mentions}! **{odul}** kazandın!")
    for kazanan in kazananlar:
        try:
            dm = discord.Embed(title="🏆 Çekiliş Kazandınız!", color=0xFFD700)
            dm.add_field(name="Ödül", value=odul, inline=True)
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
        except:
            await interaction.response.send_message("❌ Kanal oluşturulamadı.", ephemeral=True)
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
        except:
            pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    try:
        await interaction.response.send_message(f"❌ Hata: {error}", ephemeral=True)
    except:
        pass

bot.run(TOKEN)
