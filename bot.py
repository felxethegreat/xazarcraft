import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import asyncio
from datetime import datetime

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="x!", intents=intents)

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
            "otomatik_mesajlar": [],
            "kara_liste": [],
            "muaf_roller": [],
            "kufur_sure": 0,
            "reklam_sure": 0,
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

REKLAM_PATTERNLERI = [
    r"discord\.gg/\S+",
    r"discord\.com/invite/\S+",
    r"https?://\S+",
    r"http?://\S+",
    r"\.gg/\S+",
    r"@everyone.*join",
    r"free\s*nitro",
]

def kufur_var_mi(metin: str, kara_liste: list) -> bool:
    metin_lower = metin.lower()
    tum_liste = KUFUR_LISTESI + kara_liste
    return any(kelime in metin_lower for kelime in tum_liste)

def reklam_var_mi(metin: str) -> bool:
    metin_lower = metin.lower()
    return any(re.search(pattern, metin_lower) for pattern in REKLAM_PATTERNLERI)

def muaf_mi(member: discord.Member, muaf_roller: list) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(str(role.id) in muaf_roller for role in member.roles)

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
        if s.get("kufur_filtre", True) and kufur_var_mi(message.content, s.get("kara_liste", [])):
            try:
                await message.delete()
                sure = s.get("kufur_sure", 0)
                uyari_metin = f"⚠️ {message.author.mention}, uygunsuz kelime kullandın! Bu mesaj silindi."
                if sure > 0:
                    uyari_metin += f" {sure} saniye beklemelisin."
                uyari = await message.channel.send(uyari_metin)
                await uyari.delete(delay=5)
                await log_gonder(message.guild, s, f"🚫 **Küfür Filtresi** | {message.author} | {message.channel.mention} | ||{message.content}||")
            except discord.Forbidden:
                pass
            return

        if s.get("reklam_filtre", True) and reklam_var_mi(message.content):
            try:
                await message.delete()
                sure = s.get("reklam_sure", 0)
                uyari_metin = f"📢 {message.author.mention}, reklam/link paylaşmak yasaktır! Mesajın silindi."
                if sure > 0:
                    uyari_metin += f" {sure} saniye beklemelisin."
                uyari = await message.channel.send(uyari_metin)
                await uyari.delete(delay=5)
                await log_gonder(message.guild, s, f"🔗 **Reklam Filtresi** | {message.author} | {message.channel.mention} | ||{message.content}||")
            except discord.Forbidden:
                pass
            return

    for om in s.get("otomatik_mesajlar", []):
        if om["anahtar"].lower() in message.content.lower():
            await message.channel.send(om["cevap"])
            break

    await bot.process_commands(message)

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

# ══════════════════════════════════
#  x!sil
# ══════════════════════════════════
@bot.command(name="sil")
@commands.has_permissions(manage_messages=True)
async def sil(ctx, miktar: int):
    if miktar < 1 or miktar > 100:
        await ctx.send("⚠️ 1 ile 100 arasında bir sayı gir.", delete_after=5)
        return
    await ctx.message.delete()
    silinen = await ctx.channel.purge(limit=miktar)
    bilgi = await ctx.send(f"🗑️ {len(silinen)} mesaj silindi.")
    await bilgi.delete(delay=4)

@sil.error
async def sil_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Mesaj silme yetkin yok.", delete_after=5)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Kullanım: `x!sil 10`", delete_after=5)

# ══════════════════════════════════
#  SLASH KOMUTLARI
# ══════════════════════════════════

@bot.tree.command(name="log-kanal-ayarla", description="Bot loglarının gönderileceği kanalı ayarlar.")
@app_commands.describe(kanal="Log kanalını seçin")
@app_commands.checks.has_permissions(administrator=True)
async def log_kanal_ayarla(interaction: discord.Interaction, kanal: discord.TextChannel):
    s = get_guild_settings(interaction.guild.id)
    s["log_kanal"] = str(kanal.id)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Log kanalı {kanal.mention} olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="kufur-ayarla", description="Küfür filtresini açar veya kapatır.")
@app_commands.describe(durum="Açık mı kapalı mı?")
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

@bot.tree.command(name="kufur-sure-ayarla", description="Küfür sonrası uyarı süresi (saniye).")
@app_commands.describe(saniye="Süre (0 = kapalı)")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_sure_ayarla(interaction: discord.Interaction, saniye: int):
    s = get_guild_settings(interaction.guild.id)
    s["kufur_sure"] = max(0, saniye)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Küfür uyarı süresi **{saniye} saniye** olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="kufur-kelime-ekle", description="Küfür listesine özel kelime ekler.")
@app_commands.describe(kelime="Eklenecek yasaklı kelime")
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
@app_commands.describe(kelime="Silinecek kelime")
@app_commands.checks.has_permissions(administrator=True)
async def kufur_kelime_sil(interaction: discord.Interaction, kelime: str):
    s = get_guild_settings(interaction.guild.id)
    if kelime.lower() in s["kara_liste"]:
        s["kara_liste"].remove(kelime.lower())
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{kelime}` kara listeden silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ `{kelime}` kara listede bulunamadı.", ephemeral=True)

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
@app_commands.describe(durum="Açık mı kapalı mı?")
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

@bot.tree.command(name="reklam-sure-ayarla", description="Reklam sonrası uyarı süresi (saniye).")
@app_commands.describe(saniye="Süre (0 = kapalı)")
@app_commands.checks.has_permissions(administrator=True)
async def reklam_sure_ayarla(interaction: discord.Interaction, saniye: int):
    s = get_guild_settings(interaction.guild.id)
    s["reklam_sure"] = max(0, saniye)
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Reklam uyarı süresi **{saniye} saniye** olarak ayarlandı.", ephemeral=True)

@bot.tree.command(name="muaf-rol-ekle", description="Bu role sahip kişiler küfür/reklam filtresinden muaf olur.")
@app_commands.describe(rol="Muaf yapılacak rol")
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
@app_commands.describe(rol="Muaf listesinden çıkarılacak rol")
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
            await interaction.response.send_message(f"🔄 `{anahtar}` anahtarının cevabı güncellendi.", ephemeral=True)
            return
    s["otomatik_mesajlar"].append({"anahtar": anahtar.lower(), "cevap": cevap})
    save_guild_settings(interaction.guild.id, s)
    await interaction.response.send_message(f"✅ Otomatik mesaj eklendi!\n> **Anahtar:** `{anahtar}`\n> **Cevap:** {cevap}", ephemeral=True)

@bot.tree.command(name="otomatikmesaj-sil", description="Bir otomatik mesajı siler.")
@app_commands.describe(anahtar="Silinecek anahtar kelime")
@app_commands.checks.has_permissions(administrator=True)
async def otomatikmesaj_sil(interaction: discord.Interaction, anahtar: str):
    s = get_guild_settings(interaction.guild.id)
    onceki = len(s["otomatik_mesajlar"])
    s["otomatik_mesajlar"] = [om for om in s["otomatik_mesajlar"] if om["anahtar"].lower() != anahtar.lower()]
    if len(s["otomatik_mesajlar"]) < onceki:
        save_guild_settings(interaction.guild.id, s)
        await interaction.response.send_message(f"✅ `{anahtar}` anahtarlı otomatik mesaj silindi.", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ `{anahtar}` anahtarı bulunamadı.", ephemeral=True)

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
@app_commands.describe(kanal="Destek talep mesajının gönderileceği kanal")
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
    embed = discord.Embed(title="⚙️ Bot Ayarları", color=0xFEE75C)
    embed.add_field(name="🚫 Küfür Filtresi",  value="✅ Açık" if s["kufur_filtre"] else "❌ Kapalı", inline=True)
    embed.add_field(name="📢 Reklam Filtresi", value="✅ Açık" if s["reklam_filtre"] else "❌ Kapalı", inline=True)
    embed.add_field(name="⏱️ Küfür Süresi",   value=f"{s.get('kufur_sure', 0)} sn", inline=True)
    embed.add_field(name="⏱️ Reklam Süresi",  value=f"{s.get('reklam_sure', 0)} sn", inline=True)
    embed.add_field(name="🎫 Destek Kanalı",   value=destek_k, inline=True)
    embed.add_field(name="📋 Log Kanalı",      value=log_k, inline=True)
    embed.add_field(name="🤖 Otomatik Mesaj",  value=f"{len(s['otomatik_mesajlar'])} adet", inline=True)
    embed.add_field(name="📝 Kara Liste",      value=f"{len(s['kara_liste'])} kelime", inline=True)
    embed.add_field(name="🛡️ Muaf Roller",    value=f"{len(s.get('muaf_roller', []))} rol", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════
#  DESTEK TALEBİ SİSTEMİ
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
            ticket_kanal = await guild.create_text_channel(kanal_adi, overwrites=overwrites, reason=f"Destek talebi: {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Kanal oluşturma iznim yok.", ephemeral=True)
            return
        embed = discord.Embed(title="🎫 Yeni Destek Talebi", color=0x5865F2, timestamp=datetime.utcnow())
        embed.add_field(name="👤 Kullanıcı", value=interaction.user.mention, inline=True)
        embed.add_field(name="📌 Konu", value=self.konu.value, inline=True)
        embed.add_field(name="📝 Açıklama", value=self.aciklama.value, inline=False)
        embed.set_footer(text=f"ID: {interaction.user.id}")
        kapat_view = KapatView()
        await ticket_kanal.send(f"{interaction.user.mention} hoş geldin!", embed=embed, view=kapat_view)
        await interaction.response.send_message(f"✅ Destek kanalın oluşturuldu: {ticket_kanal.mention}", ephemeral=True)
        await log_gonder(guild, s, f"🎫 **Yeni Ticket** | {interaction.user.mention} | Konu: {self.konu.value} | {ticket_kanal.mention}")

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
            await interaction.channel.delete(reason=f"Ticket kapatıldı: {interaction.user}")
        except discord.Forbidden:
            pass

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Bu komutu kullanmak için **Yönetici** yetkisine sahip olmalısın.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Bir hata oluştu: {error}", ephemeral=True)

bot.run(TOKEN)
