"""🎄 App de entrega de cestas natalinas.

Publicado como um segundo app no Streamlit Cloud (arquivo principal:
natal_app.py). Usa o mesmo Supabase, os mesmos usuários e o mesmo
cadastro de crachás do app de cestas básicas, com tabelas próprias.
"""

import json
import textwrap
import time
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from natal import servicos as natal
from services.autenticacao import autenticar


st.set_page_config(
    page_title="Cestas Natalinas",
    page_icon="🎄",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# AJUDANTES
# ============================================================

def html(conteudo):
    conteudo = textwrap.dedent(str(conteudo)).strip()
    if hasattr(st, "html"):
        st.html(conteudo)
    else:
        st.markdown(" ".join(l.strip() for l in conteudo.splitlines()), unsafe_allow_html=True)


def seguro(valor):
    return escape(natal.texto(valor))


def primeiro_nome(nome):
    partes = natal.texto(nome).split()
    return partes[0].title() if partes else ""


# ============================================================
# ESTADO
# ============================================================

for chave, valor in {
    "logado": False,
    "usuario": None,
    "nome_usuario": None,
    "perfil": None,
    "pagina": "Terminal",
    "resultado": None,
    "ultima_leitura": "",
    "ultimo_tempo": 0.0,
    "id_leitura": 0,
}.items():
    st.session_state.setdefault(chave, valor)


# ============================================================
# VISUAL DE NATAL
# ============================================================

VERDE = "#0E4D35"
VERDE_ESCURO = "#08331F"
VERMELHO = "#B3202A"
VERMELHO_ESCURO = "#7E1219"
DOURADO = "#E8B547"
CREME = "#FFF8EC"
TEXTO = "#1F1A17"
TEXTO_SUAVE = "#5B4E45"

flocos = "".join(
    f'<span class="floco" style="left:{(i * 37) % 100}%;'
    f'animation-duration:{7 + (i * 3) % 9}s;animation-delay:-{(i * 1.7) % 9:.1f}s;'
    f'font-size:{10 + (i * 5) % 14}px;">{"❄" if i % 3 else "❅"}</span>'
    for i in range(28)
)

html(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Mountains+of+Christmas:wght@700&family=Nunito:wght@500;700;800;900&display=swap');

    html, body, .stApp, [data-testid="stAppViewContainer"] {{
        background:
            radial-gradient(circle at 12% 0%, rgba(179,32,42,.10), transparent 35%),
            radial-gradient(circle at 90% 10%, rgba(14,77,53,.12), transparent 40%),
            {CREME} !important;
        color: {TEXTO} !important;
        font-family: 'Nunito', sans-serif !important;
    }}
    header[data-testid="stHeader"] {{ background: transparent !important; }}
    div[data-testid="stDecoration"] {{ display: none !important; }}
    .block-container {{ max-width: 1150px; padding-top: 1.2rem; }}
    h1, h2, h3 {{ color: {VERDE_ESCURO} !important; font-weight: 900 !important; }}

    /* Neve */
    .neve {{ position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden; }}
    .floco {{
        position: absolute; top: -30px; color: #EAF4FB;
        text-shadow: 0 0 4px rgba(70,110,150,.8);
        animation-name: cair; animation-timing-function: linear; animation-iteration-count: infinite;
        opacity: .9;
    }}
    @keyframes cair {{
        0% {{ transform: translateY(-30px) translateX(0) rotate(0deg); }}
        50% {{ transform: translateY(50vh) translateX(18px) rotate(180deg); }}
        100% {{ transform: translateY(105vh) translateX(-12px) rotate(360deg); }}
    }}

    /* Faixa do topo */
    .faixa {{
        position: relative; overflow: hidden;
        background: linear-gradient(120deg, {VERMELHO_ESCURO}, {VERMELHO} 45%, {VERDE} 100%);
        border-radius: 22px; padding: 22px 28px 26px; margin-bottom: 18px;
        box-shadow: 0 10px 28px rgba(126,18,25,.28);
        border: 2px solid {DOURADO};
    }}
    .faixa h1 {{
        font-family: 'Mountains of Christmas', cursive !important;
        color: #FFFFFF !important; font-size: 48px !important; margin: 0 !important;
        text-shadow: 0 3px 0 rgba(0,0,0,.25); line-height: 1.1;
    }}
    .faixa .sub {{ color: #FFEFD0; font-size: 17px; font-weight: 800; margin-top: 4px; }}
    .luzes {{ display: flex; gap: 22px; position: absolute; top: 6px; left: 20px; right: 20px; }}
    .luz {{
        width: 11px; height: 15px; border-radius: 50% 50% 45% 45%;
        animation: piscar 1.6s ease-in-out infinite;
    }}
    .luz:nth-child(4n+1) {{ background: #FFD54F; animation-delay: 0s; }}
    .luz:nth-child(4n+2) {{ background: #66BB6A; animation-delay: .4s; }}
    .luz:nth-child(4n+3) {{ background: #FF5252; animation-delay: .8s; }}
    .luz:nth-child(4n+4) {{ background: #4FC3F7; animation-delay: 1.2s; }}
    @keyframes piscar {{ 0%,100% {{ opacity: 1; box-shadow: 0 0 10px currentColor; }} 50% {{ opacity: .35; }} }}

    /* Barra lateral */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {VERDE_ESCURO}, {VERDE}) !important;
        border-right: 3px solid {DOURADO};
    }}
    section[data-testid="stSidebar"] * {{ color: #FFF8EC !important; }}
    section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] * {{ color: #F3E6CC !important; }}
    section[data-testid="stSidebar"] .stButton button,
    section[data-testid="stSidebar"] .stButton button * {{ color: #FFF8EC !important; }}
    section[data-testid="stSidebar"] .stButton button {{
        justify-content: flex-start !important; text-align: left !important;
        background: rgba(255,255,255,.06) !important; border: 1px solid rgba(255,255,255,.18) !important;
        border-radius: 12px !important; min-height: 44px; font-weight: 800 !important; font-size: 15px !important;
    }}
    section[data-testid="stSidebar"] .stButton button:hover {{
        background: rgba(232,181,71,.20) !important; border-color: {DOURADO} !important;
    }}
    section[data-testid="stSidebar"] .stButton button[kind="primary"],
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {{
        background: {VERMELHO} !important; border: 2px solid {DOURADO} !important;
    }}
    section[data-testid="stSidebar"] .stButton button > div,
    section[data-testid="stSidebar"] .stButton button p {{ justify-content: flex-start !important; width: 100%; }}
    section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.2) !important; }}

    /* Campos e botões da área principal */
    div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input {{
        background: #FFFFFF !important; color: {TEXTO} !important;
        border: 2px solid #B9A88F !important; border-radius: 10px !important;
    }}
    input[aria-label="Leitura"] {{
        border: 2.5px solid {VERDE} !important; border-radius: 16px !important;
        font-size: 26px !important; font-weight: 900 !important; text-align: center !important;
        min-height: 66px !important;
    }}
    div[data-testid="stTextInput"] input:focus {{ border-color: {VERMELHO} !important; box-shadow: 0 0 0 4px rgba(179,32,42,.15) !important; }}
    input::placeholder {{ color: #7A6B60 !important; opacity: 1 !important; }}
    button[kind="primary"], button[kind="primaryFormSubmit"],
    button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {{
        background: {VERMELHO} !important; border: 2px solid {VERMELHO_ESCURO} !important; color: #FFFFFF !important;
        font-weight: 800 !important; border-radius: 12px !important;
    }}
    button[kind="primary"] *, button[data-testid="stBaseButton-primary"] *,
    button[kind="primaryFormSubmit"] *, button[data-testid="stBaseButton-primaryFormSubmit"] * {{ color: #FFFFFF !important; }}
    button[kind="secondary"], button[data-testid="stBaseButton-secondary"], div[data-testid="stDownloadButton"] button {{
        background: #FFFFFF !important; color: {VERDE_ESCURO} !important;
        border: 2px solid {VERDE} !important; border-radius: 12px !important; font-weight: 800 !important;
    }}
    div[data-testid="stMetric"] {{
        background: #FFFFFF; border: 2px solid #E9D8BC; border-top: 6px solid {VERDE};
        border-radius: 16px; padding: 12px 16px; box-shadow: 0 4px 14px rgba(31,26,23,.06);
    }}
    div[data-testid="stMetricLabel"] * {{ color: {TEXTO_SUAVE} !important; font-weight: 800 !important; }}
    div[data-testid="stMetricValue"] * {{ color: {VERDE_ESCURO} !important; font-weight: 900 !important; }}
    div[data-testid="stCaptionContainer"] * {{ color: {TEXTO_SUAVE} !important; }}
    div[data-testid="stAlert"] {{ border-radius: 12px !important; }}
    div[data-testid="stProgress"] > div > div > div > div {{ background: linear-gradient(90deg, {VERMELHO}, {DOURADO}, {VERDE}) !important; }}

    /* Cartões de resultado */
    .resultado {{
        border-radius: 24px; padding: 26px 24px; text-align: center; margin: 14px 0 10px;
        border: 3px solid; box-shadow: 0 10px 26px rgba(0,0,0,.10); position: relative; overflow: hidden;
        animation: surgir .35s ease-out;
    }}
    @keyframes surgir {{ from {{ transform: scale(.96); opacity: 0; }} to {{ transform: scale(1); opacity: 1; }} }}
    .resultado .titulo {{ font-size: 40px; font-weight: 900; letter-spacing: .5px; line-height: 1.15; }}
    .resultado .nome {{ font-size: 30px; font-weight: 900; margin-top: 12px; }}
    .resultado .dados {{ font-size: 17px; font-weight: 700; margin-top: 6px; }}
    .resultado .mensagem {{ font-family: 'Mountains of Christmas', cursive; font-size: 34px; margin-top: 10px; }}
    .r-entregue {{ background: linear-gradient(135deg, #E8F7EE, #FFFFFF); border-color: #1B7A45; color: #0B4A28; }}
    .r-ja {{ background: linear-gradient(135deg, #FFF3D6, #FFFFFF); border-color: #C98A00; color: #6B4300; }}
    .r-erro {{ background: linear-gradient(135deg, #FDE8E8, #FFFFFF); border-color: {VERMELHO}; color: #7E1219; }}
    .r-cinza {{ background: #F1EEE9; border-color: #8A7B70; color: #3D342E; }}
    .presentes {{ position: absolute; inset: 0; pointer-events: none; }}
    .presentes span {{ position: absolute; bottom: -30px; font-size: 26px; animation: subir 2.4s ease-out forwards; }}
    @keyframes subir {{ to {{ transform: translateY(-260px) rotate(25deg); opacity: 0; }} }}

    .pronto {{
        background: #FFFFFF; border: 2px dashed {VERDE}; color: {VERDE_ESCURO};
        border-radius: 14px; padding: 10px; text-align: center; font-weight: 900; margin-top: 8px;
    }}
    .leitura-linha {{
        display: flex; justify-content: space-between; gap: 10px; background: #FFFFFF;
        border: 1px solid #E9D8BC; border-left: 6px solid; border-radius: 10px; padding: 8px 12px; margin-bottom: 6px;
        font-size: 14px; font-weight: 700;
    }}
    .rodape {{ text-align: center; color: {TEXTO_SUAVE}; font-size: 13px; margin-top: 30px; font-weight: 700; }}
    div[data-testid="stElementContainer"]:has(> iframe[height="0"]) {{ height: 0 !important; margin: 0 !important; overflow: hidden; }}
    </style>
    <div class="neve">{flocos}</div>
    """
)


def faixa(titulo, subtitulo=""):
    luzes = "".join('<span class="luz"></span>' for _ in range(40))
    html(
        f"""
        <div class="faixa">
            <div class="luzes">{luzes}</div>
            <h1>{titulo}</h1>
            <div class="sub">{subtitulo}</div>
        </div>
        """
    )


def tocar_som(tipo, marcador):
    """Som curto gerado no navegador (sem arquivos de áudio e sem player na tela)."""
    melodias = {
        # Início de "Jingle Bells" (domínio público)
        "ENTREGUE": [(659, .18), (659, .18), (659, .36), (659, .18), (659, .18), (659, .36),
                     (659, .18), (784, .18), (523, .27), (587, .09), (659, .5)],
        "JA_RETIROU": [(523, .2), (440, .35)],
        "ERRO": [(330, .25), (247, .45)],
    }
    notas = melodias.get(tipo, melodias["ERRO"])
    components.html(
        f"""
        <script>
        // {escape(str(marcador))}
        (function () {{
            try {{
                const J = window.parent;
                const Ctx = J.AudioContext || J.webkitAudioContext;
                if (!Ctx) return;
                J.__natalAudio = J.__natalAudio || new Ctx();
                const ctx = J.__natalAudio;
                if (ctx.state === "suspended") ctx.resume();
                let t = ctx.currentTime + 0.05;
                {json.dumps([list(n) for n in notas])}.forEach(function (n) {{
                    const osc = ctx.createOscillator();
                    const ganho = ctx.createGain();
                    osc.type = "triangle";
                    osc.frequency.value = n[0];
                    ganho.gain.setValueAtTime(0.0001, t);
                    ganho.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
                    ganho.gain.exponentialRampToValueAtTime(0.0001, t + n[1]);
                    osc.connect(ganho); ganho.connect(ctx.destination);
                    osc.start(t); osc.stop(t + n[1] + 0.02);
                    t += n[1] + 0.03;
                }});
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def focar_leitura(marcador):
    components.html(
        f"""
        <script>
        // {escape(str(marcador))}
        (function () {{
            try {{
                const doc = window.parent.document;
                const focar = () => {{
                    const campo = doc.querySelector('input[aria-label="Leitura"]');
                    const ativo = doc.activeElement;
                    const digitando = ativo && (["TEXTAREA", "SELECT"].includes(ativo.tagName)
                        || (ativo.tagName === "INPUT" && !["radio", "checkbox", "button"].includes(ativo.type)));
                    if (campo && !campo.disabled && !digitando) campo.focus();
                }};
                setTimeout(focar, 150); setTimeout(focar, 700);
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
    )


# ============================================================
# LOGIN
# ============================================================

def tela_login():
    faixa("Cestas Natalinas 🎄", "Entre com o mesmo usuário do app de cestas básicas")
    _, centro, _ = st.columns([1, 1.3, 1])
    with centro:
        with st.form("login"):
            usuario = st.text_input("Usuário", key="login_usuario")
            senha = st.text_input("Senha", type="password", key="login_senha")
            entrar = st.form_submit_button("🎅 Entrar", type="primary", use_container_width=True)
        if entrar:
            try:
                registro = autenticar(usuario, senha)
            except Exception as erro:
                st.error(f"Não foi possível conectar: {erro}")
                return
            if not registro:
                st.error("Usuário ou senha inválidos.")
                return
            st.session_state.logado = True
            st.session_state.usuario = registro["usuario"]
            st.session_state.nome_usuario = registro.get("nome") or registro["usuario"]
            st.session_state.perfil = registro.get("perfil")
            st.rerun()


if not st.session_state.logado:
    tela_login()
    st.stop()

eh_admin = st.session_state.perfil == "ADMIN"


# ============================================================
# MENU
# ============================================================

def ir_para(pagina):
    st.session_state.pagina = pagina


def sair():
    for chave in ("logado", "usuario", "nome_usuario", "perfil", "resultado"):
        st.session_state[chave] = None
    st.session_state.logado = False
    st.session_state.pagina = "Terminal"


PAGINAS = [("Terminal", "🎄"), ("Acompanhamento", "📊")]
if eh_admin:
    PAGINAS += [("Lista", "📋"), ("Relatório", "📑"), ("Campanha", "⚙️")]

if st.session_state.pagina not in [p for p, _ in PAGINAS]:
    st.session_state.pagina = "Terminal"

try:
    campanha = natal.campanha_ativa()
except Exception as erro:
    st.error(
        "Não consegui acessar as tabelas do Natal. Rode o arquivo "
        f"sql/003_natal.sql no SQL Editor do Supabase. Detalhe: {erro}"
    )
    st.stop()

with st.sidebar:
    html('<div style="font-size:30px;font-weight:900;">🎄 Cestas Natalinas</div>')
    st.caption(f"🎅 {st.session_state.nome_usuario} • {'Administrador' if eh_admin else 'Operador'}")
    if campanha:
        status = "🟢 ABERTA" if campanha.get("status") == "ABERTA" else "🔴 FINALIZADA"
        st.caption(f"🎁 {campanha.get('nome')} • {status}")
    else:
        st.caption("🎁 Nenhuma campanha ativa")
    st.divider()
    for pagina, icone in PAGINAS:
        st.button(
            f"{icone}  {pagina}",
            key=f"menu_{pagina}",
            type="primary" if st.session_state.pagina == pagina else "secondary",
            use_container_width=True,
            on_click=ir_para,
            args=(pagina,),
        )
    st.divider()
    st.button("🚪 Sair", key="menu_sair", use_container_width=True, on_click=sair)


def exigir_campanha():
    if campanha:
        return True
    faixa("Cestas Natalinas 🎄", "Nenhuma campanha ativa")
    if eh_admin:
        st.info("Crie a campanha (ex.: Natal 2026) na página ⚙️ Campanha e depois importe a lista.")
    else:
        st.info("Nenhuma campanha ativa. Peça ao administrador para criar a campanha de Natal.")
    return False


# ============================================================
# TERMINAL
# ============================================================

def processar_leitura():
    valor = natal.texto(st.session_state.get("Leitura"))
    st.session_state["Leitura"] = ""
    if not valor:
        return

    agora = time.time()
    if valor == st.session_state.ultima_leitura and agora - st.session_state.ultimo_tempo < 2:
        return  # leitura duplicada do leitor
    st.session_state.ultima_leitura = valor
    st.session_state.ultimo_tempo = agora

    try:
        resultado = natal.processar_leitura(valor, natal.campanha_ativa(), st.session_state.usuario)
    except Exception as erro:
        resultado = {"resultado": "ERRO", "motivo": f"Erro ao registrar: {erro}", "valor_lido": valor}
    st.session_state.resultado = resultado
    st.session_state.id_leitura += 1


def tela_terminal():
    if not exigir_campanha():
        return

    faixa("Feliz Natal! 🎅", f"{seguro(campanha.get('nome'))} • aproxime o crachá ou digite a matrícula")
    aberta = campanha.get("status") == "ABERTA"

    st.text_input(
        "Leitura",
        key="Leitura",
        placeholder="🎁 Aproxime o crachá ou digite a matrícula..." if aberta else "Campanha finalizada",
        on_change=processar_leitura,
        label_visibility="collapsed",
        disabled=not aberta,
    )
    focar_leitura(f"{st.session_state.id_leitura}-{st.session_state.pagina}")

    if aberta:
        html('<div class="pronto">✨ Pronto para a próxima leitura ✨</div>')
    else:
        st.warning("Campanha finalizada. Para voltar a entregar, reabra em ⚙️ Campanha.")

    resultado = st.session_state.resultado
    if resultado:
        mostrar_resultado(resultado)

    try:
        ind = natal.indicadores(campanha)
        c1, c2, c3 = st.columns(3)
        c1.metric("🎁 Entregues", f"{ind['entregues']} de {ind['total']}")
        c2.metric("⏳ Faltam retirar", ind["pendentes"])
        if ind["estoque_restante"] is not None:
            c3.metric("📦 Cestas no estoque", ind["estoque_restante"])
        else:
            c3.metric("📈 Progresso", f"{ind['percentual']:.0f}%")
        st.progress(min(ind["percentual"] / 100, 1.0))
    except Exception:
        pass

    leituras_recentes()


def mostrar_resultado(r):
    tipo = r.get("resultado")
    nome = seguro(r.get("nome"))
    dados = []
    if r.get("matricula"):
        dados.append(f"🆔 Matrícula: <strong>{seguro(r.get('matricula'))}</strong>")
    if r.get("setor"):
        dados.append(f"🏢 {seguro(r.get('setor'))}")
    if r.get("forma"):
        dados.append(f"🪪 {seguro(r.get('forma'))}")
    linha_dados = " &nbsp;•&nbsp; ".join(dados)

    if tipo == "ENTREGUE":
        presentes = "".join(
            f'<span style="left:{(i * 13) % 95}%;animation-delay:{(i % 5) * .15:.2f}s;">'
            f'{"🎁🎄⭐🔔❄"[i % 5]}</span>'
            for i in range(14)
        )
        html(
            f"""
            <div class="resultado r-entregue">
                <div class="presentes">{presentes}</div>
                <div class="titulo">🎁 ENTREGAR CESTA NATALINA</div>
                <div class="nome">{nome or 'Colaborador'}</div>
                <div class="dados">{linha_dados}</div>
                <div class="mensagem">Feliz Natal, {seguro(primeiro_nome(r.get('nome'))) or 'colaborador'}! 🎄</div>
            </div>
            """
        )
        som = "ENTREGUE"
    elif tipo == "JA_RETIROU":
        html(
            f"""
            <div class="resultado r-ja">
                <div class="titulo">🔔 JÁ RETIROU A CESTA</div>
                <div class="nome">{nome}</div>
                <div class="dados">{linha_dados}</div>
                <div class="dados">Retirada em <strong>{seguro(r.get('data_hora')) or '-'}</strong>
                {f"por {seguro(r.get('retirado_por'))}" if r.get('retirado_por') else ""}</div>
            </div>
            """
        )
        som = "JA_RETIROU"
    else:
        titulos = {
            "NAO_ESTA_NA_LISTA": "🚫 NÃO ESTÁ NA LISTA",
            "SEM_ESTOQUE": "📦 ESTOQUE ESGOTADO",
            "FINALIZADA": "⛔ CAMPANHA FINALIZADA",
        }
        classe = "r-cinza" if tipo == "FINALIZADA" else "r-erro"
        complemento = (
            f"Valor lido: <strong>{seguro(r.get('valor_lido'))}</strong>"
            if tipo == "NAO_ESTA_NA_LISTA" and not nome else seguro(r.get("motivo"))
        )
        html(
            f"""
            <div class="resultado {classe}">
                <div class="titulo">{titulos.get(tipo, '⚠️ ERRO')}</div>
                {f'<div class="nome">{nome}</div>' if nome else ''}
                <div class="dados">{linha_dados}</div>
                <div class="dados">{complemento}</div>
            </div>
            """
        )
        som = "ERRO"

    tocar_som(som, st.session_state.id_leitura)


def leituras_recentes():
    try:
        registros = natal.historico(campanha["id"], limite=6)
    except Exception:
        return
    if not registros:
        return
    cores = {"ENTREGUE": "#1B7A45", "JA_RETIROU": "#C98A00"}
    rotulos = {
        "ENTREGUE": "🎁 Entregue", "JA_RETIROU": "🔔 Já retirou", "NAO_ESTA_NA_LISTA": "🚫 Fora da lista",
        "SEM_ESTOQUE": "📦 Sem estoque", "FINALIZADA": "⛔ Finalizada",
    }
    st.markdown("#### 🕯️ Últimas leituras")
    linhas = "".join(
        f'<div class="leitura-linha" style="border-left-color:{cores.get(r.get("resultado"), "#B3202A")}">'
        f'<span>{seguro(natal.data_hora_local(r.get("data_hora"))[11:])} &nbsp; '
        f'<strong>{seguro(r.get("nome") or r.get("valor_lido"))}</strong></span>'
        f'<span>{rotulos.get(r.get("resultado"), seguro(r.get("resultado")))}</span></div>'
        for r in registros
    )
    html(linhas)


# ============================================================
# ACOMPANHAMENTO
# ============================================================

def tela_acompanhamento():
    if not exigir_campanha():
        return
    faixa("Acompanhamento 📊", seguro(campanha.get("nome")))

    ind = natal.indicadores(campanha)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Na lista", ind["total"])
    c2.metric("🎁 Entregues", ind["entregues"])
    c3.metric("⏳ Faltam", ind["pendentes"])
    c4.metric("📈 Progresso", f"{ind['percentual']:.1f}%")
    st.progress(min(ind["percentual"] / 100, 1.0))
    if ind["estoque"] is not None:
        st.caption(f"📦 Estoque: {ind['estoque']} cestas • restam {ind['estoque_restante']}")

    lista = natal.listar_lista(campanha["id"])
    if not lista:
        st.info("A lista ainda está vazia.")
        return

    st.markdown("#### 🔎 Consultar colaborador")
    f1, f2 = st.columns([2, 1])
    busca = f1.text_input("Buscar", placeholder="Nome, matrícula ou setor...", key="acomp_busca")
    situacao = f2.selectbox("Situação", ["Todos", "Entregues", "Faltam retirar"], key="acomp_sit")

    df = pd.DataFrame(
        [
            {
                "Matrícula": natal.texto(r.get("matricula")),
                "Nome": natal.texto(r.get("nome")),
                "Setor": natal.texto(r.get("setor")),
                "Situação": "🎁 ENTREGUE" if r.get("retirado") else "⏳ FALTA RETIRAR",
                "Retirada em": natal.data_hora_local(r.get("data_hora_retirada")),
                "Por": natal.texto(r.get("retirado_por")),
            }
            for r in lista
        ]
    )
    if busca:
        termo = busca.strip()
        df = df[
            df[["Matrícula", "Nome", "Setor"]].apply(
                lambda c: c.str.contains(termo, case=False, na=False, regex=False)
            ).any(axis=1)
        ]
    if situacao == "Entregues":
        df = df[df["Situação"].str.contains("ENTREGUE")]
    elif situacao == "Faltam retirar":
        df = df[df["Situação"].str.contains("FALTA")]

    st.caption(f"{len(df)} pessoa(s).")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("#### 🏢 Por setor")
    st.dataframe(
        pd.DataFrame(ind["por_setor"], columns=["Setor", "Total", "Entregues", "Pendentes"]),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# LISTA (IMPORTAÇÃO)
# ============================================================

def ler_planilha(arquivo):
    nome = arquivo.name.lower()
    if nome.endswith(".csv"):
        df = pd.read_csv(arquivo, dtype=str, sep=None, engine="python", encoding_errors="replace")
    else:
        df = pd.read_excel(arquivo, dtype=str)
    df = df.dropna(how="all")
    colunas = [str(c).strip() for c in df.columns]
    df.columns = colunas
    return df.to_dict(orient="records"), colunas


def tela_lista():
    if not exigir_campanha():
        return
    faixa("Lista de quem tem direito 📋", f"{seguro(campanha.get('nome'))} • 1 cesta natalina por pessoa")

    st.markdown("#### 📥 Importar planilha")
    st.caption(
        "Excel (.xlsx) ou CSV com uma linha por pessoa. Colunas aceitas: "
        "**Matrícula** (obrigatória), **Nome** e **Setor**. Todos da lista têm direito a 1 cesta. "
        "Pode importar de novo: quem já retirou continua como retirado."
    )
    arquivo = st.file_uploader("Planilha", type=["xlsx", "xls", "csv"], key="natal_arquivo")

    if arquivo is not None:
        try:
            linhas, colunas = ler_planilha(arquivo)
        except Exception as erro:
            st.error(f"Não consegui ler a planilha: {erro}")
            return

        itens, erros, avisos = natal.preparar_lista(linhas, colunas)
        for erro in erros:
            st.error(erro)
        if erros:
            return

        mapa = natal.mapear_colunas(colunas)
        st.success(
            f"✅ {len(itens)} pessoa(s) encontradas. Colunas usadas: "
            + ", ".join(f"{campo.title()} = \"{coluna}\"" for campo, coluna in mapa.items())
        )
        with st.expander(f"⚠️ {len(avisos)} aviso(s)", expanded=False) if avisos else st.container():
            for aviso in avisos[:200]:
                st.write(aviso)
        st.dataframe(pd.DataFrame(itens[:20]), use_container_width=True, hide_index=True)
        st.caption("Prévia das primeiras 20 linhas.")

        if st.button("🎄 Confirmar importação", type="primary", use_container_width=True):
            with st.spinner("Importando..."):
                itens = natal.completar_com_cadastro(itens)
                resumo = natal.importar_lista(campanha["id"], itens)
            st.success(
                f"🎁 Importação concluída: {resumo['novos']} nova(s) pessoa(s) e "
                f"{resumo['atualizados']} atualizada(s)."
            )
            st.balloons()

    st.divider()
    st.markdown("#### ➕ Adicionar uma pessoa")
    with st.form("form_adicionar", clear_on_submit=True):
        a1, a2, a3 = st.columns([1, 2, 1.5])
        matricula = a1.text_input("Matrícula *")
        nome = a2.text_input("Nome (opcional se já estiver no cadastro)")
        setor = a3.text_input("Setor")
        if st.form_submit_button("Adicionar à lista", type="primary"):
            try:
                natal.adicionar_pessoa(campanha["id"], matricula, nome, setor)
                st.success("Pessoa adicionada.")
            except Exception as erro:
                st.error(str(erro))

    with st.expander("🗑️ Recomeçar a lista"):
        st.caption("Remove quem ainda NÃO retirou, para importar uma lista nova. Quem já retirou é mantido.")
        confirmar = st.checkbox("Confirmo que quero remover os pendentes da lista.", key="conf_limpar")
        if st.button("Remover pendentes", disabled=not confirmar):
            natal.limpar_lista_sem_retirada(campanha["id"])
            st.success("Pendentes removidos.")


# ============================================================
# RELATÓRIO
# ============================================================

def tela_relatorio():
    campanhas = natal.listar_campanhas()
    if not campanhas:
        exigir_campanha()
        return
    faixa("Relatório 📑", "Entregas e leituras da campanha")

    mapa = {c["id"]: c for c in campanhas}
    escolhida = st.selectbox(
        "Campanha",
        list(mapa.keys()),
        format_func=lambda i: f"{mapa[i]['nome']} — {mapa[i]['status']}{' (ativa)' if mapa[i]['ativa'] else ''}",
        key="rel_campanha",
    )
    camp = mapa[escolhida]
    ind = natal.indicadores(camp)
    c1, c2, c3 = st.columns(3)
    c1.metric("👥 Na lista", ind["total"])
    c2.metric("🎁 Entregues", ind["entregues"])
    c3.metric("⏳ Não retiraram", ind["pendentes"])

    lista = natal.listar_lista(escolhida)
    df = pd.DataFrame(
        [
            {
                "Matrícula": natal.texto(r.get("matricula")),
                "Nome": natal.texto(r.get("nome")),
                "Setor": natal.texto(r.get("setor")),
                "Situação": "ENTREGUE" if r.get("retirado") else "NÃO RETIROU",
                "Data/Hora da retirada": natal.data_hora_local(r.get("data_hora_retirada")),
                "Forma": natal.texto(r.get("forma_retirada")),
                "Usuário": natal.texto(r.get("retirado_por")),
            }
            for r in lista
        ],
        columns=["Matrícula", "Nome", "Setor", "Situação", "Data/Hora da retirada", "Forma", "Usuário"],
    )

    aba1, aba2 = st.tabs(["🎁 Lista com situação", "🕯️ Todas as leituras"])
    with aba1:
        filtro = st.selectbox("Mostrar", ["Todos", "Entregues", "Não retiraram"], key="rel_filtro")
        exibir = df
        if filtro == "Entregues":
            exibir = df[df["Situação"] == "ENTREGUE"]
        elif filtro == "Não retiraram":
            exibir = df[df["Situação"] == "NÃO RETIROU"]
        st.caption(f"{len(exibir)} linha(s).")
        st.dataframe(exibir, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Exportar lista (CSV)",
            exibir.to_csv(index=False, encoding="utf-8-sig"),
            file_name=f"natal_{camp['nome'].replace(' ', '_')}_{filtro.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with aba2:
        hist = natal.historico(escolhida, limite=100000)
        df_hist = pd.DataFrame(
            [
                {
                    "Data/Hora": natal.data_hora_local(h.get("data_hora")),
                    "Lido": natal.texto(h.get("valor_lido")),
                    "Forma": natal.texto(h.get("tipo_identificacao")),
                    "Matrícula": natal.texto(h.get("matricula")),
                    "Nome": natal.texto(h.get("nome")),
                    "Setor": natal.texto(h.get("setor")),
                    "Resultado": natal.texto(h.get("resultado")),
                    "Usuário": natal.texto(h.get("usuario")),
                }
                for h in hist
            ]
        )
        st.caption(f"{len(df_hist)} leitura(s), incluindo repetidas e fora da lista.")
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        if not df_hist.empty:
            st.download_button(
                "⬇️ Exportar leituras (CSV)",
                df_hist.to_csv(index=False, encoding="utf-8-sig"),
                file_name=f"natal_leituras_{camp['nome'].replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ============================================================
# CAMPANHA
# ============================================================

def tela_campanha():
    faixa("Campanha de Natal ⚙️", "Crie, finalize ou reabra a campanha")

    if campanha:
        st.markdown(f"#### 🎁 Campanha ativa: **{seguro(campanha['nome'])}** — {campanha['status']}")
        c1, c2 = st.columns(2)
        with c1:
            if campanha["status"] == "ABERTA":
                confirmar = st.checkbox("Confirmo que a entrega terminou.", key="conf_finalizar")
                if st.button("⛔ Finalizar campanha", disabled=not confirmar, use_container_width=True):
                    natal.finalizar_campanha(campanha["id"], st.session_state.usuario)
                    st.rerun()
            else:
                if st.button("🔓 Reabrir campanha", use_container_width=True):
                    natal.reabrir_campanha(campanha["id"])
                    st.rerun()
        with c2:
            with st.form("form_estoque"):
                controlar = st.checkbox(
                    "Controlar estoque", value=campanha.get("estoque_inicial") is not None
                )
                estoque = st.number_input(
                    "Quantidade de cestas natalinas recebidas",
                    min_value=0, step=1, value=int(campanha.get("estoque_inicial") or 0),
                )
                if st.form_submit_button("💾 Salvar estoque"):
                    natal.definir_estoque(campanha["id"], int(estoque) if controlar else None)
                    st.success("Estoque salvo.")
                    st.rerun()
    else:
        st.info("Nenhuma campanha ativa ainda.")

    st.divider()
    st.markdown("#### ✨ Nova campanha")
    st.caption("A campanha atual deixa de ser a ativa (os dados dela continuam no Relatório).")
    with st.form("form_nova", clear_on_submit=True):
        n1, n2 = st.columns([2, 1])
        nome = n1.text_input("Nome", placeholder="Natal 2026")
        estoque_novo = n2.number_input("Estoque (0 = sem controle)", min_value=0, step=1, value=0)
        if st.form_submit_button("🎄 Criar campanha", type="primary"):
            try:
                natal.criar_campanha(nome, int(estoque_novo) or None, st.session_state.usuario)
                st.success("Campanha criada! Agora importe a lista em 📋 Lista.")
                st.rerun()
            except Exception as erro:
                st.error(str(erro))

    anteriores = [c for c in natal.listar_campanhas() if not c.get("ativa")]
    if anteriores:
        st.divider()
        st.markdown("#### 📚 Campanhas anteriores")
        mapa = {c["id"]: c for c in anteriores}
        escolha = st.selectbox(
            "Tornar ativa novamente", list(mapa.keys()),
            format_func=lambda i: f"{mapa[i]['nome']} — {mapa[i]['status']}", key="camp_ativar",
        )
        if st.button("Ativar esta campanha"):
            natal.ativar_campanha(escolha)
            st.rerun()


# ============================================================
# ROTEAMENTO
# ============================================================

telas = {
    "Terminal": tela_terminal,
    "Acompanhamento": tela_acompanhamento,
    "Lista": tela_lista,
    "Relatório": tela_relatorio,
    "Campanha": tela_campanha,
}
telas.get(st.session_state.pagina, tela_terminal)()

html('<div class="rodape">🎄 Boas festas! • Sistema de Cestas Natalinas 🎁</div>')
