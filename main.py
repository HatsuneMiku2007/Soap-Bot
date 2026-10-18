import os
import random
import asyncio
import threading
import logging
import time
import xml.etree.ElementTree as ET

from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen

import discord
from discord.ext import commands, tasks

# =========================================================
# CONFIGURACION
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MIKU_BOT_ID = int(os.getenv("MIKU_BOT_ID", "0"))

COD_BLOG_URL = "https://www.callofduty.com/blog"
COD_NEWS_FEED = "https://www.callofduty.com/rss"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Soap141")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Canal donde Soap haya visto actividad humana reciente.
ultimo_canal_activo = {}
ultimo_mensaje_espontaneo = {}
ultimo_mensaje_por_canal = {}

# Evita respuestas excesivas.
cooldown_respuestas = {}
cooldown_miku = {}

# =========================================================
# SERVIDOR HTTP PARA RENDER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Soap MacTavish - Task Force 141 online")

    def log_message(self, format, *args):
        pass


def iniciar_servidor_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


# =========================================================
# PERSONALIDAD DE SOAP
# =========================================================

SALUDOS = [
    "¡Aquí Soap! ¿Qué pasa, equipo?",
    "Task Force 141, presente. ¿Cuál es el plan?",
    "Estoy aquí. Y no, todavía no he volado nada por accidente.",
    "¿Qué pasa, muchachos? ¿Todo tranquilo por aquí?",
    "Soap al habla. Espero que alguno tenga un plan decente.",
    "¡Equipo! ¿Quién está listo para una misión?",
    "Informe de situación: sigo vivo, el café se acabó.",
    "Buenas, soldados. ¿Qué desastre tenemos hoy?",
    "MacTavish conectado. Price todavía no me ha regañado hoy.",
    "¿Qué cuentan? Espero que no estén jugando como reclutas."
]

BROMAS = [
    "Mi plan era sencillo. Luego alguien dijo: «¿Y si explotamos todo?».",
    "Ghost dice que no hago ruido. Eso es porque nunca me ha escuchado intentar cocinar.",
    "Price me dijo que pensara antes de actuar. Llevo años intentando entender esa orden.",
    "Una misión silenciosa conmigo es como una partida sin campers: una leyenda.",
    "Si algo explota, yo no fui. Si explota dos veces, tampoco.",
    "¿Trabajo en equipo? Perfecto. ¿Cargar con todo el equipo yo solo? También parece habitual.",
    "Mi currículum dice experto en improvisación. Price lo llama causar problemas.",
    "No estoy diciendo que mi plan sea perfecto, pero al menos será memorable.",
    "Ghost y yo tenemos un acuerdo: él pone la cara seria y yo hago los comentarios malos.",
    "El problema de ser un buen soldado es que luego todos te piden que arregles sus desastres.",
    "He sobrevivido a demasiadas misiones como para perder una discusión con un bot.",
    "Si me dieran una moneda por cada explosión, podría financiar mi propio helicóptero.",
    "La discreción es importante. Por eso estoy hablando en mayúsculas mentalmente.",
    "No es caos si tienes un plan. Y si no tienes plan, improvisa con confianza.",
    "Necesito vacaciones. Un sitio tranquilo, sin disparos, explosiones ni órdenes de Price."
]

COMENTARIOS = [
    "Eso suena a una misión que terminará con mucho papeleo.",
    "Interesante. Quiero ver cómo termina eso.",
    "Bueno, al menos alguien está pensando por aquí.",
    "No sé si eso es brillante o una pésima idea. Probablemente ambas.",
    "Tomo nota, soldado.",
    "Me gusta la confianza. Ahora necesitamos un plan.",
    "He visto operaciones empezar con menos preparación y terminar bastante peor.",
    "No voy a juzgar. Bueno, quizá un poco.",
    "Eso merece una reunión de la 141. Y probablemente café.",
    "Yo digo que sigamos adelante, pero que nadie toque los explosivos.",
    "Eso ha sido inesperado. Incluso para mis estándares.",
    "Tenemos una situación. No necesariamente una emergencia, todavía.",
    "No está mal. Ghost pondría cara de desaprobación, pero yo lo apruebo.",
    "Me quedo con esa idea. Puede servir en el campo.",
    "Necesito más información antes de declarar esto una catástrofe."
]

OPINIONES_141 = [
    "Price es el líder que quieres tener cuando todo sale mal. Aunque sus discursos podrían durar menos.",
    "Ghost es increíblemente competente. También podría intentar sonreír una vez en su vida.",
    "Gaz es de los que mantienen al equipo funcionando mientras los demás hacemos tonterías.",
    "Ghost y yo hacemos un buen equipo. Él intimida; yo hablo demasiado. Equilibrio perfecto.",
    "Price tiene experiencia, cabeza fría y una habilidad extraordinaria para mandarnos a situaciones complicadas.",
    "Gaz suele ser más sensato de lo que le reconocemos. Alguien tiene que serlo.",
    "La 141 funciona porque cada uno aporta algo distinto. No cambiaría eso por nada.",
    "Ghost es el tipo de compañero que quieres cubriéndote la espalda. Aunque te asuste cuando aparece detrás de ti.",
    "Price inspira confianza. También inspira la sensación de que te va a asignar otra misión.",
    "Gaz es fiable. En nuestro trabajo, eso vale muchísimo.",
    "No hay un integrante inútil en la 141. Aunque algunos ponemos a prueba la paciencia del capitán."
]

GUSTOS = [
    "Me gusta el trabajo en equipo, las misiones bien ejecutadas y que el plan sobreviva más de cinco minutos.",
    "Prefiero una operación con buenos compañeros a una con equipamiento caro y nadie que te cubra.",
    "Tengo debilidad por el humor en los peores momentos. Si no puedes bromear, la tensión te come.",
    "Me gustan las armas fiables. No necesito que mi equipo tenga luces de colores para hacer su trabajo.",
    "Mi actividad favorita es volver de una misión con todos los compañeros a salvo.",
    "¿Comida favorita? Después de una operación larga, casi cualquier cosa sabe como un banquete.",
    "Me gusta la música que te mantiene despierto durante una guardia. Price probablemente preferiría silencio.",
    "Prefiero los planes claros, aunque rara vez tengamos la suerte de seguirlos.",
    "Mi mayor gusto es tener cinco minutos de tranquilidad. En la 141, eso cuenta como vacaciones.",
    "Me gusta competir, pero ganar gracias al equipo siempre es mejor que presumir en solitario."
]

ARMAS = [
    "Si hablamos de Warzone, no existe un arma perfecta para todo. Importan la temporada, la distancia y cómo juegues.",
    "Para elegir un arma, fíjate en el retroceso, el tiempo para apuntar y el alcance efectivo. Las estadísticas importan.",
    "Una escopeta puede ser peligrosa a corta distancia, pero no soluciona todos los enfrentamientos.",
    "No copies una clase sin probarla. Una configuración popular puede no encajar con tu estilo.",
    "La mejor arma es la que controlas bien y que sirve para el combate que estás buscando.",
    "Lleva un arma para tus enfrentamientos principales y piensa cómo vas a cubrir tus distancias débiles.",
    "Practicar el retroceso te ayudará más que cambiar de accesorio cada dos minutos."
]

CONSEJOS_WARZONE = [
    "Consejo: mira el círculo antes de lootear. El mejor botín no sirve de nada si la zona te obliga a cruzar campo abierto.",
    "Consejo: no revivas a un compañero por impulso si el equipo enemigo sigue apuntando al mismo lugar. Busca cobertura.",
    "Consejo: comunica la posición enemiga y la dirección. Decir «está ahí» no ayuda mucho si nadie sabe dónde es ahí.",
    "Consejo: evita correr por zonas abiertas sin necesidad. Usa cobertura y planifica tu siguiente movimiento.",
    "Consejo: no dispares a todo lo que se mueve si eso revela tu posición y no puedes terminar el enfrentamiento.",
    "Consejo: aprende cuándo retirarte. Sobrevivir para reagruparte también es jugar bien.",
    "Consejo: vigila el dinero del equipo y acuerden qué comprar. La coordinación suele valer más que comprar al azar.",
    "Consejo: no te quedes mirando el mapa demasiado tiempo en un lugar expuesto. Comprueba la zona y muévete.",
    "Consejo: si te eliminan siempre en el mismo tipo de situación, revisa qué información te faltaba antes del combate.",
    "Consejo: escucha el audio del juego y ajusta la mezcla para distinguir pasos, disparos y señales importantes.",
    "Consejo: recarga en cobertura, no en mitad de un pasillo porque te entró la ansiedad.",
    "Consejo: si tu compañero inicia un combate, comunícate con él antes de entrar por otra dirección sin avisar.",
    "Consejo: usa el terreno a tu favor. La altura y la cobertura pueden decidir un combate.",
    "Consejo: revisa tu equipamiento entre partidas y cambia lo que realmente te esté perjudicando.",
    "Consejo: no persigas a un enemigo sin pensar. Puede estar llevándote hacia sus compañeros.",
    "Consejo: marca objetivos y comparte recursos. Un equipo organizado tiene más opciones que cuatro jugadores aislados.",
    "Consejo: si estás perdiendo muchos duelos, prueba a reducir la exposición y mejorar la colocación antes de culpar al arma.",
    "Consejo: presta atención al tiempo de rotación. Llegar antes a una buena posición puede evitar peleas innecesarias.",
    "Consejo: no hace falta ganar todos los enfrentamientos. A veces la mejor decisión es reposicionarse.",
    "Consejo: juega unas partidas centrándote en una sola habilidad, como el movimiento, la puntería o la lectura del círculo."
]

DATOS_COD = [
    "Dato CoD: la franquicia alterna entre distintos estudios, como Infinity Ward, Treyarch y Sledgehammer Games.",
    "Dato CoD: la saga incluye campañas, multijugador y modos cooperativos, según el título.",
    "Dato CoD: Call of Duty 4: Modern Warfare ayudó a consolidar la fórmula moderna de la franquicia.",
    "Dato CoD: Zombies se convirtió en una de las señas de identidad de varios juegos desarrollados por Treyarch.",
    "Dato CoD: Task Force 141 es una unidad ficticia central en la historia de Modern Warfare.",
    "Dato CoD: Soap MacTavish y Simon «Ghost» Riley son personajes diferentes; no confundas sus historias entre continuidades.",
    "Dato CoD: las versiones originales de Modern Warfare y las reinterpretaciones modernas no comparten todos los acontecimientos.",
    "Dato CoD: Warzone ha cambiado mapas, armas y mecánicas a lo largo de sus diferentes etapas.",
    "Dato CoD: los mapas multijugador pequeños suelen favorecer enfrentamientos rápidos, mientras que los grandes permiten otros ritmos.",
    "Dato CoD: las estadísticas de un arma no cuentan toda la historia; también importan el mapa, la distancia y el estilo del jugador.",
    "Dato CoD: algunos personajes y acontecimientos cambian entre la continuidad original y la reiniciada de Modern Warfare.",
    "Dato CoD: las misiones de campaña pueden combinar objetivos de combate, infiltración, defensa y sigilo.",
    "Dato CoD: las rachas de bajas y las rachas de puntos no son exactamente el mismo sistema.",
    "Dato CoD: el diseño de sonido puede ayudarte a reconocer recargas, disparos y movimientos cercanos.",
    "Dato CoD: no todas las armas que aparecen en campaña están disponibles de la misma forma en cada modo."
]

PREGUNTAS_SOAP = [
    "Pregunta táctica: ¿cuál es tu Call of Duty favorito y por qué?",
    "A ver, soldado: ¿prefieres jugar agresivo o controlar la zona con paciencia?",
    "Necesito una respuesta seria: ¿Ghost, Price o Gaz? ¿Quién es tu favorito?",
    "¿Qué mapa de Call of Duty te sabes de memoria?",
    "Pregunta importante: ¿campaña, multijugador, Zombies o Warzone?",
    "¿Cuál ha sido tu mejor partida de Warzone? Quiero escuchar ese informe.",
    "Si pudieras elegir una misión de la saga para jugar de nuevo por primera vez, ¿cuál sería?",
    "¿Qué arma de CoD te gusta más, sin contar las que están rotas en el meta?",
    "¿Qué villano de Call of Duty te parece más memorable?",
    "¿Eres de los que aterrizan en el lugar más concurrido o de los que prefieren preparar la partida?",
    "¿Qué juego de Modern Warfare te gusta más: la trilogía original o la moderna?",
    "¿Qué modo de juego debería regresar en una próxima entrega?",
    "Pregunta de la 141: ¿prefieres a un líder experimentado como Price o a un compañero impredecible como yo?",
    "¿Qué misión de campaña te dejó más impresionado?",
    "¿Qué mapa borrarías de la historia de CoD y cuál recuperarías?"
]

def normalizar(texto):
    return texto.lower().strip()


def elegir(lista):
    return random.choice(lista)


# =========================================================
# RESPUESTAS A PREGUNTAS SOBRE SOAP
# =========================================================

RESPUESTAS_GUSTOS = {
    "favorito": [
        "Difícil elección. Price tiene mi respeto, Ghost es un compañero excelente y Gaz es muy fiable. La 141 funciona como equipo.",
        "Si me obligas a escoger, diría que Price por su liderazgo. Pero no le cuentes que he dicho algo amable.",
        "No voy a elegir a uno para dejar mal a los demás. Cada uno tiene su lugar en la 141."
    ],
    "arma": [
        "Depende de la misión, soldado. Quiero un arma fiable, que pueda controlar y adecuada a la distancia del combate.",
        "No tengo una única respuesta para todas las situaciones. Un buen operador adapta su equipamiento al objetivo.",
        "La herramienta importa, pero saber cuándo usarla importa más."
    ],
    "juego": [
        "Tengo debilidad por Modern Warfare. Hay recuerdos de misiones que no se olvidan fácilmente.",
        "La saga tiene varias etapas interesantes. ¿La trilogía original o la moderna? Esa sí que es una discusión larga.",
        "No todos los juegos brillan en lo mismo. Algunos destacan por su campaña y otros por sus modos multijugador."
    ],
    "ghost": [
        "Ghost es un compañero de confianza. Aunque sospecho que practica esa mirada seria frente al espejo.",
        "Es un buen soldado. No esperes que te lo diga delante de él.",
        "Ghost y yo tenemos estilos distintos. Por eso funcionamos tan bien juntos."
    ],
    "price": [
        "El capitán Price sabe dirigir una operación. También sabe encontrar trabajo extra para todos.",
        "Price tiene mi respeto. Si te da una orden, normalmente hay una razón detrás.",
        "Es un gran líder. Pero si pregunta quién rompió algo, yo no he visto nada."
    ],
    "gaz": [
        "Gaz es fiable y sabe mantener la cabeza fría. Eso vale mucho en una operación.",
        "Gaz aporta equilibrio al equipo. No se lo digas demasiado alto o se acostumbrará a los elogios.",
        "Un compañero sólido. Siempre quieres a alguien así cubriéndote la espalda."
    ],
    "comida": [
        "Después de una misión larga, algo caliente y abundante. No soy precisamente exigente en ese momento.",
        "Cualquier comida sabe mejor cuando has terminado el trabajo y todos han vuelto.",
        "Lo que haya disponible, siempre que no tenga sabor a ración de emergencia."
    ],
    "musica": [
        "Algo que me mantenga despierto durante una guardia larga. Price probablemente me quitaría los auriculares.",
        "Depende del día. A veces necesitas energía y otras veces solo un poco de calma.",
        "No pienso revelar mi lista de reproducción a toda la 141. Tengo una reputación que mantener."
    ]
}


def responder_gustos(texto):
    t = normalizar(texto)

    if any(p in t for p in ["ghost", "fantasma"]):
        return elegir(RESPUESTAS_GUSTOS["ghost"])

    if "price" in t or "capitan" in t or "capitán" in t:
        return elegir(RESPUESTAS_GUSTOS["price"])

    if "gaz" in t:
        return elegir(RESPUESTAS_GUSTOS["gaz"])

    if any(p in t for p in ["arma favorita", "arma preferida", "arma te gusta"]):
        return elegir(RESPUESTAS_GUSTOS["arma"])

    if any(p in t for p in ["call of duty favorito", "cod favorito", "juego favorito", "juego prefieres"]):
        return elegir(RESPUESTAS_GUSTOS["juego"])

    if any(p in t for p in ["comida favorita", "qué comes", "que comes"]):
        return elegir(RESPUESTAS_GUSTOS["comida"])

    if any(p in t for p in ["música", "musica", "canción", "cancion"]):
        return elegir(RESPUESTAS_GUSTOS["musica"])

    if any(p in t for p in ["integrante favorito", "miembro favorito", "mejor integrante", "mejor miembro", "quien es tu favorito", "quién es tu favorito"]):
        return elegir(RESPUESTAS_GUSTOS["favorito"])

    if any(p in t for p in ["qué te gusta", "que te gusta", "tus gustos", "qué opinas de", "que opinas de"]):
        return elegir(GUSTOS)

    return None


# =========================================================
# COMANDOS GENERALES
# =========================================================

@bot.event
async def on_ready():
    logger.info("Soap conectado como %s", bot.user)
    if not charla_espontanea.is_running():
        charla_espontanea.start()


@bot.command(name="ayuda")
async def ayuda(ctx):
    embed = discord.Embed(
        title="🫡 Manual de campo de Soap",
        description="Comandos disponibles para la Task Force 141.",
        color=discord.Color.dark_green()
    )
    embed.add_field(
        name="Conversación",
        value=(
            "`!soap` — Habla conmigo\n"
            "`!gustos` — Mis preferencias y opiniones\n"
            "`!pregunta` — Pregunta aleatoria para el equipo\n"
            "`!141` — Mi opinión sobre el equipo\n"
            "`!broma` — Humor militar de calidad cuestionable"
        ),
        inline=False
    )
    embed.add_field(
        name="Call of Duty",
        value=(
            "`!consejo` — Consejo aleatorio de Warzone\n"
            "`!consejos` — Más consejos\n"
            "`!dato` — Curiosidad de CoD\n"
            "`!arma` — Consejo sobre armas\n"
            "`!cod` — Enlace a las novedades oficiales\n"
            "`!novedades` — Últimas noticias disponibles\n"
            "`!kesto` — Recomendación de contenido de Kesto"
        ),
        inline=False
    )
    embed.add_field(
        name="Servidor",
        value=(
            "`!hola` — Saludo\n"
            "`!limpiar 10` — Borra mensajes (moderadores)\n"
            "`!kick @usuario motivo` — Expulsa (moderadores)\n"
            "`!ban @usuario motivo` — Banea (moderadores)"
        ),
        inline=False
    )
    embed.set_footer(text="Task Force 141 | Mantengan la cabeza fría.")
    await ctx.send(embed=embed)


@bot.command(name="hola")
async def hola(ctx):
    await ctx.send(elegir(SALUDOS))


@bot.command(name="soap")
async def soap(ctx):
    await ctx.send(elegir(BROMAS + COMENTARIOS + GUSTOS))


@bot.command(name="broma")
async def broma(ctx):
    await ctx.send(elegir(BROMAS))


@bot.command(name="gustos")
async def gustos(ctx):
    await ctx.send(elegir(GUSTOS))


@bot.command(name="pregunta")
async def pregunta(ctx):
    await ctx.send(elegir(PREGUNTAS_SOAP))


@bot.command(name="141")
async def opinion_141(ctx):
    await ctx.send(elegir(OPINIONES_141))


@bot.command(name="consejo")
async def consejo(ctx):
    await ctx.send(elegir(CONSEJOS_WARZONE))


@bot.command(name="consejos")
async def consejos(ctx):
    seleccion = random.sample(CONSEJOS_WARZONE, k=3)
    await ctx.send("🫡 **Tres consejos de Soap:**\n\n" + "\n\n".join(
        f"• {c}" for c in seleccion
    ))


@bot.command(name="dato")
async def dato(ctx):
    await ctx.send(elegir(DATOS_COD))


@bot.command(name="arma")
async def arma(ctx):
    await ctx.send(elegir(ARMAS))


@bot.command(name="cod")
async def cod(ctx):
    await ctx.send(
        "📰 Informe de inteligencia: consulta las novedades oficiales de Call of Duty.\n"
        + COD_BLOG_URL
    )


@bot.command(name="warzone")
async def warzone(ctx):
    await ctx.send(
        "🎯 Soldado, revisa la información oficial de Warzone aquí:\n"
        "https://www.callofduty.com/warzone"
    )


# =========================================================
# RECOMENDACIONES DE KESTO
# =========================================================

KESTO_URL = "https://www.youtube.com/results?search_query=Kesto+Warzone"

VIDEOS_KESTO = [
    "Te recomiendo buscar los análisis de armas y clases de Warzone de Kesto. Comprueba la fecha del vídeo: el meta cambia.",
    "Misión de hoy: busca a Kesto probando clases de Warzone. No copies una configuración sin probarla tú mismo.",
    "Si quieres ideas para tus equipamientos, revisa los vídeos de Kesto sobre armas y configuraciones. El parche actual importa.",
    "¿Buscas consejos para mejorar en Warzone? Puedes explorar el contenido de Kesto y comparar sus recomendaciones con tu estilo.",
    "Recomendación de Soap: un vídeo de Kesto sobre movimiento o posicionamiento puede darte ideas útiles para practicar.",
    "Busca los vídeos recientes de Kesto sobre Warzone para evitar guías de armas que ya hayan cambiado."
]


@bot.command(name="kesto")
async def kesto(ctx):
    await ctx.send(
        "🎥 **Recomendación de Soap:** " + elegir(VIDEOS_KESTO)
        + "\n🔎 " + KESTO_URL
    )


# =========================================================
# NOTICIAS DE CALL OF DUTY
# =========================================================

def obtener_noticias():
    try:
        request = Request(
            COD_NEWS_FEED,
            headers={"User-Agent": "Mozilla/5.0 Soap141Bot/1.0"}
        )
        with urlopen(request, timeout=8) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        noticias = []

        for item in root.findall(".//item")[:5]:
            titulo = item.findtext("title", default="Noticia de Call of Duty")
            link = item.findtext("link", default=COD_BLOG_URL)
            fecha = item.findtext("pubDate", default="")

            titulo = unescape(titulo).strip()
            link = unescape(link).strip()

            if titulo and link:
                noticias.append((titulo, link, fecha))

        return noticias

    except Exception as error:
        logger.warning("No se pudieron leer las noticias: %s", error)
        return []


@bot.command(name="novedades")
@commands.cooldown(1, 20, commands.BucketType.channel)
async def novedades(ctx):
    await ctx.send("🛰️ Recibiendo información del cuartel general...")

    noticias = await asyncio.to_thread(obtener_noticias)

    if not noticias:
        await ctx.send(
            "No he podido recuperar un listado de noticias ahora mismo, soldado. "
            "Consulta el blog oficial: " + COD_BLOG_URL
        )
        return

    embed = discord.Embed(
        title="📰 Informe de inteligencia: Call of Duty",
        description="Estas son las entradas que pude recuperar del feed disponible.",
        color=discord.Color.dark_green(),
        url=COD_BLOG_URL
    )

    for titulo, link, fecha in noticias[:5]:
        fecha_texto = ""
        if fecha:
            try:
                fecha_texto = parsedate_to_datetime(fecha).strftime("%d/%m/%Y")
            except Exception:
                fecha_texto = fecha

        valor = f"[Leer noticia]({link})"
        if fecha_texto:
            valor += f"\nPublicado: {fecha_texto}"

        embed.add_field(name=titulo[:250], value=valor, inline=False)

    embed.set_footer(text="Verifica la fecha y el título en la página oficial.")
    await ctx.send(embed=embed)


@novedades.error
async def novedades_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send("Calma, soldado. Ya estoy buscando información. Inténtalo en unos segundos.")
    else:
        raise error


# =========================================================
# MODERACION
# =========================================================

def es_moderador(ctx):
    return (
        ctx.author.id == OWNER_ID
        or ctx.author.guild_permissions.manage_messages
        or ctx.author.guild_permissions.administrator
    )


@bot.command(name="limpiar")
@commands.bot_has_permissions(manage_messages=True, read_message_history=True)
async def limpiar(ctx, cantidad: int = 5):
    if not es_moderador(ctx):
        await ctx.send("No tienes autorización para esa operación, soldado.")
        return

    if cantidad < 1 or cantidad > 100:
        await ctx.send("Indica una cantidad entre 1 y 100.")
        return

    borrados = await ctx.channel.purge(limit=cantidad + 1)
    aviso = await ctx.send(f"🧹 Limpieza completada. Mensajes eliminados: {len(borrados) - 1}.")
    await asyncio.sleep(4)
    try:
        await aviso.delete()
    except discord.HTTPException:
        pass


@bot.command(name="kick")
@commands.bot_has_permissions(kick_members=True)
async def kick(ctx, miembro: discord.Member, *, motivo="Sin motivo indicado"):
    if not es_moderador(ctx):
        await ctx.send("No tienes autorización para esa operación, soldado.")
        return

    if miembro == ctx.author or miembro == bot.user:
        await ctx.send("No puedes usar ese comando con ese objetivo.")
        return

    if ctx.guild.owner_id != ctx.author.id and miembro.top_role >= ctx.author.top_role:
        await ctx.send("No puedo expulsar a alguien con un rango igual o superior al tuyo.")
        return

    if miembro.top_role >= ctx.guild.me.top_role:
        await ctx.send("Mi rango es demasiado bajo para expulsar a ese miembro.")
        return

    await miembro.kick(reason=f"{ctx.author}: {motivo}")
    await ctx.send(f"🫡 {miembro} ha sido expulsado. Motivo: {motivo}")


@bot.command(name="ban")
@commands.bot_has_permissions(ban_members=True)
async def ban(ctx, miembro: discord.Member, *, motivo="Sin motivo indicado"):
    if not es_moderador(ctx):
        await ctx.send("No tienes autorización para esa operación, soldado.")
        return

    if miembro == ctx.author or miembro == bot.user:
        await ctx.send("No puedes usar ese comando con ese objetivo.")
        return

    if ctx.guild.owner_id != ctx.author.id and miembro.top_role >= ctx.author.top_role:
        await ctx.send("No puedes banear a alguien con un rango igual o superior al tuyo.")
        return

    if miembro.top_role >= ctx.guild.me.top_role:
        await ctx.send("Mi rango es demasiado bajo para banear a ese miembro.")
        return

    await miembro.ban(reason=f"{ctx.author}: {motivo}")
    await ctx.send(f"🔨 {miembro} ha sido baneado. Motivo: {motivo}")


# =========================================================
# BIENVENIDAS
# =========================================================

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    for canal in member.guild.text_channels:
        if canal.name.lower() in ("general", "bienvenida", "chat"):
            await canal.send(
                f"🫡 ¡Bienvenido, {member.mention}! Soap MacTavish, Task Force 141. "
                "Lee las reglas y ponte cómodo, soldado."
            )
            break


# =========================================================
# CONVERSACION ESPONTANEA
# =========================================================

def elegir_respuesta_espontanea():
    grupos = [
        (SALUDOS, 1),
        (BROMAS, 3),
        (COMENTARIOS, 3),
        (OPINIONES_141, 2),
        (GUSTOS, 2),
        (PREGUNTAS_SOAP, 3),
        (DATOS_COD, 2),
        (CONSEJOS_WARZONE, 3)
    ]

    lista = []
    for respuestas, peso in grupos:
        lista.extend(respuestas * peso)

    return elegir(lista)


@tasks.loop(minutes=15)
async def charla_espontanea():
    # Solo considera canales donde hubo actividad humana reciente.
    ahora = time.time()

    candidatos = [
        canal_id for canal_id, ultima in ultimo_canal_activo.items()
        if ahora - ultima < 60 * 60
        and ahora - ultimo_mensaje_espontaneo.get(canal_id, 0) > 45 * 60
    ]

    if not candidatos:
        return

    # No habla en todos los ciclos: mantiene la conversación natural.
    if random.random() > 0.35:
        return

    canal_id = elegir(candidatos)
    canal = bot.get_channel(canal_id)

    if canal is None:
        return

    try:
        await canal.send(elegir_respuesta_espontanea())
        ultimo_mensaje_espontaneo[canal_id] = ahora
    except (discord.Forbidden, discord.HTTPException):
        logger.warning("No pude enviar un mensaje espontáneo en el canal %s", canal_id)


@charla_espontanea.before_loop
async def antes_de_charla():
    await bot.wait_until_ready()


# =========================================================
# RESPUESTAS A MENSAJES Y A MIKU
# =========================================================

FRASES_MIKU = [
    "Miku, necesito un informe. Y no, cantar no cuenta como informe.",
    "Miku, ¿tus puerros tienen alguna aplicación táctica o solo son decoración?",
    "No sé cómo lo haces, Miku, pero consigues que hasta el cuartel parezca un karaoke.",
    "Miku, si vas a cantar durante una operación, al menos avisa antes de empezar.",
    "He trabajado con muchos compañeros, pero ninguno me había hablado tanto de puerros.",
    "Miku, el capitán Price quiere saber quién convirtió el canal en un concierto.",
    "Admito que tienes talento, Miku. Pero todavía no te dejo a cargo de los explosivos.",
    "Miku, ¿alguna vez respondes sin mencionar música? Pregunto por motivos científicos.",
    "Creo que Ghost preferiría enfrentarse a un escuadrón entero antes que cantar contigo.",
    "Está bien, Miku. Tú pones la música y yo reviso las salidas de emergencia."
]


def es_mensaje_para_soap(texto):
    t = normalizar(texto)

    activadores = [
        "soap", "mactavish", "sargento", "soldado",
        "task force", "141", "warzone", "call of duty"
    ]

    return any(p in t for p in activadores)


def detectar_tema(texto):
    t = normalizar(texto)

    if any(p in t for p in ["hola", "buenas", "buenos dias", "buenas noches", "qué tal", "que tal"]):
        return elegir(SALUDOS)

    if any(p in t for p in ["jajaja", "xd", "lol", "que risa", "qué risa"]):
        return elegir(BROMAS)

    if any(p in t for p in ["consejo", "como mejorar", "cómo mejorar", "warzone"]):
        return elegir(CONSEJOS_WARZONE)

    if any(p in t for p in ["dato", "curiosidad", "sabias que", "sabías que"]):
        return elegir(DATOS_COD)

    if any(p in t for p in ["ghost", "price", "gaz", "141"]):
        return elegir(OPINIONES_141)

    if any(p in t for p in ["aburrido", "aburrida", "no hay nada que hacer"]):
        return elegir(PREGUNTAS_SOAP)

    return None


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.guild is None:
        await bot.process_commands(message)
        return

    # Solo registra actividad humana para la charla espontánea.
    if not message.author.bot:
        ultimo_canal_activo[message.channel.id] = time.time()
        ultimo_mensaje_por_canal[message.channel.id] = time.time()

    # No procesa comandos ni conversa con otros bots salvo Miku.
    if message.author.bot:
        if MIKU_BOT_ID and message.author.id == MIKU_BOT_ID:
            ahora = time.time()
            ultimo = cooldown_miku.get(message.channel.id, 0)

            if ahora - ultimo > 25 and random.random() < 0.40:
                await message.channel.send(elegir(FRASES_MIKU))
                cooldown_miku[message.channel.id] = ahora

        return

    # Procesa comandos antes de respuestas automáticas.
    await bot.process_commands(message)

    if message.author.id == OWNER_ID:
        pass

    texto = normalizar(message.content)
    ahora = time.time()
    ultimo = cooldown_respuestas.get(message.channel.id, 0)

    # Soap no debe responder a cada mensaje.
    if ahora - ultimo < 12:
        return

    # Preguntas sobre sus gustos, incluso si no mencionan su nombre.
    respuesta_gusto = responder_gustos(texto)
    if respuesta_gusto and (
        "soap" in texto
        or "mactavish" in texto
        or "tu " in texto
        or "te gusta" in texto
        or "favorito" in texto
        or "prefieres" in texto
        or "opinas" in texto
    ):
        if random.random() < 0.85:
            await message.channel.send(respuesta_gusto)
            cooldown_respuestas[message.channel.id] = ahora
            return

    # Responde si lo llaman directamente.
    if bot.user in message.mentions or es_mensaje_para_soap(texto):
        respuesta = detectar_tema(texto)

        if respuesta is None:
            respuesta = elegir(COMENTARIOS + BROMAS + GUSTOS)

        await message.channel.send(respuesta)
        cooldown_respuestas[message.channel.id] = ahora
        return

    # Conversación espontánea basada en mensajes humanos.
    # La probabilidad baja evita que interrumpa demasiado.
    if len(texto) > 5 and random.random() < 0.035:
        await message.channel.send(elegir(COMENTARIOS + BROMAS))
        cooldown_respuestas[message.channel.id] = ahora


# =========================================================
# ERRORES DE COMANDOS
# =========================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Falta información, soldado. Usa `!ayuda` para ver cómo funciona el comando.")
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send("No he podido reconocer ese usuario o argumento. Revisa cómo escribiste el comando.")
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("No tienes permisos para esa operación.")
        return

    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send("Me faltan permisos para cumplir esa orden. Revisa mis permisos y mi posición en los roles.")
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send("Espera un poco, soldado. Estoy procesando la petición.")
        return

    logger.error("Error en comando: %s", error)
    await ctx.send("Algo salió mal. Inténtalo de nuevo más tarde.")


# =========================================================
# ARRANQUE
# =========================================================

if not TOKEN:
    raise RuntimeError("Falta la variable DISCORD_TOKEN en Render.")

threading.Thread(target=iniciar_servidor_web, daemon=True).start()
bot.run(TOKEN)
