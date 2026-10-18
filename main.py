
import os
import random
import asyncio
import threading
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin
from xml.etree import ElementTree

import aiohttp
import discord
from discord.ext import commands


# ============================================================
# CONFIGURACION
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"

# ID numerico del bot Miku. Opcional hasta que integremos ambos.
MIKU_BOT_ID = os.getenv("MIKU_BOT_ID", "").strip()

# ID de tu usuario de Discord para controlar comandos sensibles.
# Recomendado: configurar OWNER_ID en las variables de Render.
OWNER_ID = os.getenv("OWNER_ID", "").strip()

COD_BLOG_URL = "https://www.callofduty.com/blog"
COD_NEWS_FEED = "https://www.callofduty.com/rss"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("soap")


# ============================================================
# SERVIDOR WEB PARA RENDER
# ============================================================

class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"Soap esta operativo."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b"No encontrado."
            self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def run_web_server():
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), WebHandler)
    log.info("Servidor web iniciado en el puerto %s", port)
    server.serve_forever()


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None
)

# Evita respuestas repetidas a Miku.
ultimo_mensaje_miku = {}
cooldown_miku = 20

CONSEJOS = [
    "No cruces terreno abierto sin pensar en la cobertura, recluta.",
    "Mantente cerca de tu escuadron. Separarse facilita que os aislen.",
    "Revisa el mapa y la zona antes de decidir hacia donde moverte.",
    "Si una posicion deja de ser segura, prepara una ruta alternativa.",
    "Comunica donde viste movimiento. Un aviso a tiempo ayuda al equipo.",
    "No persigas a un rival sin comprobar antes que tu equipo pueda apoyarte.",
    "Si tu escuadron necesita reagruparse, prioriza volver con el equipo.",
    "Aprende rutas y puntos de referencia para orientarte mejor en el mapa.",
    "No te quedes demasiado tiempo en una posicion que ya ha sido descubierta.",
    "Coordina las decisiones con tu equipo en vez de actuar cada uno por su lado."
]

RESPUESTAS_HOLA = [
    "¡Soap MacTavish, a tus ordenes! ¿Que necesita el equipo?",
    "Buenas, recluta. ¿Todo listo para otra partida?",
    "Aqui Soap. Espero que hoy el escuadron tenga un plan mejor que improvisar.",
    "¡A la orden! ¿Que ocurre en Villapene?"
]

RESPUESTAS_SOAP = [
    "Soy Soap MacTavish. Moderador, soldado y sufridor oficial de este servidor.",
    "MacTavish presente. Intentad no convertir el chat en una zona de desastre.",
    "¿Necesitas algo, recluta? Procura que no sea otro informe de incompetencia.",
    "Aqui Soap. Si buscas orden, has llegado al servidor equivocado."
]

RESPUESTAS_MIKU = [
    "¿Puerros otra vez, Miku? Empiezo a sospechar que tienes un almacen entero.",
    "Tranquila, cantante. Esto es un servidor, no un concierto militar.",
    "¡Recibido, Miku! Aunque sigo sin entender vuestra obsesion con los puerros.",
    "A la orden, Miku. Pero que conste que esto no estaba en el entrenamiento.",
    "Miku, he visto planes de operaciones menos caoticos que tus conversaciones."
]


# ============================================================
# EVENTOS
# ============================================================

@bot.event
async def on_ready():
    log.info("Soap conectado como %s (%s)", bot.user, bot.user.id)
    await bot.change_presence(
        activity=discord.Game(name="Supervisando Villapene")
    )


@bot.event
async def on_member_join(member):
    """Da la bienvenida si encuentra un canal general apropiado."""
    if member.bot:
        return

    for channel in member.guild.text_channels:
        if channel.name.lower() in ("general", "bienvenida", "chat"):
            if channel.permissions_for(member.guild.me).send_messages:
                try:
                    await channel.send(
                        f"¡Atencion, equipo! {member.mention} acaba de "
                        "incorporarse a Villapene. ¡Bienvenido!"
                    )
                except discord.HTTPException:
                    pass
                return


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Los comandos normales los procesa discord.py.
    # Los mensajes de otros bots no ejecutan comandos.
    if message.author.bot:
        if MIKU_BOT_ID and str(message.author.id) == MIKU_BOT_ID:
            await responder_a_miku(message)
        return

    # Respuestas espontaneas a personas, sin interferir con comandos.
    if not message.content.startswith(PREFIX):
        texto = message.content.lower()

        if bot.user and bot.user.mentioned_in(message):
            await message.channel.send(
                random.choice(RESPUESTAS_SOAP)
            )

        elif "¿quien es soap" in texto or "quien es soap" in texto:
            await message.channel.send(
                "Soap MacTavish, sargento de la Task Force 141. "
                "Y aparentemente tambien moderador de este servidor."
            )

    await bot.process_commands(message)


async def responder_a_miku(message):
    """Responde solo a ciertos mensajes de Miku para evitar bucles."""
    if not message.guild or not message.channel:
        return

    texto = message.content.lower()

    disparadores = (
        "puerro",
        "hola, soap",
        "hola soap",
        "soap,",
        "soap!",
        "cantante",
        "¿quieres puerros?"
    )

    if not any(palabra in texto for palabra in disparadores):
        return

    ahora = asyncio.get_running_loop().time()
    canal_id = message.channel.id
    ultimo = ultimo_mensaje_miku.get(canal_id, 0)

    if ahora - ultimo < cooldown_miku:
        return

    ultimo_mensaje_miku[canal_id] = ahora

    try:
        await message.channel.send(random.choice(RESPUESTAS_MIKU))
    except discord.HTTPException:
        log.warning("No se pudo responder al mensaje de Miku.")


# ============================================================
# AYUDA Y PERSONALIDAD
# ============================================================

@bot.command(name="ayuda", aliases=["comandos", "help"])
async def ayuda(ctx):
    embed = discord.Embed(
        title="Manual de campo de Soap",
        description="Comandos disponibles en Villapene.",
        color=discord.Color.dark_green()
    )

    embed.add_field(
        name="Personalidad",
        value=(
            "`!hola` — Saludar a Soap\n"
            "`!soap` — Escuchar a Soap presentarse\n"
            "`!ayuda` — Mostrar este manual"
        ),
        inline=False
    )

    embed.add_field(
        name="Call of Duty",
        value=(
            "`!consejo` — Consejo aleatorio para Warzone\n"
            "`!warzone` — Informacion y fuente oficial\n"
            "`!cod` — Noticias recientes de CoD\n"
            "`!novedades` — Ultimas noticias disponibles"
        ),
        inline=False
    )

    embed.add_field(
        name="Moderacion",
        value=(
            "`!limpiar 10` — Eliminar mensajes recientes\n"
            "`!kick @usuario razon` — Expulsar un miembro\n"
            "`!ban @usuario razon` — Banear un miembro"
        ),
        inline=False
    )

    embed.set_footer(
        text="Soap MacTavish | Villapene"
    )
    await ctx.send(embed=embed)


@bot.command(name="hola")
async def hola(ctx):
    await ctx.send(random.choice(RESPUESTAS_HOLA))


@bot.command(name="soap")
async def presentacion(ctx):
    await ctx.send(random.choice(RESPUESTAS_SOAP))


# ============================================================
# CONSEJOS DE WARZONE
# ============================================================

@bot.command(name="consejo")
@commands.cooldown(1, 3, commands.BucketType.user)
async def consejo(ctx):
    await ctx.send(
        "🎖️ **Consejo de Soap:**\n"
        + random.choice(CONSEJOS)
    )


@bot.command(name="warzone")
async def warzone(ctx):
    await ctx.send(
        "🎮 **Informe de Warzone**\n"
        "Para consultar noticias, temporadas y cambios recientes, "
        "revisa la pagina oficial:\n"
        "https://www.callofduty.com/blog"
    )


# ============================================================
# NOTICIAS DE CALL OF DUTY
# ============================================================

async def obtener_noticias():
    """
    Intenta leer el RSS de Call of Duty.
    Si no responde o cambia su formato, devuelve una lista vacia.
    """
    timeout = aiohttp.ClientTimeout(total=12)
    headers = {
        "User-Agent": "VillapeneSoapBot/1.0"
    }

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=headers
    ) as session:
        async with session.get(COD_NEWS_FEED) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"El sitio devolvio HTTP {response.status}"
                )

            xml_text = await response.text()
            root = ElementTree.fromstring(xml_text)

    noticias = []

    for item in root.findall(".//item"):
        titulo = item.findtext("title", default="Noticia sin titulo")
        enlace = item.findtext("link", default=COD_BLOG_URL)
        fecha = item.findtext("pubDate", default="")

        titulo = unescape(titulo).strip()
        enlace = enlace.strip()

        if not enlace.startswith("https://"):
            enlace = urljoin(COD_BLOG_URL, enlace)

        fecha_formateada = "Fecha no disponible"

        if fecha:
            try:
                fecha_dt = parsedate_to_datetime(fecha)
                fecha_formateada = fecha_dt.strftime("%d/%m/%Y")
            except (TypeError, ValueError, OverflowError):
                pass

        noticias.append({
            "titulo": titulo[:240],
            "enlace": enlace,
            "fecha": fecha_formateada
        })

        if len(noticias) >= 5:
            break

    return noticias


async def enviar_noticias(ctx):
    await ctx.send("🛰️ **Soap consulta los informes de inteligencia...**")

    try:
        noticias = await obtener_noticias()
    except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError,
            ElementTree.ParseError, ValueError) as error:
        log.warning("No se pudieron obtener noticias: %s", error)
        await ctx.send(
            "No he podido verificar las noticias ahora mismo, recluta. "
            "Consulta el blog oficial: " + COD_BLOG_URL
        )
        return

    if not noticias:
        await ctx.send(
            "No he encontrado noticias en el feed. "
            "Consulta el blog oficial: " + COD_BLOG_URL
        )
        return

    embed = discord.Embed(
        title="📰 Informe de inteligencia: Call of Duty",
        description="Noticias obtenidas del feed consultado.",
        color=discord.Color.dark_green(),
        url=COD_BLOG_URL
    )

    for noticia in noticias:
        embed.add_field(
            name=noticia["titulo"],
            value=(
                f"Fecha: {noticia['fecha']}\n"
                f"[Leer noticia]({noticia['enlace']})"
            ),
            inline=False
        )

    embed.set_footer(
        text="Fuente oficial: Call of Duty | Las fechas pueden variar por region."
    )
    await ctx.send(embed=embed)


@bot.command(name="cod")
@commands.cooldown(1, 15, commands.BucketType.user)
async def cod(ctx):
    await enviar_noticias(ctx)


@bot.command(name="novedades")
@commands.cooldown(1, 15, commands.BucketType.user)
async def novedades(ctx):
    await enviar_noticias(ctx)


# ============================================================
# MODERACION
# ============================================================

def moderacion_autorizada(ctx):
    """Solo el propietario configurado o moderadores del servidor."""
    if OWNER_ID and str(ctx.author.id) == OWNER_ID:
        return True

    permisos = ctx.author.guild_permissions
    return permisos.administrator or permisos.manage_messages


@bot.command(name="limpiar", aliases=["clear", "purge"])
@commands.guild_only()
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def limpiar(ctx, cantidad: int):
    if not moderacion_autorizada(ctx):
        await ctx.send(
            "No tienes autorizacion para ejecutar esa orden, recluta."
        )
        return

    if cantidad < 1 or cantidad > 100:
        await ctx.send("Indica una cantidad entre 1 y 100.")
        return

    try:
        borrados = await ctx.channel.purge(
            limit=cantidad + 1,
            reason=f"Limpieza solicitada por {ctx.author}"
        )
        aviso = await ctx.send(
            f"🧹 He eliminado {max(0, len(borrados) - 1)} mensajes."
        )
        await asyncio.sleep(4)
        await aviso.delete()
    except discord.Forbidden:
        await ctx.send("No tengo permisos para limpiar este canal.")
    except discord.HTTPException:
        await ctx.send("No se pudo completar la limpieza.")


@bot.command(name="kick")
@commands.guild_only()
@commands.bot_has_permissions(kick_members=True)
async def kick(ctx, miembro: discord.Member, *, razon="Sin razon indicada"):
    if not moderacion_autorizada(ctx):
        await ctx.send("Orden denegada, recluta. No tienes permisos.")
        return

    if miembro.id == ctx.author.id or miembro.id == bot.user.id:
        await ctx.send("No puedo ejecutar esa orden contra ese objetivo.")
        return

    if miembro.top_role >= ctx.guild.me.top_role:
        await ctx.send(
            "El rol de esa persona es igual o superior al mio."
        )
        return

    if miembro.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send(
            "No puedes expulsar a alguien con un rol igual o superior al tuyo."
        )
        return

    try:
        await miembro.kick(
            reason=f"{razon} | Moderador: {ctx.author}"
        )
        await ctx.send(
            f"🫡 {miembro} ha sido expulsado. Motivo: {razon}"
        )
    except discord.Forbidden:
        await ctx.send("Discord no me permite expulsar a ese miembro.")
    except discord.HTTPException:
        await ctx.send("No se pudo completar la expulsion.")


@bot.command(name="ban")
@commands.guild_only()
@commands.bot_has_permissions(ban_members=True)
async def ban(ctx, miembro: discord.Member, *, razon="Sin razon indicada"):
    if not moderacion_autorizada(ctx):
        await ctx.send("Orden denegada, recluta. No tienes permisos.")
        return

    if miembro.id == ctx.author.id or miembro.id == bot.user.id:
        await ctx.send("No puedo ejecutar esa orden contra ese objetivo.")
        return

    if miembro.top_role >= ctx.guild.me.top_role:
        await ctx.send(
            "El rol de esa persona es igual o superior al mio."
        )
        return

    if miembro.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send(
            "No puedes banear a alguien con un rol igual o superior al tuyo."
        )
        return

    try:
        await miembro.ban(
            reason=f"{razon} | Moderador: {ctx.author}",
            delete_message_seconds=0
        )
        await ctx.send(
            f"🔨 {miembro} ha sido baneado. Motivo: {razon}"
        )
    except discord.Forbidden:
        await ctx.send("Discord no me permite banear a ese miembro.")
    except discord.HTTPException:
        await ctx.send("No se pudo completar el baneo.")


# ============================================================
# ERRORES Y ARRANQUE
# ============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"Espera {error.retry_after:.1f} segundos antes de repetir la orden."
        )
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "Faltan datos para esa orden. Usa `!ayuda` para ver ejemplos."
        )
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send(
            "No he podido identificar ese usuario o argumento. "
            "Comprueba la mencion y vuelve a intentarlo."
        )
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("No tienes los permisos necesarios.")
        return

    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send("No tengo los permisos necesarios para esa accion.")
        return

    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("Esa orden solo funciona dentro del servidor.")
        return

    log.error("Error de comando: %r", error)
    await ctx.send("Algo salio mal al ejecutar la orden.")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "Falta DISCORD_TOKEN en las variables de entorno."
        )

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    bot.run(TOKEN)
