import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import asyncio
from datetime import datetime, timedelta
import io
from PIL import Image, ImageDraw, ImageFont
import aiohttp

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("x!", "X!"), intents=intents)

DATA_FILE = "settings.json"

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
            "kufur_sure": 0,
            "reklam_sure": 0,
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

@bot.event
async def on_ready():
    print(f"✅ {bot.user} aktif!")
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

        # KÜFÜR FİLTRE → 1 saat mute
        if s.get("kufur_filtre", True) and kufur_var_mi(message.content, s.get("kara_liste", [])):
            try:
                await message.delete()
                until = discord.utils.utcnow() + timedelta(hours=1)
                await message.author.timeout(until, reason="Küfür filtresi")
                uyari = await message.channel.send(
                    f"⚠️ {message.author.mention}, küfür kullandığın için **1 saat** zaman aşımı aldın!"
                )
                await uyari.delete(delay=6)
                try:
                    dm = discord.Embed(title="🔇 Zaman Aşımı Aldınız", color=0xFFA500)
                    dm.add_field(name="Sunucu", value="XazarCraft", inline=True)
                    dm.add_field(name="Süre", value="1 saat", inline=True)
                    dm.add_field(name="Sebep", value="Küfür kullanımı", inline=False)
                    dm.set_footer(text="XazarCraft • play.xazarcraft.com")
                    await message.author.send(embed=dm)
                except:
                    pass
                await log_gonder(message.guild, s, f"🚫 **Küfür → 1h Mute** | {message.author} | {message.channel.mention} | ||{message.content}||")
            except discord.Forbidden:
                pass
            return

        # REKLAM FİLTRE → 1 gün mute
        if s.get("reklam_filtre", True) and reklam_var_mi(message.content, s.get("reklam_liste", [])):
            try:
                await message.delete()
                until = discord.utils.utcnow() + timedelta(days=1)
                await message.author.timeout(until, reason="Reklam filtresi")
                uyari = await message.channel.send(
                    f"📢 {message.author.mention}, reklam yaptığın için **1 gün** zaman aşımı aldın!"
                )
                await uyari.delete(delay=6)
                try:
                    dm = discord.Embed(title="🔇 Zaman Aşımı Aldınız", color=0xFF4444)
                    dm.add_field(name="Sunucu", value="XazarCraft", inline=True)
                    dm.add_field(name="Süre", value="1 gün", inline=True)
                    dm.add_field(name="Sebep", value="Reklam/link paylaşımı", inline=False)
                    dm.set_footer(text="XazarCraft • play.xazarcraft.com")
                    await message.author.send(embed=dm)
                except:
                    pass
                await log_gonder(message.guild, s, f"🔗 **Reklam → 1d Mute** | {message.author} | {message.channel.mention} | ||{message.content}||")
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
    try:
        kart = await hosgeldin_karti_olustur(member, hosgeldin=True)
        embed = discord.Embed(
            title="👋 Hoş Geldin!",
            description=f"**{member.mention}** XazarCraft sunucusuna hoş geldin!\n\n📋 Kuralları okumayı unutma.\n🎮 IP: `play.xazarcraft.com`",
            color=0x57F287
        )
        embed.set_footer(text=f"Seninle birlikte {member.guild.member_count} kişi olduk!")
        await kanal.send(embed=embed, file=kart)
    except Exception as e:
        print(f"Hoşgeldin hatası: {e}")
        embed = discord.Embed(
            title="👋 Hoş Geldin!",
            description=f"**{member.mention}** XazarCraft sunucusuna hoş geldin!\n\n📋 Kuralları okumayı unutma.\n🎮 IP: `play.xazarcraft.com`",
            color=0x57F287
        )
        embed.set_footer(text=f"Seninle birlikte {member.guild.member_count} kişi olduk!")
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
    try:
        kart = await hosgeldin_karti_olustur(member, hosgeldin=False)
        embed = discord.Embed(
            title="👋 Hoşça Kal!",
            description=f"**{member.name}** bize veda etti.\nBize veda etmen üzücü oldu. 💔",
            color=0xFF4444
        )
        embed.set_footer(text=f"Şu an {member.guild.member_count} kişiyiz.")
        await kanal.send(embed=embed, file=kart)
    except Exception as e:
        print(f"Hoşçakal hatası: {e}")
        embed = discord.Embed(
            title="👋 Hoşça Kal!",
            description=f"**{member.name}** bize veda etti.\nBize veda etmen üzücü oldu. 💔",
            color=0xFF4444
        )
        embed.set_footer(text=f"Şu an {member.guild.member_count} kişiyiz.")
        await kanal.send(embed=embed)

async def hosgeldin_karti_olustur(member: discord.Member, hosgeldin: bool = True) -> discord.File:
    W, H = 800, 250
    img = Image.new("RGBA", (W, H), (30, 31, 34, 255))
    draw = ImageDraw.Draw(img)
    renk = (87, 242, 135) if hosgeldin else (255, 68, 68)
    draw.rectangle([0, 0, W-1, H-1], outline=renk, width=4)
    draw.rectangle([8, 8, W-9, H-9], outline=(60, 62, 68), width=2)
    try:
        avatar_url = str(member.display_avatar.with_size(128).url)
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                avatar_data = await resp.read()
        avatar = Image.open(io.BytesIO(avatar_data)).convert("RGBA").resize((120, 120))
        mask = Image.new("L", (120, 120), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 119, 119], fill=255)
        avatar.putalpha(mask)
        img.paste(avatar, (65, 65), avatar)
        draw.ellipse([62, 62, 185, 185], outline=renk, width=3)
    except:
        draw.ellipse([65, 65, 185, 185], fill=(80, 80, 80), outline=renk, width=3)
    try:
        font_buyuk = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_kucuk = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_mini  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        font_buyuk = ImageFont.load_default()
        font_kucuk = font_buyuk
        font_mini  = font_buyuk
    baslik = "HOS GELDIN!" if hosgeldin else "HOSCA KAL!"
    draw.text((220, 55), baslik, fill=renk, font=font_buyuk)
    draw.text((220, 105), member.name, fill=(255, 255, 255), font=font_kucuk)
    alt = f"Seninle {member.guild.member_count} kisi olduk!" if hosgeldin else "Bize veda etmen uzucu oldu"
    draw.text((220, 145), alt, fill=(180, 180, 180), font=font_mini)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return discord.File(buf, filename="kart.png")

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

def admin_kontrol():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        await ctx.send("❌ Bu komutu kullanmak için **Yönetici** yetkisi gerekli.", delete_after=5)
        return False
    return commands.check(predicate)

# ══════════════════════════════════
#  PREFIX KOMUTLARI
# ══════════════════════════════════

@bot.command(name="owner")
async def owner(ctx):
    embed = discord.Embed(title="👑 Sunucu Kurucusu", description="**FelxeTheGreat**", color=0xFFD700)
    embed.set_footer(text="XazarCraft")
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
        dm_embed = discord.Embed(title="🔨 Sunucudan Uzaklaştırıldınız", color=0xFF4444)
        dm_embed.add_field(name="Sunucu", value="XazarCraft", inline=True)
        dm_embed.add_field(name="Süre", value=sure_metin, inline=True)
        dm_embed.add_field(name="Sebep", value=sebep, inline=False)
        dm_embed.set_footer(text="XazarCraft • play.xazarcraft.com")
        await uye.send(embed=dm_embed)
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

@bot.command(name="mute")
@admin_kontrol()
async def mute(ctx, uye: discord.Member, sure_str: str = None, *, sebep: str = "Belirtilmedi"):
    saniye = sure_parse(sure_str) if sure_str else 600
    sure_metin = sure_format(saniye)
    try:
        dm_embed = discord.Embed(title="🔇 Zaman Aşımı Aldınız", color=0xFFA500)
        dm_embed.add_field(name="Sunucu", value="XazarCraft", inline=True)
        dm_embed.add_field(name="Süre", value=sure_metin, inline=True)
        dm_embed.add_field(name="Sebep", value=sebep, inline=False)
        dm_embed.set_footer(text="XazarCraft • play.xazarcraft.com")
        await uye.send(embed=dm_embed)
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

@bot.command(name="yavaşmod", aliases=["yavasmod"])
@admin_kontrol()
async def yavasmod(ctx, sure_veya_kapat: str, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    if sure_veya_kapat.lower() == "kapat":
        await hedef.edit(slowmode_delay=0)
        embed = discord.Embed(
            title="✅ Yavaş Mod Kapatıldı",
            description=f"{hedef.mention} kanalında yavaş mod kapatıldı.",
            color=0x57F287
        )
    else:
        try:
            saniye = int(sure_veya_kapat)
        except:
            await ctx.send("❌ Kullanım: `x!yavaşmod 5 #kanal` veya `x!yavaşmod kapat #kanal`", delete_after=5)
            return
        if saniye < 0 or saniye > 21600:
            await ctx.send("⚠️ Süre 0-21600 saniye arasında olmalı.", delete_after=5)
            return
        await hedef.edit(slowmode_delay=saniye)
        embed = discord.Embed(
            title="🐢 Yavaş Mod Açıldı",
            description=f"{hedef.mention} kanalında **{saniye} saniye** yavaş mod aktif.",
            color=0xFFA500
        )
    await ctx.send(embed=embed)

@bot.command(name="lock")
@admin_kontrol()
async def lock(ctx, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    overwrites = hedef.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = False
    await hedef.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    embed = discord.Embed(
        title="🔒 Kanal Kilitlendi",
        description=f"{hedef.mention} kanalı kilitlendi. Oyuncular mesaj atamaz.",
        color=0xFF4444
    )
    await ctx.send(embed=embed)
    await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"🔒 **Lock** | {hedef.mention} | Yetkili: {ctx.author}")

@bot.command(name="unlock")
@admin_kontrol()
async def unlock(ctx, kanal: discord.TextChannel = None):
    hedef = kanal or ctx.channel
    overwrites = hedef.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = None
    await hedef.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    embed = discord.Embed(
        title="🔓 Kanal Açıldı",
        description=f"{hedef.mention} kanalı açıldı. Oyuncular tekrar mesaj atabilir.",
        color=0x57F287
    )
    await ctx.send(embed=embed)
    await log_gonder(ctx.guild, get_guild_settings(ctx.guild.id), f"🔓 **Unlock** | {hedef.mention} | Yetkili: {ctx.author}")

# ══════════════════════════════════
#  SLASH KOMUTLARI
# ══════════════════════════════════

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

@bot.tree.command(name="log-kanal-ayarla", description="Bot loglarının gönderileceği kanalı ayarlar.")
@app_commands.checks.has_permissions(administrator=True)
async def log_kanal_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    s = get_guild_settings(interaction.guild.id)
    s["log_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Log kanalı {kanal.mention} olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="kufur-ayarla", description="Küfür filtresini açar veya kapatır.")
@app_commands.choices(durum=[
    app_commands.Choice(name="Açık", value="ac"),
    app_commands.Choice(name="Kapalı", value="kapat"),
])
@app_commands.checks.has_permissions(administrator=True)
async def kufur_ayarla(interaction: discord.Interaction, durum: app_commands.Choice[str]):
    s = get_guild_settings(interaction.guild.id)
    s["kufur_filtre"] = (durum.value == "ac")
    save_guild_settings(interaction.guild.id, s)
    emoji = "✅" if s["kufur_filtre"] else "❌"
    await interaction.response.send_message(f"{emoji} Küfür filtresi **{'açıldı' if s['kufur_filtre'] else 'kapatıldı'}**.", ephemeral=True)

@bot.tree.command(name="kufur-kelime-ekle", description="Küfür listesine özel kelime ekler.")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_kelime_ekle(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() not in s["kara_liste"]:
        s["kara_liste"].append(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` kara listeye eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ `{kelime}` zaten kara listede.", ephemeral=True)

@bot.tree.command(name="kufur-kelime-sil", description="Küfür listesinden kelime siler.")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_kelime_sil(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() in s["kara_liste"]:
        s["kara_liste"].remove(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` kara listeden silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ `{kelime}` bulunamadı.", ephemeral=True)

@bot.tree.command(name="kufur-kelime-liste", description="Kara listedeki kelimeleri gösterir.")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_kelime_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    liste = s.get("kara_liste", [])
    if not liste:
        await interaction.response.send_message("📭 Kara liste boş.", ephemeral=True)
        return
    embed = discord.Embed(title="📝 Kara Liste", color=0xFF4444)
    embed.description = "\n".join([f"`{k}`" for k in liste])
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="reklam-ayarla", description="Reklam/link filtresini açar veya kapatır.")
@app_commands.choices(durum=[
    app_commands.Choice(name="Açık", value="ac"),
    app_commands.Choice(name="Kapalı", value="kapat"),
])
@app_commands.checks.has_permissions(administrator=True)
async def reklam_ayarla(interaction: discord.Interaction, durum: app_commands.Choice[str]):
    s = get_guild_settings(interaction.guild.id)
    s["reklam_filtre"] = (durum.value == "ac")
    save_guild_settings(interaction.guild.id, s)
    emoji = "✅" if s["reklam_filtre"] else "❌"
    await interaction.response.send_message(f"{emoji} Reklam filtresi **{'açıldı' if s['reklam_filtre'] else 'kapatıldı'}**.", ephemeral=True)

@bot.tree.command(name="reklam-ekle", description="Reklam listesine özel kelime/link ekler.")
@app_commands.checks.has_permissions(administrator=True)
async def reklam_ekle(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() not in s["reklam_liste"]:
        s["reklam_liste"].append(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` reklam listesine eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ `{kelime}` zaten reklam listesinde.", ephemeral=True)

@bot.tree.command(name="reklam-sil", description="Reklam listesinden kelime/link siler.")
@app_commands.checks.has_permissions(administrator=True)
async def reklam_sil(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() in s["reklam_liste"]:
        s["reklam_liste"].remove(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` reklam listesinden silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ `{kelime}` bulunamadı.", ephemeral=True)

@bot.tree.command(name="reklam-liste", description="Reklam listesindeki kelimeleri gösterir.")
@app_commands.checks.has_permissions(administrator=True)
async def reklam_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    liste = s.get("reklam_liste", [])
    if not liste:
        await interaction.response.send_message("📭 Reklam listesi boş.", ephemeral=True)
        return
    embed = discord.Embed(title="📢 Reklam Listesi", color=0xFFA500)
    embed.description = "\n".join([f"`{k}`" for k in liste])
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="muaf-rol-ekle", description="Bu role sahip kişiler küfür/reklam filtresinden muaf olur.")
@app_commands.checks.has_permissions(administrator=True)
async def muaf_rol_ekle(interaction: discord.Interaction, rol: discord.Role):
    s = get_guild_settings(interaction.guild.id)
    if str(rol.id) not in s["muaf_roller"]:
        s["muaf_roller"].append(str(rol.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {rol.mention} rolü muaf listeye eklendi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ {rol.mention} zaten muaf listede.", ephemeral=True)

@bot.tree.command(name="muaf-rol-sil", description="Rolü muaf listesinden çıkarır.")
@app_commands.checks.has_permissions(administrator=True)
async def muaf_rol_sil(interaction: discord.Interaction, rol: discord.Role):
    s = get_guild_settings(interaction.guild.id)
    if str(rol.id) in s["muaf_roller"]:
        s["muaf_roller"].remove(str(rol.id))
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ {rol.mention} muaf listesinden çıkarıldı.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ {rol.mention} muaf listede değil.", ephemeral=True)

@bot.tree.command(name="muaf-rol-liste", description="Muaf rollerin listesini gösterir.")
@app_commands.checks.has_permissions(administrator=True)
async def muaf_rol_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    muaf = s.get("muaf_roller", [])
    if not muaf:
        await interaction.response.send_message("📭 Muaf rol listesi boş.", ephemeral=True)
        return
    embed = discord.Embed(title="🛡️ Muaf Roller", color=0x57F287)
    roller = []
    for rid in muaf:
        rol = interaction.guild.get_role(int(rid))
        roller.append(rol.mention if rol else f"Silinmiş Rol ({rid})")
    embed.description = "\n".join(roller)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="otomatikmesaj-ayarla", description="Bir anahtar kelimeye otomatik cevap ekler.")
@app_commands.describe(anahtar="Tetiklenecek anahtar kelime", cevap="Bot'un göndereceği cevap")
@app_commands.checks.has_permissions(administrator=True)
async def otomatikmesaj_ayarla(interaction: discord.Interaction, anahtar: str, cevap: str):
    s = get_guild_settings(interaction.guild.id)
    for om in s["otomatik_mesajlar"]:
        if om["anahtar"].lower() == anahtar.lower():
            om["cevap"] = cevap
            save_guild_settings(interaction.guild.id, s)
            await interaction.response.send_message(f"🔄 `{anahtar}` güncellendi.", ephemeral=True)
            return
    s["otomatik_mesajlar"].append({"anahtar": anahtar.lower(), "cevap": cevap})
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ **{anahtar}** → {cevap}", ephemeral=True)

@bot.tree.command(name="otomatikmesaj-sil", description="Bir otomatik mesajı siler.")
@app_commands.checks.has_permissions(administrator=True)
async def otomatikmesaj_sil(interaction: discord.Interaction, anahtar: str):
    s = get_guild_settings(interaction.guild.id)
    onceki = len(s["otomatik_mesajlar"])
    s["otomatik_mesajlar"] = [om for om in s["otomatik_mesajlar"] if om["anahtar"].lower() != anahtar.lower()]
    if len(s["otomatik_mesajlar"]) < onceki:
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{anahtar}` silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ `{anahtar}` bulunamadı.", ephemeral=True)

@bot.tree.command(name="otomatikmesaj-liste", description="Tüm otomatik mesajları listeler.")
@app_commands.checks.has_permissions(administrator=True)
async def otomatikmesaj_liste(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    mesajlar = s.get("otomatik_mesajlar", [])
    if not mesajlar:
        await interaction.response.send_message("📭 Henüz otomatik mesaj eklenmemiş.", ephemeral=True)
        return
    embed = discord.Embed(title="🤖 Otomatik Mesajlar", color=0x5865F2)
    for i, om in enumerate(mesajlar, 1):
        embed.add_field(name=f"{i}. `{om['anahtar']}`", value=om["cevap"], inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="destek-kanal-ayarla", description="Destek taleplerinin oluşturulacağı kanalı ayarlar.")
@app_commands.checks.has_permissions(administrator=True)
async def destek_kanal_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    s = get_guild_settings(interaction.guild.id)
    s["destek_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    embed = discord.Embed(
        title="🎫 Destek Talebi Oluştur",
        description="Aşağıdaki butona tıklayarak destek talebi oluşturabilirsiniz.\nEkibimiz en kısa sürede size yardımcı olacaktır.",
        color=0x57F287
    )
    view = DestekView()
    await kanal.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Destek paneli {kanal.mention} kanalına gönderildi.", ephemeral=True)

@bot.tree.command(name="ayarlar", description="Mevcut bot ayarlarını gösterir.")
@app_commands.checks.has_permissions(administrator=True)
async def ayarlar(interaction: discord.Interaction):
    s = get_guild_settings(interaction.guild.id)
    guild = interaction.guild
    destek_k = guild.get_channel(int(s["destek_kanal"])).mention if s.get("destek_kanal") else "❌ Ayarlanmadı"
    log_k    = guild.get_channel(int(s["log_kanal"])).mention if s.get("log_kanal") else "❌ Ayarlanmadı"
    hg_k     = guild.get_channel(int(s["hosgeldin_kanal"])).mention if s.get("hosgeldin_kanal") else "❌ Ayarlanmadı"
    embed = discord.Embed(title="⚙️ Bot Ayarları", color=0xFEE75C)
    embed.add_field(name="🚫 Küfür Filtresi",   value="✅ Açık" if s["kufur_filtre"] else "❌ Kapalı", inline=True)
    embed.add_field(name="📢 Reklam Filtresi",  value="✅ Açık" if s["reklam_filtre"] else "❌ Kapalı", inline=True)
    embed.add_field(name="🎫 Destek Kanalı",    value=destek_k, inline=True)
    embed.add_field(name="📋 Log Kanalı",       value=log_k, inline=True)
    embed.add_field(name="👋 Hoşgeldin Kanalı", value=hg_k, inline=True)
    embed.add_field(name="🤖 Otomatik Mesaj",   value=f"{len(s['otomatik_mesajlar'])} adet", inline=True)
    embed.add_field(name="🛡️ Muaf Roller",     value=f"{len(s.get('muaf_roller', []))} rol", inline=True)
    embed.add_field(name="📝 Kara Liste",       value=f"{len(s['kara_liste'])} kelime", inline=True)
    embed.add_field(name="📢 Reklam Listesi",   value=f"{len(s.get('reklam_liste', []))} kelime", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════
#  DESTEK TALEBİ
# ══════════════════════════════════

class DestekModal(discord.ui.Modal, title="Destek Talebi"):
    konu = discord.ui.TextInput(label="Konu", placeholder="Sorununuzu kısaca yazın...", max_length=100)
    aciklama = discord.ui.TextInput(
        label="Açıklama",
        style=discord.TextStyle.paragraph,
        placeholder="Sorununuzu detaylıca açıklayın...",
        max_length=500
    )

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
        embed = discord.Embed(title="🎫 Yeni Destek Talebi", color=0x5865F2, timestamp=datetime.utcnow())
        embed.add_field(name="👤 Kullanıcı", value=interaction.user.mention, inline=True)
        embed.add_field(name="📌 Konu", value=self.konu.value, inline=True)
        embed.add_field(name="📝 Açıklama", value=self.aciklama.value, inline=False)
        kapat_view = KapatView()
        await ticket_kanal.send(f"{interaction.user.mention} hoş geldin!", embed=embed, view=kapat_view)
        await interaction.response.send_message(f"✅ Destek kanalın: {ticket_kanal.mention}", ephemeral=True)
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
        await interaction.response.send_message("🔒 Kanal 5 saniye içinde kapatılıyor...")
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

# ══════════════════════════════════
#  ÇEKİLİŞ SİSTEMİ
# ══════════════════════════════════

aktif_cekilisler = {}  # mesaj_id -> bilgiler

@bot.tree.command(name="çekiliş", description="Çekiliş başlatır.")
@app_commands.describe(
    ödül="Çekilişin ödülü",
    süre="Süre (örn: 1d, 12h, 30m)",
    kazanan="Kazanan sayısı (varsayılan: 1)"
)
@app_commands.checks.has_permissions(administrator=True)
async def cekilis(interaction: discord.Interaction, ödül: str, süre: str, kazanan: int = 1):
    saniye = sure_parse(süre)
    if saniye <= 0:
        await interaction.response.send_message("❌ Geçerli bir süre gir. Örnek: `1d`, `12h`, `30m`", ephemeral=True)
        return

    bitis = discord.utils.utcnow() + timedelta(seconds=saniye)

    embed = discord.Embed(
        title="🎉 ÇEKİLİŞ 🎉",
        description=f"**{ödül}** için çekiliş başladı!\n\nKatılmak için 🎉 emojisine tıkla!",
        color=0xFF73FA
    )
    embed.add_field(name="🏆 Ödül", value=ödül, inline=True)
    embed.add_field(name="👑 Kazanan Sayısı", value=str(kazanan), inline=True)
    embed.add_field(name="⏱️ Bitiş", value=f"<t:{int(bitis.timestamp())}:R>", inline=True)
    embed.add_field(name="📢 Başlatan", value=interaction.user.mention, inline=True)
    embed.set_footer(text="XazarCraft • play.xazarcraft.com")

    await interaction.response.send_message("✅ Çekiliş başlatıldı!", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("🎉")

    aktif_cekilisler[msg.id] = {
        "kanal_id": interaction.channel.id,
        "mesaj_id": msg.id,
        "odul": ödül,
        "kazanan_sayisi": kazanan,
        "baslatan": interaction.user.id,
        "bitis": bitis.timestamp()
    }

    # Arka planda sayaç başlat
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

    # Katılımcıları topla
    katilimcilar = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    katilimcilar.append(user)

    if not katilimcilar:
        embed = discord.Embed(
            title="🎉 Çekiliş Bitti",
            description=f"**{odul}**\n\n❌ Kimse katılmadı, kazanan yok.",
            color=0xFF4444
        )
        embed.set_footer(text="XazarCraft • play.xazarcraft.com")
        await msg.edit(embed=embed)
        await kanal.send("😔 Çekilişe kimse katılmadığı için kazanan belirlenemedi.")
        return

    import random
    kazananlar = random.sample(katilimcilar, min(kazanan_sayisi, len(katilimcilar)))
    kazanan_mentions = " ".join([k.mention for k in kazananlar])

    embed = discord.Embed(
        title="🎉 Çekiliş Bitti!",
        description=f"**{odul}** çekilişi tamamlandı!\n\n🏆 **Kazanan(lar):** {kazanan_mentions}",
        color=0xFFD700
    )
    embed.add_field(name="🏆 Ödül", value=odul, inline=True)
    embed.add_field(name="👥 Katılımcı", value=str(len(katilimcilar)), inline=True)
    embed.add_field(name="📢 Başlatan", value=baslatan.mention, inline=True)
    embed.set_footer(text="XazarCraft • play.xazarcraft.com")
    await msg.edit(embed=embed)

    tebrik = await kanal.send(f"🎊 Tebrikler {kazanan_mentions}! **{odul}** kazandın!")

    # Kazananlara DM at
    for kazanan in kazananlar:
        try:
            dm = discord.Embed(title="🏆 Çekiliş Kazandınız!", color=0xFFD700)
            dm.add_field(name="Ödül", value=odul, inline=True)
            dm.add_field(name="Sunucu", value="XazarCraft", inline=True)
            dm.set_footer(text="XazarCraft • play.xazarcraft.com")
            await kazanan.send(embed=dm)
        except:
            pass

    if mesaj_id in aktif_cekilisler:
        del aktif_cekilisler[mesaj_id]

@bot.tree.command(name="çekiliş-bitir", description="Aktif çekilişi erken bitirir.")
@app_commands.describe(mesaj_id="Çekiliş mesajının ID'si")
@app_commands.checks.has_permissions(administrator=True)
async def cekilis_bitir(interaction: discord.Interaction, mesaj_id: str):
    try:
        mid = int(mesaj_id)
        msg = await interaction.channel.fetch_message(mid)
    except:
        await interaction.response.send_message("❌ Mesaj bulunamadı.", ephemeral=True)
        return

    katilimcilar = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    katilimcilar.append(user)

    bilgi = aktif_cekilisler.get(mid, {})
    odul = bilgi.get("odul", "Bilinmiyor")
    kazanan_sayisi = bilgi.get("kazanan_sayisi", 1)

    if not katilimcilar:
        await interaction.response.send_message("❌ Kimse katılmamış.", ephemeral=True)
        return

    import random
    kazananlar = random.sample(katilimcilar, min(kazanan_sayisi, len(katilimcilar)))
    kazanan_mentions = " ".join([k.mention for k in kazananlar])

    embed = discord.Embed(
        title="🎉 Çekiliş Erken Bitirildi!",
        description=f"**{odul}**\n\n🏆 **Kazanan(lar):** {kazanan_mentions}",
        color=0xFFD700
    )
    embed.set_footer(text="XazarCraft • play.xazarcraft.com")
    await msg.edit(embed=embed)
    await interaction.response.send_message(f"✅ Çekiliş bitirildi! Kazanan: {kazanan_mentions}", ephemeral=True)
    await interaction.channel.send(f"🎊 Tebrikler {kazanan_mentions}! **{odul}** kazandın!")

    for kazanan in kazananlar:
        try:
            dm = discord.Embed(title="🏆 Çekiliş Kazandınız!", color=0xFFD700)
            dm.add_field(name="Ödül", value=odul, inline=True)
            dm.add_field(name="Sunucu", value="XazarCraft", inline=True)
            dm.set_footer(text="XazarCraft • play.xazarcraft.com")
            await kazanan.send(embed=dm)
        except:
            pass

    if mid in aktif_cekilisler:
        del aktif_cekilisler[mid]

bot.run(TOKEN)
