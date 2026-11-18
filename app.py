import time
import textwrap
import base64
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from database.database import (
    inicializar_banco,
    obter_estoque,
    configurar_estoque,
    liberar_cesta,
    registrar_tentativa_nao_encontrada,
    obter_historico,
    obter_historico_geral,
    obter_historico_legado,
    obter_indicadores,
    obter_periodo_ativo,
    listar_periodos,
    obter_colaboradores_periodo,
    obter_consulta_retiradas,
    obter_resumo_consulta,
    finalizar_entrega,
    reabrir_entrega,
    iniciar_nova_entrega,
    registrar_historico,
    perdeu_todas,
    perda_parcial,
)
from services.importador import importar_excel
from services.identificacao import (
    identificar,
    cadastrar_cracha,
    buscar_por_matricula,
    completar_cracha_pelo_cadastro,
)
from services import cadastro
from services.audio_manager import (
    TIPOS_AUDIO,
    obter_audio_evento,
    listar_configuracoes_audio,
    salvar_audio_personalizado,
    definir_audio_ativo,
    restaurar_audio_padrao,
    verificar_setup_audio,
)
from services.supabase_client import service_role_configurada
from services.autenticacao import (
    inicializar_usuarios,
    autenticar,
    listar_usuarios,
    criar_usuario,
    alterar_status_usuario,
    alterar_senha_usuario,
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Sistema de Cestas Básicas",
    page_icon="🥫",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# UTILITÁRIOS VISUAIS
# ============================================================

def valor_seguro(valor):
    if valor is None:
        return ""
    return escape(str(valor))


def render_html(conteudo):
    conteudo = textwrap.dedent(str(conteudo)).strip()
    if hasattr(st, "html"):
        st.html(conteudo)
    else:
        conteudo = " ".join(linha.strip() for linha in conteudo.splitlines())
        st.markdown(conteudo, unsafe_allow_html=True)


def texto_campo(valor):
    """Normaliza campos do banco/Excel sem transformar vazio em 'nan'."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.lower() in {"", "nan", "none", "null", "nat"}:
        return ""
    return texto


# ============================================================
# ÁUDIOS DO TERMINAL
# ============================================================


def tipo_audio_resultado(resultado):
    """Traduz o resultado da operação para o evento de áudio configurável."""
    if not resultado:
        return None

    if resultado.get("sucesso"):
        try:
            normal = int(resultado.get("cesta_normal") or 0)
        except (TypeError, ValueError):
            normal = 0

        try:
            especial = int(resultado.get("cesta_especial") or 0)
        except (TypeError, ValueError):
            especial = 0

        if normal > 0 and especial > 0:
            return "cesta_normal_especial"
        if normal > 0:
            return "cesta_normal"
        if especial > 0:
            return "cesta_especial"
        return None

    status = texto_campo(resultado.get("resultado")).upper()
    mapa = {
        "NEGADO": "negado",
        "DUPLICADO": "duplicado",
        "SEM_ESTOQUE": "sem_estoque",
        "NAO_ENCONTRADO": "nao_encontrado",
        "DEMITIDO": "demitido",
        "ERRO_CRACHA": "erro_cracha",
    }
    return mapa.get(status)


def tocar_audio_resultado(resultado):
    """Toca uma única vez o áudio configurado para a operação atual."""
    tipo = tipo_audio_resultado(resultado)
    if not tipo:
        return

    audio = obter_audio_evento(tipo)
    if not audio.get("ativo") or not audio.get("dados"):
        return

    identificador = "|".join(
        [
            tipo,
            texto_campo(resultado.get("matricula")),
            texto_campo(resultado.get("resultado")),
            str(st.session_state.get("ultimo_timestamp", "")),
        ]
    )

    if st.session_state.get("ultimo_audio_operacao") == identificador:
        return

    st.audio(
        audio["dados"],
        format=audio.get("mime_type") or "audio/mpeg",
        autoplay=True,
    )

    st.session_state.ultimo_audio_operacao = identificador
    st.session_state.ultima_frase_audio = TIPOS_AUDIO[tipo]["titulo"]


def render_preview_audio(dados, mime_type="audio/mpeg"):
    """Player visível para a tela administrativa, sem sofrer o CSS do st.audio."""
    if not dados:
        st.info("Nenhum áudio disponível para prévia.")
        return

    conteudo = base64.b64encode(bytes(dados)).decode("ascii")
    mime = valor_seguro(mime_type or "audio/mpeg")
    render_html(
        f"""
        <div style="padding:8px 0 4px 0;">
            <audio controls preload="metadata" style="width:100%; height:42px;">
                <source src="data:{mime};base64,{conteudo}" type="{mime}">
                Seu navegador não suporta reprodução de áudio.
            </audio>
        </div>
        """
    )


# ============================================================
# BANCO
# ============================================================

@st.cache_resource(show_spinner=False)
def inicializar_uma_vez():
    """Antes rodava a cada clique/leitura (várias consultas ao Supabase).
    Agora roda uma vez por inicialização do servidor. Se falhar, tenta de
    novo na próxima interação (o Streamlit não guarda exceções no cache)."""
    inicializar_banco()
    inicializar_usuarios()
    return True


inicializar_uma_vez()


# ============================================================
# SESSION STATE
# ============================================================

valores_iniciais = {
    "logado": False,
    "usuario_id": None,
    "usuario": None,
    "nome_usuario": None,
    "perfil": None,
    "identificacao": "",
    "resultado_liberacao": None,
    "ultima_leitura": "",
    "ultimo_timestamp": 0.0,
    "limpar_entrada": False,
    "tema": "Claro",
    "pagina": "Terminal",
    "consulta_matricula": "",
    "resultado_consulta": None,
    "aguardando_cracha": False,
    "colaborador_cracha_id": None,
    "matricula_cracha": None,
    # "CADASTRO" = primeira vez (cadastra e libera a cesta)
    # "ATUALIZAR" = troca de crachá pelo botão (não libera cesta)
    "modo_cracha": None,
    "dados_cracha": None,
    "ultimo_audio_operacao": None,
    "ultima_frase_audio": "",
}

for chave, valor in valores_iniciais.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


# ============================================================
# LOGIN
# ============================================================

def sair():
    st.session_state.logado = False
    st.session_state.usuario_id = None
    st.session_state.usuario = None
    st.session_state.nome_usuario = None
    st.session_state.perfil = None
    st.session_state.pagina = "Terminal"
    st.session_state.identificacao = ""
    st.session_state.resultado_liberacao = None
    st.session_state.resultado_consulta = None
    limpar_modo_cracha()


def tela_login():
    render_html(
        """
        <style>
        .login-container {
            max-width: 460px;
            margin: 45px auto 15px auto;
            text-align: center;
        }
        .login-icon { font-size: 56px; line-height: 1; margin-bottom: 8px; }
        .login-title { font-size: 34px; font-weight: 900; margin-bottom: 5px; }
        .login-subtitle { font-size: 15px; color: #98A2B3; margin-bottom: 18px; }
        </style>
        <div class="login-container">
            <div class="login-icon">🥫</div>
            <div class="login-title">Cestas Básicas</div>
            <div class="login-subtitle">Sistema de controle de distribuição</div>
        </div>
        """
    )

    _, centro, _ = st.columns([1, 1.5, 1])
    with centro:
        with st.form("form_login"):
            usuario = st.text_input("Usuário", placeholder="Digite o usuário")
            senha = st.text_input("Senha", type="password", placeholder="Digite a senha")
            entrar = st.form_submit_button(
                "🔐 Entrar", type="primary", use_container_width=True
            )

            if entrar:
                registro = autenticar(usuario, senha)
                if registro is None:
                    st.error("Usuário ou senha inválidos.")
                else:
                    st.session_state.logado = True
                    st.session_state.usuario_id = registro["id"]
                    st.session_state.usuario = registro["usuario"]
                    st.session_state.nome_usuario = registro["nome"]
                    st.session_state.perfil = registro["perfil"]
                    st.session_state.pagina = "Terminal"
                    st.rerun()


if not st.session_state.logado:
    tela_login()
    st.stop()


eh_admin = st.session_state.perfil == "ADMIN"


# ============================================================
# PERÍODOS
# ============================================================

def selecionar_periodo(prefixo, label="📅 Período"):
    periodos = listar_periodos()

    if not periodos:
        st.warning("Nenhum período encontrado no Supabase.")
        return None

    periodo_ativo = obter_periodo_ativo()
    periodo_ativo_id = periodo_ativo.get("id")

    ids = [periodo["id"] for periodo in periodos]
    mapa = {periodo["id"]: periodo for periodo in periodos}

    indice_padrao = (
        ids.index(periodo_ativo_id)
        if periodo_ativo_id in ids
        else 0
    )

    def formatar(periodo_id):
        periodo = mapa[periodo_id]
        nome = periodo.get("nome") or f"Período {periodo_id}"
        status = str(periodo.get("status") or "").upper()
        marcador = "🟢 ATIVO" if periodo.get("ativo") else "⚪ ANTERIOR"
        return f"{nome} — {status} — {marcador}"

    selecionado = st.selectbox(
        label,
        ids,
        index=indice_padrao,
        format_func=formatar,
        key=f"{prefixo}_periodo_id",
    )

    return mapa[selecionado]


def mapa_periodos():
    return {
        periodo["id"]: periodo
        for periodo in listar_periodos()
    }



# ============================================================
# LIMPEZA DO CAMPO DE LEITURA
# ============================================================

if st.session_state.limpar_entrada:
    st.session_state.identificacao = ""
    st.session_state.limpar_entrada = False


# ============================================================
# CORES
# ============================================================

if st.session_state.tema == "Claro":
    CORES = {
        # Tema claro revisado para contraste (texto sempre bem mais escuro
        # que o fundo; nada de cinza claro sobre branco).
        "fundo": "#F4F6FA",
        "card": "#FFFFFF",
        "campo": "#FFFFFF",
        "texto": "#101828",
        "secundario": "#475467",
        "borda": "#7D8A9E",
        "verde_fundo": "#E7F8EF",
        "verde_borda": "#12915C",
        "verde_texto": "#05603A",
        "vermelho_fundo": "#FEEEEC",
        "vermelho_borda": "#D92D20",
        "vermelho_texto": "#912018",
        "laranja_fundo": "#FFF4E0",
        "laranja_borda": "#DC8A00",
        "laranja_texto": "#7A3E00",
        "azul_borda": "#1D4ED8",
        "cinza_fundo": "#EEF1F5",
        "cinza_borda": "#667085",
        "cinza_texto": "#1D2939",
        "primaria": "#1D4ED8",
        "primaria_texto": "#FFFFFF",
        "selecao": "#E0E9FF",
    }
else:
    CORES = {
        "fundo": "#0E1729",
        "card": "#182236",
        "texto": "#F8FAFC",
        "secundario": "#B7C1D1",
        "borda": "#394861",
        "verde_fundo": "#07382A",
        "verde_borda": "#32D583",
        "verde_texto": "#75E0A7",
        "vermelho_fundo": "#4A1717",
        "vermelho_borda": "#F97066",
        "vermelho_texto": "#FDA29B",
        "laranja_fundo": "#402409",
        "laranja_borda": "#FDB022",
        "laranja_texto": "#FEC84B",
        "azul_borda": "#53B1FD",
        "cinza_fundo": "#29364A",
        "cinza_borda": "#8291A8",
        "cinza_texto": "#E2E8F0",
        "campo": "#111C30",
        "primaria": "#3B82F6",
        "primaria_texto": "#FFFFFF",
        "selecao": "#25395C",
    }


# ============================================================
# CSS
# ============================================================

render_html(
    f"""
    <style>
    html, body, .stApp {{
        background-color: {CORES['fundo']} !important;
        color: {CORES['texto']} !important;
    }}
    header[data-testid="stHeader"] {{
        background-color: {CORES['fundo']} !important;
        box-shadow: none !important;
    }}
    div[data-testid="stDecoration"] {{ display: none !important; }}
    .block-container {{
        padding-top: 1.8rem !important;
        padding-bottom: 0.4rem !important;
        max-width: 1450px !important;
    }}
    h1, h2, h3, h4, h5, h6 {{ color: {CORES['texto']} !important; }}
    p, span, label {{ color: {CORES['texto']}; }}
    section[data-testid="stSidebar"] {{
        background-color: {CORES['card']} !important;
        border-right: 1px solid {CORES['borda']};
    }}
    section[data-testid="stSidebar"] * {{ color: {CORES['texto']}; }}
    div[data-testid="stForm"] {{
        background-color: {CORES['card']};
        border: 1px solid {CORES['borda']};
        border-radius: 12px;
    }}
    div[data-testid="stTextInput"] input {{
        height: 52px !important;
        font-size: 21px !important;
        font-weight: 700 !important;
        text-align: center !important;
        background-color: {CORES['card']} !important;
        color: {CORES['texto']} !important;
        border: 2px solid {CORES['borda']} !important;
        border-radius: 10px !important;
    }}
    div[data-testid="stTextInput"] input:focus {{
        border-color: {CORES['azul_borda']} !important;
        box-shadow: 0 0 0 2px rgba(46,144,250,.13) !important;
    }}
    .titulo {{
        text-align: center; color: {CORES['texto']}; font-size: 28px;
        font-weight: 900; line-height: 1.1; margin: 0 0 2px 0;
    }}
    .subtitulo {{
        text-align: center; color: {CORES['secundario']}; font-size: 12px;
        margin-bottom: 8px;
    }}
    .estoque-card {{
        background-color: {CORES['card']}; border: 1px solid {CORES['borda']};
        border-radius: 10px; text-align: center; padding: 8px 10px; min-height: 58px;
    }}
    .estoque-label {{
        color: {CORES['secundario']}; font-size: 11px; font-weight: 800; line-height: 1.1;
    }}
    .estoque-numero {{
        color: {CORES['texto']}; font-size: 25px; font-weight: 900;
        line-height: 1.15; margin-top: 3px;
    }}
    .pronto {{
        background-color: {CORES['verde_fundo']}; color: {CORES['verde_texto']};
        border: 1px solid {CORES['verde_borda']}; border-radius: 8px;
        text-align: center; font-size: 12px; font-weight: 900; padding: 5px;
        margin: 5px 0 6px 0;
    }}
    .status {{
        border-radius: 10px; text-align: center; font-size: 20px;
        font-weight: 900; padding: 8px; margin: 5px 0 6px 0;
    }}
    .status-verde {{
        background-color: {CORES['verde_fundo']}; color: {CORES['verde_texto']};
        border: 2px solid {CORES['verde_borda']};
    }}
    .status-vermelho {{
        background-color: {CORES['vermelho_fundo']}; color: {CORES['vermelho_texto']};
        border: 2px solid {CORES['vermelho_borda']};
    }}
    .status-laranja {{
        background-color: {CORES['laranja_fundo']}; color: {CORES['laranja_texto']};
        border: 2px solid {CORES['laranja_borda']};
    }}
    .status-cinza {{
        background-color: {CORES['cinza_fundo']}; color: {CORES['cinza_texto']};
        border: 2px solid {CORES['cinza_borda']};
    }}
    .nome-card {{
        background-color: {CORES['card']}; border: 1px solid {CORES['borda']};
        border-radius: 9px; color: {CORES['texto']}; text-align: center;
        font-size: 20px; font-weight: 900; padding: 7px; margin-bottom: 5px;
    }}
    .dados-card {{
        background-color: {CORES['card']}; border: 1px solid {CORES['borda']};
        border-radius: 9px; color: {CORES['texto']}; text-align: center;
        font-size: 13px; padding: 7px; margin-bottom: 5px;
    }}
    .dados-card strong {{ color: {CORES['texto']}; }}
    .motivo-card {{
        background-color: {CORES['vermelho_fundo']}; border: 2px solid {CORES['vermelho_borda']};
        border-radius: 10px; text-align: center; padding: 10px; margin-top: 5px;
    }}
    .motivo-titulo {{
        color: {CORES['vermelho_texto']}; font-size: 12px; font-weight: 900; margin-bottom: 3px;
    }}
    .motivo-texto {{
        color: {CORES['vermelho_texto']}; font-size: 19px; font-weight: 900; line-height: 1.2;
    }}
    .aguardando-card {{
        background-color: {CORES['laranja_fundo']}; border: 2px solid {CORES['laranja_borda']};
        color: {CORES['laranja_texto']}; border-radius: 10px; text-align: center;
        font-size: 17px; font-weight: 900; padding: 8px; margin: 5px 0;
    }}
    div[data-testid="stMetric"] {{
        background-color: {CORES['card']}; border: 1px solid {CORES['borda']};
        border-radius: 9px; padding: 7px 10px;
    }}
    .stButton button, .stFormSubmitButton button, .stDownloadButton button {{
        border-radius: 8px !important; font-weight: 700 !important;
    }}
    /* O áudio é reproduzido automaticamente, sem ocupar espaço no terminal. */
    div[data-testid="stAudio"] {{
        height: 1px !important;
        min-height: 1px !important;
        overflow: hidden !important;
        opacity: 0.01 !important;
        pointer-events: none !important;
    }}

    div[data-testid="stAudio"] audio {{
        height: 1px !important;
        width: 1px !important;
    }}

    /* ===== Componentes do Streamlit seguindo o tema escolhido ===== */
    div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] *,
    .stCaption, small {{
        color: {CORES['secundario']} !important;
    }}
    div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] * {{
        color: {CORES['secundario']} !important;
        font-weight: 700 !important;
    }}
    div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {{
        color: {CORES['texto']} !important;
    }}
    div[data-testid="stWidgetLabel"], div[data-testid="stWidgetLabel"] * {{
        color: {CORES['texto']} !important;
        font-weight: 600;
    }}

    /* Caixas de seleção (selectbox) e listas abertas */
    div[data-baseweb="select"] > div {{
        background-color: {CORES['campo']} !important;
        border: 1.5px solid {CORES['borda']} !important;
        color: {CORES['texto']} !important;
    }}
    div[data-baseweb="select"] *, div[data-baseweb="select"] input {{
        color: {CORES['texto']} !important;
    }}
    div[data-baseweb="select"] svg {{ fill: {CORES['texto']} !important; }}
    div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li,
    div[data-baseweb="popover"] div[role="listbox"], div[data-baseweb="menu"] {{
        background-color: {CORES['card']} !important;
        color: {CORES['texto']} !important;
    }}
    div[data-baseweb="popover"] li:hover, div[data-baseweb="popover"] li[aria-selected="true"] {{
        background-color: {CORES['selecao']} !important;
    }}

    /* Campos de texto longo e números */
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stNumberInput"] input {{
        background-color: {CORES['campo']} !important;
        color: {CORES['texto']} !important;
        border: 1.5px solid {CORES['borda']} !important;
    }}
    div[data-testid="stNumberInput"] button {{
        background-color: {CORES['cinza_fundo']} !important;
        color: {CORES['texto']} !important;
    }}
    div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"] {{
        background-color: {CORES['campo']} !important;
    }}
    input::placeholder, textarea::placeholder {{
        color: {CORES['secundario']} !important;
        opacity: 1 !important;
    }}

    /* Botões */
    button[kind="secondary"], button[kind="secondaryFormSubmit"],
    button[data-testid="stBaseButton-secondary"], button[data-testid="baseButton-secondary"],
    button[data-testid="stBaseButton-secondaryFormSubmit"],
    div[data-testid="stDownloadButton"] button {{
        background-color: {CORES['card']} !important;
        color: {CORES['texto']} !important;
        border: 1.5px solid {CORES['borda']} !important;
    }}
    button[kind="secondary"]:hover, button[kind="secondaryFormSubmit"]:hover,
    div[data-testid="stDownloadButton"] button:hover {{
        border-color: {CORES['azul_borda']} !important;
        color: {CORES['azul_borda']} !important;
    }}
    button[kind="primary"], button[kind="primaryFormSubmit"],
    button[data-testid="stBaseButton-primary"], button[data-testid="baseButton-primary"],
    button[data-testid="stBaseButton-primaryFormSubmit"] {{
        background-color: {CORES['primaria']} !important;
        border: 1.5px solid {CORES['primaria']} !important;
        color: {CORES['primaria_texto']} !important;
    }}
    button[kind="primary"] *, button[kind="primaryFormSubmit"] *,
    button[data-testid="stBaseButton-primary"] *, button[data-testid="stBaseButton-primaryFormSubmit"] * {{
        color: {CORES['primaria_texto']} !important;
    }}
    button:disabled {{ opacity: 0.55 !important; }}

    /* Opções do menu (radio) e caixas de confirmação (checkbox) */
    label[data-baseweb="radio"] > div:first-child {{
        background-color: {CORES['campo']} !important;
        border: 2px solid {CORES['cinza_borda']} !important;
    }}
    label[data-baseweb="radio"]:has(input:checked) > div:first-child {{
        background-color: {CORES['primaria']} !important;
        border-color: {CORES['primaria']} !important;
    }}
    label[data-baseweb="radio"] > div:first-child > div {{
        background-color: {CORES['campo']} !important;
    }}
    label[data-baseweb="radio"]:has(input:checked) {{ font-weight: 800; }}
    label[data-baseweb="checkbox"] > span:first-of-type {{
        background-color: {CORES['campo']} !important;
        border-color: {CORES['cinza_borda']} !important;
    }}
    label[data-baseweb="checkbox"]:has(input:checked) > span:first-of-type {{
        background-color: {CORES['primaria']} !important;
        border-color: {CORES['primaria']} !important;
    }}

    /* Expansores, upload de arquivos, tabelas e código */
    div[data-testid="stExpander"] details {{
        background-color: {CORES['card']} !important;
        border: 1px solid {CORES['borda']} !important;
    }}
    div[data-testid="stExpander"] summary, div[data-testid="stExpander"] summary * {{
        color: {CORES['texto']} !important;
    }}
    section[data-testid="stFileUploaderDropzone"] {{
        background-color: {CORES['campo']} !important;
        border: 2px dashed {CORES['borda']} !important;
    }}
    section[data-testid="stFileUploaderDropzone"] * {{ color: {CORES['texto']} !important; }}
    div[data-testid="stDataFrame"] {{
        border: 1px solid {CORES['borda']};
        border-radius: 8px;
    }}
    code, pre {{
        background-color: {CORES['cinza_fundo']} !important;
        color: {CORES['texto']} !important;
    }}
    hr {{ border-color: {CORES['borda']} !important; }}

    .rodape {{
        text-align: center; color: {CORES['secundario']}; font-size: 9px; margin-top: 5px;
    }}
    </style>
    """
)


# ============================================================
# AJUDANTES DE REGRA DE NEGÓCIO
# ============================================================

def preencher_dados_colaborador(resultado_liberacao, colaborador):
    resultado_liberacao["nome"] = colaborador["nome"]
    resultado_liberacao["matricula"] = colaborador["matricula"]
    resultado_liberacao["setor"] = colaborador["setor"]
    # Usados pelo botão "Atualizar crachá".
    resultado_liberacao["colaborador_id"] = colaborador.get("id")
    resultado_liberacao["id_mat"] = colaborador.get("id_mat")
    motivo_parcial = perda_parcial(colaborador)
    if motivo_parcial:
        resultado_liberacao["perda_parcial"] = motivo_parcial
    return resultado_liberacao


def limpar_modo_cracha():
    st.session_state.aguardando_cracha = False
    st.session_state.colaborador_cracha_id = None
    st.session_state.matricula_cracha = None
    st.session_state.modo_cracha = None
    st.session_state.dados_cracha = None


def iniciar_atualizacao_cracha(dados):
    """Botão "Atualizar crachá": o próximo crachá lido substitui o atual."""
    st.session_state.aguardando_cracha = True
    st.session_state.modo_cracha = "ATUALIZAR"
    st.session_state.colaborador_cracha_id = dados.get("colaborador_id")
    st.session_state.matricula_cracha = dados.get("matricula")
    st.session_state.dados_cracha = {
        "nome": dados.get("nome"),
        "matricula": dados.get("matricula"),
        "setor": dados.get("setor"),
        "id_mat": dados.get("id_mat"),
    }
    st.session_state.resultado_liberacao = None
    st.session_state.identificacao = ""


def cancelar_cadastro_cracha():
    limpar_modo_cracha()
    st.session_state.resultado_liberacao = None
    st.session_state.identificacao = ""


def registrar_evento_cracha(resultado_cadastro, dados, modo):
    """Deixa a troca/cadastro de crachá registrada no Histórico."""
    try:
        anterior = resultado_cadastro.get("id_cracha_anterior")
        registrar_historico(
            tipo_identificacao="ID CRACHÁ",
            id_cracha=resultado_cadastro.get("id_cracha"),
            matricula=dados.get("matricula"),
            nome=dados.get("nome"),
            setor=dados.get("setor"),
            resultado=(
                "CRACHA_ATUALIZADO" if modo == "ATUALIZAR" else "CRACHA_CADASTRADO"
            ),
            motivo=(
                f"Crachá anterior: {anterior}. " if anterior else ""
            ) + f"Usuário: {st.session_state.usuario or '-'}",
        )
    except Exception:
        pass


def obter_motivo_perda(colaborador):
    """Retorna exatamente o conteúdo válido da coluna Perde."""
    try:
        return texto_campo(colaborador["perde"])
    except (KeyError, IndexError):
        return ""


def processar_colaborador(colaborador, tipo_identificacao, cracha_cadastrado=False):
    """
    Regra central da retirada.
    Perda TOTAL (motivo na coluna Perde e Normal/Especial zeradas) tem
    prioridade sobre cadastro de crachá e liberação.
    Perda PARCIAL (motivo na Perde, mas ainda com cesta) segue a retirada
    normal, entregando só o que restou.
    """
    perde = obter_motivo_perda(colaborador)

    if perde and perdeu_todas(colaborador):
        # Chama a regra do banco para manter o histórico da tentativa.
        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            tipo_identificacao,
        )

        # O app garante que o que aparece na tela é EXATAMENTE a coluna Perde.
        resultado_liberacao = preencher_dados_colaborador(
            resultado_liberacao,
            colaborador,
        )
        resultado_liberacao["sucesso"] = False
        resultado_liberacao["resultado"] = "NEGADO"
        resultado_liberacao["perde"] = perde
        resultado_liberacao["motivo"] = perde

        st.session_state.resultado_liberacao = resultado_liberacao
        limpar_modo_cracha()
        st.session_state.limpar_entrada = True
        return True

    if cracha_cadastrado:
        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            tipo_identificacao,
        )
        resultado_liberacao = preencher_dados_colaborador(
            resultado_liberacao,
            colaborador,
        )
        resultado_liberacao["cracha_cadastrado"] = True
        st.session_state.resultado_liberacao = resultado_liberacao
        st.session_state.limpar_entrada = True
        return True

    return False


# ============================================================
# PROCESSAMENTO DA LEITURA
# ============================================================

def processar_identificacao():
    valor = str(st.session_state.get("identificacao", "")).strip()
    if not valor:
        return

    timestamp = time.time()

    if (
        valor == st.session_state.ultima_leitura
        and (timestamp - st.session_state.ultimo_timestamp) < 2
    ):
        st.session_state.limpar_entrada = True
        return

    st.session_state.ultima_leitura = valor
    st.session_state.ultimo_timestamp = timestamp

    # ========================================================
    # MODO: CADASTRAR CRACHÁ PARA MATRÍCULA JÁ LOCALIZADA
    # ========================================================
    if st.session_state.aguardando_cracha:
        colaborador_id = st.session_state.colaborador_cracha_id
        modo = st.session_state.modo_cracha or "CADASTRO"
        dados_cracha = dict(st.session_state.dados_cracha or {})

        resultado_cadastro = cadastrar_cracha(
            colaborador_id,
            valor,
            usuario=st.session_state.usuario,
        )

        if not resultado_cadastro["sucesso"]:
            # Continua aguardando: o operador pode tentar outro crachá
            # ou clicar em Cancelar.
            st.session_state.resultado_liberacao = {
                "sucesso": False,
                "resultado": "ERRO_CRACHA",
                "motivo": resultado_cadastro["motivo"],
            }
            st.session_state.limpar_entrada = True
            return

        registrar_evento_cracha(resultado_cadastro, dados_cracha, modo)
        limpar_modo_cracha()

        if modo == "ATUALIZAR":
            # Troca de crachá: só atualiza o cadastro, não libera cesta.
            st.session_state.resultado_liberacao = {
                "sucesso": False,
                "resultado": "CRACHA_ATUALIZADO",
                "nome": dados_cracha.get("nome"),
                "matricula": dados_cracha.get("matricula"),
                "setor": dados_cracha.get("setor"),
                "colaborador_id": colaborador_id,
                "id_mat": resultado_cadastro.get("id_cracha"),
                "id_anterior": resultado_cadastro.get("id_cracha_anterior"),
            }
            st.session_state.limpar_entrada = True
            return

        resultado = identificar(valor)
        if resultado["tipo"] != "COLABORADOR":
            st.session_state.resultado_liberacao = {
                "sucesso": False,
                "resultado": "ERRO",
                "motivo": (
                    "Crachá cadastrado, mas o colaborador não foi localizado."
                ),
            }
            st.session_state.limpar_entrada = True
            return

        colaborador = resultado["dados"]

        # Segurança adicional: se a coluna Perde tiver sido preenchida,
        # ela continua tendo prioridade mesmo após o cadastro do crachá.
        if processar_colaborador(
            colaborador,
            "ID CRACHÁ",
            cracha_cadastrado=True,
        ):
            return

    # ========================================================
    # IDENTIFICAÇÃO NORMAL
    # ========================================================
    resultado = identificar(valor)

    if resultado["tipo"] == "COLABORADOR":
        colaborador = resultado["dados"]

        # ----------------------------------------------------
        # 1º: PERDA TOTAL TEM PRIORIDADE ABSOLUTA
        # (perda parcial segue para a retirada do que restou)
        # ----------------------------------------------------
        perde = obter_motivo_perda(colaborador)
        if perde and perdeu_todas(colaborador):
            resultado_liberacao = liberar_cesta(
                colaborador["id"],
                resultado["identificacao"],
            )
            resultado_liberacao = preencher_dados_colaborador(
                resultado_liberacao,
                colaborador,
            )
            resultado_liberacao["sucesso"] = False
            resultado_liberacao["resultado"] = "NEGADO"
            resultado_liberacao["perde"] = perde
            resultado_liberacao["motivo"] = perde

            st.session_state.resultado_liberacao = resultado_liberacao
            limpar_modo_cracha()
            st.session_state.limpar_entrada = True
            return

        # ----------------------------------------------------
        # 2º: MATRÍCULA SEM CRACHÁ -> SOLICITAR CADASTRO
        # ----------------------------------------------------
        # Se o cadastro permanente já tem o crachá, copia para o período
        # e segue sem pedir de novo.
        if resultado["identificacao"] == "MATRÍCULA":
            colaborador = completar_cracha_pelo_cadastro(colaborador)

        if (
            resultado["identificacao"] == "MATRÍCULA"
            and colaborador.get("id_mat") is None
        ):
            st.session_state.aguardando_cracha = True
            st.session_state.modo_cracha = "CADASTRO"
            st.session_state.colaborador_cracha_id = colaborador["id"]
            st.session_state.matricula_cracha = colaborador["matricula"]
            st.session_state.dados_cracha = {
                "nome": colaborador["nome"],
                "matricula": colaborador["matricula"],
                "setor": colaborador["setor"],
                "id_mat": None,
            }
            st.session_state.resultado_liberacao = {
                "sucesso": False,
                "resultado": "AGUARDANDO_CRACHA",
                "nome": colaborador["nome"],
                "matricula": colaborador["matricula"],
                "setor": colaborador["setor"],
                "motivo": "Colaborador sem crachá cadastrado.",
            }
            st.session_state.limpar_entrada = True
            return

        # ----------------------------------------------------
        # 3º: LIBERAÇÃO NORMAL
        # ----------------------------------------------------
        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            resultado["identificacao"],
        )
        resultado_liberacao = preencher_dados_colaborador(
            resultado_liberacao,
            colaborador,
        )
        st.session_state.resultado_liberacao = resultado_liberacao

    elif resultado["tipo"] == "DEMITIDO":
        demitido = resultado["dados"]
        st.session_state.resultado_liberacao = {
            "sucesso": False,
            "resultado": "DEMITIDO",
            "motivo": "Colaborador cadastrado na lista de demitidos.",
            "nome": demitido["nome"],
            "matricula": demitido["chapa"],
        }

    elif resultado["tipo"] == "NAO_ENCONTRADO":
        registrar_tentativa_nao_encontrada(valor)
        st.session_state.resultado_liberacao = {
            "sucesso": False,
            "resultado": "NAO_ENCONTRADO",
            "motivo": "ID do crachá ou matrícula não encontrado.",
        }

    else:
        st.session_state.resultado_liberacao = {
            "sucesso": False,
            "resultado": "ERRO",
            "motivo": resultado.get("resultado", "Erro durante a identificação."),
        }

    st.session_state.limpar_entrada = True


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("## 🥫 Cestas Básicas")
    st.caption(f"👤 {st.session_state.nome_usuario}")
    st.caption("🔴 Administrador" if eh_admin else "🟢 Operador")

    try:
        periodo_sidebar = obter_periodo_ativo()
        status_sidebar = str(periodo_sidebar.get("status") or "").upper()
        icone_status = "🟢" if status_sidebar == "ABERTA" else "🔴"
        st.caption(
            f"📅 {periodo_sidebar.get('nome', 'Período ativo')} "
            f"• {icone_status} {status_sidebar or '-'}"
        )
    except Exception:
        st.caption("📅 Período ativo não carregado")

    st.divider()

    paginas = (
        [
            "Terminal",
            "Consulta",
            "Dashboard",
            "Histórico",
            "Períodos",
            "Colaboradores",
            "Áudios",
            "Estoque",
            "Importação",
            "Usuários",
            "Relatórios",
        ]
        if eh_admin
        else ["Terminal", "Consulta", "Dashboard"]
    )

    if st.session_state.pagina not in paginas:
        st.session_state.pagina = "Terminal"

    # O menu fica ligado direto ao session_state pela key.
    # Antes, o "index" mudava a cada troca de aba, o Streamlit recriava o
    # componente e era preciso clicar duas vezes para abrir a aba.
    st.radio(
        "Menu",
        paginas,
        key="pagina",
    )

    st.divider()

    st.radio(
        "🎨 Tema",
        ["Claro", "Escuro"],
        key="tema",
    )

    st.divider()

    st.button(
        "🚪 Sair",
        use_container_width=True,
        on_click=sair,
    )


# ============================================================
# CONSULTA
# ============================================================

def normalizar_numero_consulta(valor):
    texto = texto_campo(valor)
    if not texto:
        return None

    try:
        return int(float(texto))
    except Exception:
        return None


def tela_consulta():
    st.title("🔎 Consulta")
    st.caption(
        "Consulte por matrícula e acompanhe retirados, pendentes, perdas "
        "e colaboradores sem direito em cada período."
    )

    periodo = selecionar_periodo(
        "consulta",
        label="📅 Período da consulta",
    )

    if not periodo:
        return

    periodo_id = periodo["id"]

    st.info(
        f"📅 Período selecionado: **{periodo.get('nome', '-')}** "
        f"• Status: **{str(periodo.get('status') or '-').upper()}**"
    )

    registros = obter_consulta_retiradas(
        situacao="TODOS",
        periodo_id=periodo_id,
    )

    resumo = obter_resumo_consulta(
        periodo_id=periodo_id,
        registros=registros,
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("👥 Total", resumo["total"])

    with col2:
        st.metric("✅ Retirados", resumo["retirados"])

    with col3:
        st.metric("🟡 Pendentes", resumo["pendentes"])

    with col4:
        st.metric("🚫 Perderam", resumo.get("perderam", 0))

    with col5:
        st.metric("⚪ Sem direito", resumo.get("sem_direito", 0))

    if resumo.get("perda_parcial"):
        st.caption(
            f"⚠️ {resumo['perda_parcial']} colaborador(es) com perda parcial "
            "(perderam uma cesta, mas têm direito à que restou). "
            "Eles estão contados em Retirados/Pendentes."
        )

    st.divider()
    st.subheader("🔍 Consultar colaborador")

    with st.form("form_consulta_matricula", clear_on_submit=False):
        matricula = st.text_input(
            "Matrícula",
            key="consulta_matricula",
            placeholder="Digite a matrícula do colaborador...",
        )

        consultar = st.form_submit_button(
            "🔎 Consultar matrícula",
            type="primary",
            use_container_width=True,
        )

    if consultar:
        numero_digitado = normalizar_numero_consulta(
            matricula
        )

        if numero_digitado is None:
            st.session_state.resultado_consulta = {
                "status": "ERRO",
                "mensagem": "Digite uma matrícula válida.",
                "periodo_id": periodo_id,
            }
        else:
            encontrado = None

            for colaborador in registros:
                numero_banco = normalizar_numero_consulta(
                    colaborador.get("matricula")
                )

                if numero_banco == numero_digitado:
                    encontrado = colaborador
                    break

            if encontrado is None:
                st.session_state.resultado_consulta = {
                    "status": "NAO_ENCONTRADO",
                    "matricula": matricula,
                    "periodo_id": periodo_id,
                }
            else:
                st.session_state.resultado_consulta = {
                    "status": encontrado.get("situacao", "SEM DIREITO"),
                    "dados": dict(encontrado),
                    "periodo_id": periodo_id,
                }

    resultado = st.session_state.resultado_consulta

    if resultado and resultado.get("periodo_id") == periodo_id:
        if resultado["status"] == "ERRO":
            st.error(resultado["mensagem"])

        elif resultado["status"] == "NAO_ENCONTRADO":
            st.error(
                f"❌ Matrícula {resultado['matricula']} não encontrada neste período."
            )

        else:
            dados = resultado["dados"]
            status = resultado["status"]

            if status == "RETIRADO":
                st.success("✅ RETIRADA JÁ REALIZADA")
            elif status == "PENDENTE":
                st.warning("🟡 PENDENTE DE RETIRADA")
            elif status == "PERDEU":
                st.error("🚫 COLABORADOR PERDEU O DIREITO À CESTA")
            else:
                st.info("⚪ COLABORADOR SEM CESTA CADASTRADA")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "🆔 Matrícula",
                    texto_campo(dados.get("matricula")),
                )

            with col2:
                st.metric(
                    "🥫 Cesta normal",
                    int(dados.get("cesta_normal") or 0),
                )

            with col3:
                st.metric(
                    "⭐ Cesta especial",
                    int(dados.get("cesta_especial") or 0),
                )

            st.write(
                f"**👤 Nome:** {texto_campo(dados.get('nome'))}"
            )
            st.write(
                f"**🏢 Setor:** "
                f"{texto_campo(dados.get('setor')) or 'Não informado'}"
            )

            if status == "RETIRADO":
                st.info(
                    "🕐 **Data/Hora da retirada:** "
                    f"{texto_campo(dados.get('data_hora_retirada')) or 'Não informada'}"
                )

            motivo = texto_campo(
                dados.get("perde")
            )

            if motivo and status in {"PENDENTE", "RETIRADO"}:
                st.warning(
                    f"⚠️ **Perda parcial:** {motivo} — tem direito somente "
                    "às cestas indicadas acima."
                )
            elif motivo:
                st.error(
                    f"⚠️ **Motivo da perda:** {motivo}"
                )

    st.divider()
    st.subheader("📋 Situação dos colaboradores")

    if not registros:
        st.info("Nenhum colaborador cadastrado neste período.")
        return

    linhas = []

    for colaborador in registros:
        linhas.append(
            {
                "Matrícula": texto_campo(colaborador.get("matricula")),
                "Nome": texto_campo(colaborador.get("nome")),
                "Setor": texto_campo(colaborador.get("setor")),
                "Cesta Normal": int(colaborador.get("cesta_normal") or 0),
                "Cesta Especial": int(colaborador.get("cesta_especial") or 0),
                "Status": colaborador.get("situacao"),
                "Perda parcial": (
                    "SIM"
                    if colaborador.get("situacao") in {"PENDENTE", "RETIRADO"}
                    and texto_campo(colaborador.get("perde"))
                    else ""
                ),
                "Data/Hora Retirada": texto_campo(
                    colaborador.get("data_hora_retirada")
                ),
                "Motivo": texto_campo(colaborador.get("perde")),
            }
        )

    df = pd.DataFrame(
        linhas
    )

    filtro1, filtro2 = st.columns([2, 1])

    with filtro1:
        busca = st.text_input(
            "Buscar na relação",
            placeholder="Nome, matrícula ou setor...",
            key="consulta_busca_geral",
        )

    with filtro2:
        status_filtro = st.selectbox(
            "Situação",
            ["TODOS", "RETIRADO", "PENDENTE", "PERDEU", "SEM DIREITO"],
            key="consulta_status_geral",
        )

    if busca:
        mascara = (
            df[["Matrícula", "Nome", "Setor"]]
            .astype(str)
            .apply(
                lambda coluna: coluna.str.contains(
                    str(busca).strip(),
                    case=False,
                    na=False,
                )
            )
            .any(axis=1)
        )

        df = df[
            mascara
        ]

    if status_filtro != "TODOS":
        df = df[
            df["Status"] == status_filtro
        ]

    st.caption(
        f"{len(df)} colaborador(es) encontrado(s)."
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Cesta Normal": st.column_config.NumberColumn(format="%d"),
            "Cesta Especial": st.column_config.NumberColumn(format="%d"),
        },
    )


# ============================================================
# TERMINAL
# ============================================================

def tela_terminal():
    render_html(
        """
        <div class="titulo">🥫 ENTREGA DE CESTAS BÁSICAS</div>
        <div class="subtitulo">Terminal automático de distribuição</div>
        """
    )

    periodo_ativo = obter_periodo_ativo()
    status_periodo = str(periodo_ativo.get("status") or "").upper()
    entrega_finalizada = status_periodo == "FINALIZADA"

    st.caption(
        f"📅 Período ativo: **{periodo_ativo.get('nome', '-')}** "
        f"• Status: **{status_periodo or '-'}**"
    )

    if entrega_finalizada:
        st.error(
            "🔴 Este período está finalizado. "
            "Novas retiradas estão bloqueadas até a reabertura."
        )

    estoque = obter_estoque()
    normal = estoque["cesta_normal"] if estoque else 0
    especial = estoque["cesta_especial"] if estoque else 0

    col1, col2 = st.columns(2)
    with col1:
        render_html(
            f"""
            <div class="estoque-card">
                <div class="estoque-label">🥫 CESTAS NORMAIS</div>
                <div class="estoque-numero">{valor_seguro(normal)}</div>
            </div>
            """
        )
    with col2:
        render_html(
            f"""
            <div class="estoque-card">
                <div class="estoque-label">⭐ CESTAS ESPECIAIS</div>
                <div class="estoque-numero">{valor_seguro(especial)}</div>
            </div>
            """
        )

    if st.session_state.aguardando_cracha:
        dados_atual = (
            st.session_state.dados_cracha
            or st.session_state.resultado_liberacao
            or {}
        )
        atualizando = st.session_state.modo_cracha == "ATUALIZAR"
        titulo_modo = (
            "🔄 ATUALIZAÇÃO DO CRACHÁ"
            if atualizando
            else "🟡 CADASTRO DE CRACHÁ NECESSÁRIO"
        )
        cracha_atual = texto_campo(dados_atual.get("id_mat"))
        detalhe_cracha = (
            f"&nbsp; • &nbsp; 🪪 Crachá atual: <strong>{valor_seguro(cracha_atual)}</strong>"
            if atualizando and cracha_atual
            else ""
        )
        render_html(
            f"""
            <div class="aguardando-card">{titulo_modo}</div>
            """
        )
        render_html(
            f"""
            <div class="dados-card">
                👤 <strong>{valor_seguro(dados_atual.get('nome', ''))}</strong>
                &nbsp; • &nbsp;
                🆔 Matrícula: <strong>{valor_seguro(dados_atual.get('matricula', ''))}</strong>
                {detalhe_cracha}
                &nbsp; • &nbsp;
                🪪 Aproxime o novo crachá do leitor
            </div>
            """
        )
    else:
        st.markdown("### 🪪 Leitura do crachá")

    placeholder = (
        "Aproxime o crachá para cadastrar..."
        if st.session_state.aguardando_cracha
        else "Aproxime o crachá ou digite a matrícula..."
    )

    st.text_input(
        "ID do Crachá ou Matrícula",
        key="identificacao",
        placeholder=(
            "Período finalizado — reabra o período para realizar retiradas."
            if entrega_finalizada
            else placeholder
        ),
        on_change=processar_identificacao,
        label_visibility="collapsed",
        disabled=entrega_finalizada,
    )

    if entrega_finalizada:
        render_html(
            """
            <div class="status status-vermelho">🔴 PERÍODO FINALIZADO</div>
            """
        )
    elif st.session_state.aguardando_cracha:
        render_html(
            """
            <div class="aguardando-card">🪪 AGUARDANDO LEITURA DO NOVO CRACHÁ</div>
            """
        )
        _, col_cancelar, _ = st.columns([2, 1, 2])
        with col_cancelar:
            st.button(
                "✖️ Cancelar",
                key="cancelar_cadastro_cracha",
                on_click=cancelar_cadastro_cracha,
                use_container_width=True,
            )
    else:
        render_html(
            """
            <div class="pronto">🟢 SISTEMA PRONTO PARA A PRÓXIMA LEITURA</div>
            """
        )

    focar_campo_leitura()

    resultado = st.session_state.resultado_liberacao
    if not resultado:
        return

    render_resultado_terminal(resultado)

    # Pequeno botão em toda leitura de colaborador para trocar o crachá.
    if (
        resultado.get("colaborador_id") is not None
        and not st.session_state.aguardando_cracha
        and not entrega_finalizada
    ):
        _, col_botao = st.columns([4, 1])
        with col_botao:
            st.button(
                "🪪 Atualizar crachá",
                key=(
                    "atualizar_cracha_"
                    f"{resultado.get('colaborador_id')}_"
                    f"{st.session_state.ultimo_timestamp}"
                ),
                on_click=iniciar_atualizacao_cracha,
                args=(dict(resultado),),
                help="Cadastrar um novo crachá para este colaborador.",
                use_container_width=True,
            )


def focar_campo_leitura():
    """Coloca o cursor no campo de leitura para o leitor de crachá
    funcionar sem precisar clicar (ex.: depois de usar um botão)."""
    marcador = (
        f"{st.session_state.ultimo_timestamp}-"
        f"{st.session_state.aguardando_cracha}-"
        f"{st.session_state.modo_cracha}"
    )
    components.html(
        f"""
        <script>
        // {marcador}
        (function () {{
            try {{
                const doc = window.parent.document;
                const focar = () => {{
                    // No Terminal existe um único campo de texto: o de leitura.
                    const campo = doc.querySelector(
                        'div[data-testid="stTextInput"] input:not([disabled])'
                    );
                    const ativo = doc.activeElement;
                    const digitando = ativo && (
                        ["TEXTAREA", "SELECT"].includes(ativo.tagName)
                        || (ativo.tagName === "INPUT"
                            && !["radio", "checkbox", "button"].includes(ativo.type))
                    );
                    if (campo && !digitando) {{ campo.focus(); }}
                }};
                setTimeout(focar, 150);
                setTimeout(focar, 700);
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def render_resultado_terminal(resultado):
    status_resultado = resultado.get("resultado", "")

    if status_resultado == "CRACHA_ATUALIZADO":
        render_html(
            """
            <div class="status status-verde">🪪 CRACHÁ ATUALIZADO</div>
            """
        )
        anterior = texto_campo(resultado.get("id_anterior"))
        render_html(
            f"""
            <div class="nome-card">👤 {valor_seguro(resultado.get('nome', ''))}</div>
            <div class="dados-card">
                🆔 Matrícula: <strong>{valor_seguro(resultado.get('matricula', ''))}</strong>
                &nbsp; • &nbsp;
                🪪 Novo crachá: <strong>{valor_seguro(resultado.get('id_mat', ''))}</strong>
                {f"&nbsp; • &nbsp; Anterior: <strong>{valor_seguro(anterior)}</strong>" if anterior else ""}
            </div>
            """
        )
        st.success(
            "Crachá salvo no cadastro do colaborador. Nenhuma cesta foi liberada."
        )
        return

    if status_resultado not in {"", "AGUARDANDO_CRACHA"}:
        tocar_audio_resultado(resultado)

    if status_resultado == "AGUARDANDO_CRACHA":
        render_html(
            """
            <div class="status status-laranja">🟡 AGUARDANDO CADASTRO DO CRACHÁ</div>
            """
        )
        render_html(
            f"""
            <div class="nome-card">👤 {valor_seguro(resultado.get('nome', ''))}</div>
            <div class="dados-card">
                🆔 Matrícula: <strong>{valor_seguro(resultado.get('matricula', ''))}</strong>
                &nbsp; • &nbsp;
                🏢 Setor: <strong>{valor_seguro(resultado.get('setor', ''))}</strong>
            </div>
            """
        )
        return

    if status_resultado == "ERRO_CRACHA":
        render_html(
            """
            <div class="status status-vermelho">🔴 CRACHÁ NÃO PODE SER CADASTRADO</div>
            """
        )
        st.error(resultado.get("motivo", "Erro ao cadastrar o crachá."))
        return

    if resultado.get("sucesso"):
        render_html(
            """
            <div class="status status-verde">🟢 CESTA LIBERADA</div>
            """
        )
        render_html(
            f"""
            <div class="nome-card">👤 {valor_seguro(resultado.get('nome', ''))}</div>
            <div class="dados-card">
                🆔 Matrícula: <strong>{valor_seguro(resultado.get('matricula', ''))}</strong>
                &nbsp; • &nbsp;
                🏢 Setor: <strong>{valor_seguro(resultado.get('setor', ''))}</strong>
                &nbsp; • &nbsp;
                🕐 <strong>{valor_seguro(resultado.get('data_hora', ''))}</strong>
            </div>
            """
        )

        col1, col2 = st.columns(2)
        with col1:
            st.metric("🥫 Cesta normal", resultado.get("cesta_normal", 0))
        with col2:
            st.metric("⭐ Cesta especial", resultado.get("cesta_especial", 0))

        motivo_parcial = texto_campo(resultado.get("perda_parcial"))
        if motivo_parcial:
            render_html(
                f"""
                <div class="aguardando-card">
                    ⚠️ PERDEU PARTE DAS CESTAS — entregar somente a quantidade acima
                    <div style="font-size:15px; font-weight:700; margin-top:3px;">
                        Motivo: {valor_seguro(motivo_parcial)}
                    </div>
                </div>
                """
            )

        if resultado.get("cracha_cadastrado"):
            st.success("🪪 Crachá cadastrado e cesta liberada automaticamente.")
        return

    if status_resultado == "NEGADO":
        render_html(
            """
            <div class="status status-vermelho">🔴 CESTA NÃO LIBERADA</div>
            """
        )
        render_html(
            f"""
            <div class="nome-card">👤 {valor_seguro(resultado.get('nome', ''))}</div>
            <div class="dados-card">
                🆔 Matrícula: <strong>{valor_seguro(resultado.get('matricula', ''))}</strong>
                &nbsp; • &nbsp;
                🏢 Setor: <strong>{valor_seguro(resultado.get('setor', ''))}</strong>
            </div>
            """
        )

        # Prioridade absoluta ao valor que veio da coluna Perde.
        motivo = (
            texto_campo(resultado.get("perde"))
            or texto_campo(resultado.get("motivo"))
            or "Motivo não informado na coluna Perde."
        )

        render_html(
            f"""
            <div class="motivo-card">
                <div class="motivo-titulo">⚠️ MOTIVO DA PERDA DA CESTA</div>
                <div class="motivo-texto">{valor_seguro(motivo)}</div>
            </div>
            """
        )
        return

    if status_resultado == "DUPLICADO":
        render_html(
            """
            <div class="status status-laranja">🟠 RETIRADA JÁ REALIZADA</div>
            """
        )
        render_html(
            f"""
            <div class="nome-card">👤 {valor_seguro(resultado.get('nome', ''))}</div>
            <div class="dados-card">
                🆔 Matrícula: <strong>{valor_seguro(resultado.get('matricula', ''))}</strong>
                &nbsp; • &nbsp;
                🏢 Setor: <strong>{valor_seguro(resultado.get('setor', ''))}</strong>
            </div>
            """
        )
        st.warning(resultado.get("motivo", "Retirada já realizada."))
        return

    if status_resultado == "SEM_ESTOQUE":
        render_html(
            """
            <div class="status status-vermelho">🚫 ESTOQUE INSUFICIENTE</div>
            """
        )
        render_html(
            f"""
            <div class="nome-card">👤 {valor_seguro(resultado.get('nome', ''))}</div>
            """
        )
        st.warning(resultado.get("motivo", "Estoque insuficiente."))
        return

    if status_resultado == "DEMITIDO":
        render_html(
            """
            <div class="status status-cinza">⚫ COLABORADOR DEMITIDO</div>
            """
        )
        render_html(
            f"""
            <div class="nome-card">👤 {valor_seguro(resultado.get('nome', ''))}</div>
            <div class="dados-card">
                🆔 Chapa: <strong>{valor_seguro(resultado.get('matricula', ''))}</strong>
            </div>
            """
        )
        st.warning(resultado.get("motivo", "Colaborador desligado."))
        return

    if status_resultado == "NAO_ENCONTRADO":
        render_html(
            """
            <div class="status status-vermelho">❌ COLABORADOR NÃO ENCONTRADO</div>
            """
        )
        st.error(resultado.get("motivo", "Colaborador não encontrado."))
        return

    st.error(resultado.get("motivo", "Erro desconhecido."))


# ============================================================
# DASHBOARD
# ============================================================

def tela_dashboard():
    st.title("📊 Dashboard")

    periodo = obter_periodo_ativo()
    status = str(periodo.get("status") or "").upper()

    st.info(
        f"📅 Período ativo: **{periodo.get('nome', '-')}** "
        f"• Status: **{status or '-'}**"
    )

    indicadores = obter_indicadores(
        periodo_id=periodo["id"],
    )
    estoque = obter_estoque()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("🟢 Liberadas", indicadores["liberadas"])

    with col2:
        st.metric("🔴 Negadas", indicadores["negadas"])

    with col3:
        st.metric("🟠 Duplicadas", indicadores["duplicadas"])

    with col4:
        st.metric("❌ Não encontradas", indicadores["nao_encontradas"])

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("🥫 Normais entregues", indicadores["cestas_normais"])

    with col2:
        st.metric("⭐ Especiais entregues", indicadores["cestas_especiais"])

    with col3:
        st.metric("📋 Total de tentativas", indicadores["tentativas"])

    if estoque:
        st.divider()
        st.subheader("📦 Estoque atual")

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Cestas normais", estoque["cesta_normal"])

        with col2:
            st.metric("Cestas especiais", estoque["cesta_especial"])


# ============================================================
# HISTÓRICO
# ============================================================

def tela_historico():
    st.title("📜 Histórico de operações")
    st.caption(
        "O histórico é lido diretamente do Supabase. "
        "A opção Todos os registros também recupera operações antigas."
    )

    periodos = listar_periodos()
    mapa = {
        periodo["id"]: periodo
        for periodo in periodos
    }

    opcoes = ["__TODOS__"]
    opcoes.extend(
        periodo["id"]
        for periodo in periodos
    )
    opcoes.append("__LEGADO__")

    def formatar_opcao(valor):
        if valor == "__TODOS__":
            return "🗂️ Todos os registros do Supabase"

        if valor == "__LEGADO__":
            return "🕘 Histórico legado / sem período"

        periodo = mapa[valor]
        marcador = "🟢 ATIVO" if periodo.get("ativo") else "⚪ ANTERIOR"
        return (
            f"{periodo.get('nome', f'Período {valor}')} "
            f"— {str(periodo.get('status') or '').upper()} — {marcador}"
        )

    selecao = st.selectbox(
        "📅 Visualizar histórico",
        opcoes,
        format_func=formatar_opcao,
        key="historico_periodo_filtro",
    )

    if selecao == "__TODOS__":
        registros = obter_historico_geral(
            limite=20000,
        )
        titulo_contexto = "Todos os registros"

    elif selecao == "__LEGADO__":
        registros = obter_historico_legado(
            limite=20000,
        )
        titulo_contexto = "Histórico legado / sem período"

    else:
        registros = obter_historico(
            limite=10000,
            periodo_id=selecao,
        )
        titulo_contexto = mapa[selecao].get(
            "nome",
            f"Período {selecao}",
        )

    st.info(
        f"📌 Exibindo: **{titulo_contexto}**"
    )

    if not registros:
        st.info("Nenhuma operação registrada para este filtro.")
        return

    dados = []

    for registro in registros:
        periodo_id = registro.get("periodo_id")

        if periodo_id in mapa:
            nome_periodo = mapa[periodo_id].get("nome")
        elif periodo_id is None:
            nome_periodo = "LEGADO / SEM PERÍODO"
        else:
            nome_periodo = f"Período {periodo_id}"

        dados.append(
            {
                "Período": nome_periodo,
                "Data/Hora": registro.get("data_hora"),
                "Identificação": registro.get("tipo_identificacao"),
                "Crachá": registro.get("id_cracha"),
                "Matrícula": registro.get("matricula"),
                "Nome": registro.get("nome"),
                "Setor": registro.get("setor"),
                "Cesta Normal": registro.get("cesta_normal"),
                "Cesta Especial": registro.get("cesta_especial"),
                "Resultado": registro.get("resultado"),
                "Motivo": registro.get("motivo"),
            }
        )

    df = pd.DataFrame(
        dados
    )

    col1, col2 = st.columns(2)

    with col1:
        filtro = st.text_input(
            "🔎 Buscar",
            placeholder="Nome, matrícula, crachá, setor ou período...",
            key="historico_busca",
        )

    with col2:
        resultados = [
            valor
            for valor in df["Resultado"].dropna().unique().tolist()
            if texto_campo(valor)
        ]

        filtro_resultado = st.selectbox(
            "Resultado",
            ["TODOS"] + sorted(resultados),
            key="historico_resultado",
        )

    if filtro:
        mascara = (
            df.astype(str)
            .apply(
                lambda coluna: coluna.str.contains(
                    str(filtro).strip(),
                    case=False,
                    na=False,
                )
            )
            .any(axis=1)
        )

        df = df[
            mascara
        ]

    if filtro_resultado != "TODOS":
        df = df[
            df["Resultado"] == filtro_resultado
        ]

    st.caption(
        f"{len(df)} registro(s) encontrado(s)."
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    csv = df.to_csv(
        index=False,
        encoding="utf-8-sig",
    )

    st.download_button(
        "⬇️ Exportar histórico filtrado",
        data=csv,
        file_name="historico_cestas.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# PERÍODOS
# ============================================================

def tela_periodos():
    st.title("📅 Controle de períodos")
    st.caption(
        "Abra um novo período, finalize ou reabra o período ativo. "
        "Os períodos anteriores permanecem disponíveis no Histórico e na Consulta."
    )

    periodo = obter_periodo_ativo()
    status = str(periodo.get("status") or "").upper()

    if status == "FINALIZADA":
        st.error(
            f"🔴 Período ativo finalizado: **{periodo.get('nome', '-')}**"
        )
    else:
        st.success(
            f"🟢 Período ativo aberto: **{periodo.get('nome', '-')}**"
        )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("ID", periodo.get("id", "-"))

    with col2:
        st.metric("Status", status or "-")

    with col3:
        st.metric(
            "Início",
            periodo.get("data_inicio") or "-",
        )

    if periodo.get("data_finalizacao"):
        st.caption(
            f"Finalizado em: {periodo.get('data_finalizacao')} "
            f"• Por: {periodo.get('usuario_finalizacao') or '-'}"
        )

    st.divider()
    st.subheader("🔒 Abrir / fechar entrega do período ativo")

    if status != "FINALIZADA":
        observacao = st.text_area(
            "Observação da finalização",
            placeholder="Opcional.",
            key="periodos_observacao_finalizacao",
        )

        confirmar = st.checkbox(
            "Confirmo que desejo finalizar o período ativo.",
            key="periodos_confirmar_finalizacao",
        )

        if st.button(
            "🔴 Finalizar período ativo",
            type="primary",
            use_container_width=True,
            disabled=not confirmar,
            key="periodos_finalizar",
        ):
            try:
                finalizar_entrega(
                    usuario=st.session_state.usuario,
                    observacao=observacao,
                )
                st.success("Período finalizado com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(
                    f"Não foi possível finalizar o período: {erro}"
                )

    else:
        st.warning(
            "Enquanto o período estiver finalizado, o Terminal bloqueia novas retiradas."
        )

        if st.button(
            "🟢 Reabrir período ativo",
            use_container_width=True,
            key="periodos_reabrir",
        ):
            try:
                reabrir_entrega(
                    usuario=st.session_state.usuario,
                )
                st.success("Período reaberto com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(
                    f"Não foi possível reabrir o período: {erro}"
                )

    st.divider()
    st.subheader("🆕 Criar novo período")

    st.warning(
        "Ao criar um novo período, o período atual é arquivado/finalizado. "
        "O histórico já existente no Supabase não é apagado."
    )

    nome = st.text_input(
        "Nome do novo período",
        placeholder="Ex.: Outubro/2026",
        key="periodos_novo_nome",
    )

    observacao_novo = st.text_area(
        "Observação do novo período",
        placeholder="Opcional.",
        key="periodos_novo_observacao",
    )

    zerar_estoque = st.checkbox(
        "Zerar estoque ao criar o novo período",
        value=True,
        key="periodos_zerar_estoque",
    )

    confirmar_novo = st.checkbox(
        "Confirmo que desejo criar um novo período.",
        key="periodos_confirmar_novo",
    )

    if st.button(
        "🆕 Criar novo período",
        type="primary",
        use_container_width=True,
        disabled=not confirmar_novo,
        key="periodos_criar_novo",
    ):
        if not texto_campo(nome):
            st.error("Informe o nome do novo período.")
        else:
            try:
                iniciar_nova_entrega(
                    usuario=st.session_state.usuario,
                    observacao=observacao_novo,
                    zerar_estoque=zerar_estoque,
                    nome=nome,
                )

                st.session_state.resultado_consulta = None
                st.session_state.resultado_liberacao = None

                st.success(
                    "Novo período criado. Agora importe a planilha correspondente."
                )
                st.rerun()
            except Exception as erro:
                st.error(
                    f"Não foi possível criar o período: {erro}"
                )

    st.divider()
    st.subheader("📋 Períodos cadastrados")

    periodos = listar_periodos()

    if not periodos:
        st.info("Nenhum período cadastrado.")
        return

    tabela = pd.DataFrame(
        [
            {
                "ID": p.get("id"),
                "Nome": p.get("nome"),
                "Status": p.get("status"),
                "Ativo": "SIM" if p.get("ativo") else "NÃO",
                "Início": p.get("data_inicio"),
                "Finalização": p.get("data_finalizacao"),
                "Usuário criação": p.get("usuario_criacao"),
                "Usuário finalização": p.get("usuario_finalizacao"),
                "Observação": p.get("observacao"),
            }
            for p in periodos
        ]
    )

    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# ADMINISTRAÇÃO DE ÁUDIOS
# ============================================================


def tela_audios():
    st.title("🔊 Administração de áudios")
    st.caption(
        "Os áudios personalizados ficam no Supabase Storage. "
        "Você pode trocar a voz sem alterar o código ou fazer novo deploy."
    )

    setup = verificar_setup_audio()
    if not setup["ok"]:
        st.error(
            "O armazenamento de áudios ainda não está preparado no Supabase. "
            "Execute o arquivo supabase_audio_setup.sql no SQL Editor."
        )
        with st.expander("Detalhes técnicos"):
            st.code(setup.get("erro") or "Erro não informado.")
        return

    if service_role_configurada():
        st.success("🔐 Chave administrativa do Supabase configurada no servidor.")
    else:
        st.warning(
            "SUPABASE_SERVICE_ROLE_KEY não foi encontrada. O sistema está usando "
            "SUPABASE_KEY como fallback. Para o bucket privado, configure a service role "
            "nos Secrets do Streamlit e nunca a envie ao GitHub."
        )

    configuracoes = listar_configuracoes_audio()
    mapa_config = {item["tipo"]: item for item in configuracoes}

    opcoes = list(TIPOS_AUDIO.keys())
    tipo = st.selectbox(
        "Evento",
        opcoes,
        format_func=lambda chave: TIPOS_AUDIO[chave]["titulo"],
        key="audio_admin_tipo",
    )

    info = TIPOS_AUDIO[tipo]
    config = mapa_config[tipo]

    st.info(info["descricao"])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Status", "ATIVO" if config["ativo"] else "DESATIVADO")
    with col2:
        st.metric("Fonte", config["fonte"])
    with col3:
        st.metric("Arquivo", config["nome_arquivo"] or "Padrão / nenhum")

    if config.get("atualizado_em"):
        st.caption(
            f"Última alteração: {config['atualizado_em']} "
            f"• Usuário: {config.get('atualizado_por') or '-'}"
        )

    st.subheader("▶️ Áudio atual")
    audio_atual = obter_audio_evento(tipo)
    if audio_atual.get("dados"):
        render_preview_audio(
            audio_atual["dados"],
            audio_atual.get("mime_type") or "audio/mpeg",
        )
    elif not config["ativo"]:
        st.warning("Este áudio está desativado.")
    else:
        st.info("Não existe áudio configurado para este evento.")

    st.divider()
    st.subheader("⬆️ Enviar novo áudio")

    arquivo = st.file_uploader(
        "Escolha um arquivo MP3, WAV ou OGG",
        type=["mp3", "wav", "ogg"],
        key=f"audio_upload_{tipo}",
        help="Tamanho máximo: 10 MB.",
    )

    if arquivo is not None:
        dados_upload = arquivo.getvalue()
        st.caption(
            f"Arquivo selecionado: {arquivo.name} "
            f"• {len(dados_upload) / 1024:.1f} KB"
        )
        render_preview_audio(
            dados_upload,
            arquivo.type or (
                "audio/mpeg" if arquivo.name.lower().endswith(".mp3")
                else "audio/ogg" if arquivo.name.lower().endswith(".ogg")
                else "audio/wav"
            ),
        )

        if st.button(
            "💾 Salvar no Supabase",
            type="primary",
            use_container_width=True,
            key=f"audio_salvar_{tipo}",
        ):
            try:
                salvar_audio_personalizado(
                    tipo,
                    arquivo.name,
                    dados_upload,
                    usuario=st.session_state.usuario,
                )
                st.success("Áudio salvo no Supabase com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível salvar o áudio: {erro}")

    st.divider()
    st.subheader("⚙️ Comportamento")

    col_a, col_b = st.columns(2)

    with col_a:
        novo_status = not bool(config["ativo"])
        texto_status = (
            "🔇 Desativar no Terminal"
            if config["ativo"]
            else "🔊 Ativar no Terminal"
        )
        if st.button(
            texto_status,
            use_container_width=True,
            key=f"audio_status_{tipo}",
        ):
            try:
                definir_audio_ativo(
                    tipo,
                    novo_status,
                    usuario=st.session_state.usuario,
                )
                st.success("Status do áudio atualizado.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível atualizar o status: {erro}")

    with col_b:
        texto_restaurar = (
            "↩️ Restaurar áudio padrão"
            if info.get("padrao_local")
            else "🗑️ Remover áudio personalizado"
        )

        if st.button(
            texto_restaurar,
            use_container_width=True,
            key=f"audio_restaurar_{tipo}",
        ):
            try:
                restaurar_audio_padrao(
                    tipo,
                    usuario=st.session_state.usuario,
                )
                st.success("Configuração de áudio restaurada.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível restaurar o áudio: {erro}")

    st.divider()
    st.subheader("📋 Visão geral")

    tabela = pd.DataFrame(
        [
            {
                "Evento": item["titulo"],
                "Ativo": "SIM" if item["ativo"] else "NÃO",
                "Fonte": item["fonte"],
                "Arquivo": item["nome_arquivo"] or "-",
                "Atualizado por": item["atualizado_por"] or "-",
                "Atualizado em": item["atualizado_em"] or "-",
            }
            for item in configuracoes
        ]
    )

    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# ESTOQUE
# ============================================================

def tela_estoque():
    st.title("📦 Controle de estoque")
    estoque = obter_estoque()

    atual_normal = int(estoque["cesta_normal"])
    atual_especial = int(estoque["cesta_especial"])

    col1, col2 = st.columns(2)
    with col1:
        st.metric("🥫 Cestas normais", atual_normal)
        nova_normal = st.number_input(
            "Nova quantidade",
            min_value=0,
            step=1,
            value=atual_normal,
            key="estoque_normal_admin",
        )

    with col2:
        st.metric("⭐ Cestas especiais", atual_especial)
        nova_especial = st.number_input(
            "Nova quantidade",
            min_value=0,
            step=1,
            value=atual_especial,
            key="estoque_especial_admin",
        )

    if st.button("💾 Atualizar estoque", type="primary", use_container_width=True):
        configurar_estoque(nova_normal, nova_especial)
        st.success("Estoque atualizado.")
        st.rerun()


# ============================================================
# IMPORTAÇÃO
# ============================================================

def tela_importacao():
    st.title("📥 Importação de planilha")

    periodo = obter_periodo_ativo()
    status = str(periodo.get("status") or "").upper()

    st.info(
        f"📅 A planilha será importada para o período ativo: "
        f"**{periodo.get('nome', '-')}** • Status: **{status or '-'}**"
    )

    if status == "FINALIZADA":
        st.error(
            "Este período está finalizado. Reabra-o ou crie um novo período "
            "antes de importar uma planilha."
        )
        return

    st.info(
        'A planilha deve conter as abas "BANCO DE DADOS" e "Cesta demitidos".'
    )

    arquivo = st.file_uploader(
        "Selecione o arquivo Excel",
        type=["xlsx"],
    )

    if arquivo is None:
        return

    if st.button(
        "📥 Importar dados",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Processando planilha..."):
            resultado = importar_excel(
                arquivo,
                usuario=st.session_state.usuario,
            )

        if resultado["erros"]:
            st.error("A importação encontrou problemas.")

            for erro in resultado["erros"]:
                st.warning(erro)
        else:
            st.success("Importação concluída!")

            col1, col2 = st.columns(2)

            with col1:
                st.metric(
                    "Colaboradores",
                    resultado["colaboradores"],
                )

            with col2:
                st.metric(
                    "Demitidos",
                    resultado["demitidos"],
                )

            if resultado.get("crachas_do_cadastro"):
                st.info(
                    f"🪪 {resultado['crachas_do_cadastro']} crachá(s) "
                    "preenchido(s) a partir do cadastro permanente."
                )

            if resultado.get("retiradas_preservadas"):
                st.info(
                    f"🔒 {resultado['retiradas_preservadas']} retirada(s) já "
                    "registrada(s) foram mantidas (a planilha não as apagou)."
                )

        for aviso in resultado.get("avisos", []):
            st.warning(aviso)


# ============================================================
# USUÁRIOS
# ============================================================

def tela_usuarios():
    st.title("👥 Gerenciamento de usuários")
    st.subheader("➕ Criar usuário")

    with st.form("form_novo_usuario"):
        col1, col2 = st.columns(2)
        with col1:
            usuario = st.text_input("Usuário")
            nome = st.text_input("Nome")
        with col2:
            senha = st.text_input("Senha", type="password")
            perfil = st.selectbox("Perfil", ["OPERADOR", "ADMIN"])

        criar = st.form_submit_button(
            "Criar usuário", type="primary", use_container_width=True
        )
        if criar:
            try:
                criar_usuario(usuario, nome, senha, perfil)
                st.success("Usuário criado.")
                st.rerun()
            except Exception as erro:
                st.error(str(erro))

    st.divider()
    st.subheader("👤 Usuários cadastrados")
    usuarios = listar_usuarios()

    for usuario in usuarios:
        col1, col2, col3, col4 = st.columns([2, 3, 2, 2])
        with col1:
            st.write(f"**{usuario['usuario']}**")
        with col2:
            st.write(usuario["nome"])
        with col3:
            st.write(usuario["perfil"])
        with col4:
            if usuario["ativo"]:
                if st.button("🔴 Desativar", key=f"desativar_{usuario['id']}"):
                    alterar_status_usuario(usuario["id"], False)
                    st.rerun()
            else:
                if st.button("🟢 Ativar", key=f"ativar_{usuario['id']}"):
                    alterar_status_usuario(usuario["id"], True)
                    st.rerun()

    st.divider()
    st.subheader("🔑 Alterar senha")

    usuarios_ativos = [usuario for usuario in usuarios if usuario["ativo"]]
    if usuarios_ativos:
        opcoes = {
            usuario["id"]: f"{usuario['nome']} ({usuario['usuario']})"
            for usuario in usuarios_ativos
        }
        usuario_senha = st.selectbox(
            "Usuário",
            list(opcoes.keys()),
            format_func=lambda x: opcoes[x],
        )
        nova_senha = st.text_input(
            "Nova senha",
            type="password",
            key="nova_senha_admin",
        )
        if st.button("🔑 Alterar senha", use_container_width=True):
            try:
                alterar_senha_usuario(usuario_senha, nova_senha)
                st.success("Senha alterada.")
            except Exception as erro:
                st.error(str(erro))


# ============================================================
# RELATÓRIOS
# ============================================================

MOTIVO_ENTREGA_FINALIZADA = "Entrega finalizada"


def _chave_matricula(valor):
    """Compara matrículas como número (007682 == 7682)."""
    numero = normalizar_numero_consulta(valor)
    return numero if numero is not None else texto_campo(valor)


def _colaboradores_por_periodo(periodo_ids):
    mapa = {}
    for periodo_id in periodo_ids:
        if periodo_id is None:
            continue
        for colaborador in obter_colaboradores_periodo(periodo_id=periodo_id):
            mapa[(periodo_id, _chave_matricula(colaborador.get("matricula")))] = colaborador
    return mapa


def montar_relatorio(registros, mapa_nomes_periodo, incluir_sem_leitura=False):
    """Junta retiradas (LIBERADO) e leituras de quem perdeu a cesta (NEGADO).

    - Cada pessoa aparece uma vez por período (a leitura mais recente).
    - Bloqueios por "entrega finalizada" não são perda de cesta e ficam fora.
    - Quem retirou com perda parcial é identificado pela coluna Perde.
    """
    periodo_ids = {r.get("periodo_id") for r in registros}
    if incluir_sem_leitura:
        periodo_ids |= set(mapa_nomes_periodo.keys())

    colaboradores = _colaboradores_por_periodo(periodo_ids)

    linhas = []
    vistos_negado = set()
    pessoas_com_leitura = set()

    for registro in registros:  # já vem do mais recente para o mais antigo
        resultado = registro.get("resultado")
        periodo_id = registro.get("periodo_id")
        chave = (periodo_id, _chave_matricula(registro.get("matricula")))
        colaborador = colaboradores.get(chave) or {}
        motivo = texto_campo(registro.get("motivo"))

        if resultado == "LIBERADO":
            motivo_parcial = perda_parcial(colaborador) if colaborador else ""
            situacao = "RETIROU (PERDA PARCIAL)" if motivo_parcial else "RETIROU"
            motivo = motivo_parcial or motivo

        elif resultado == "NEGADO":
            if motivo.startswith(MOTIVO_ENTREGA_FINALIZADA):
                continue
            if chave in vistos_negado:
                continue
            vistos_negado.add(chave)
            situacao = "PERDEU A CESTA"
            motivo = motivo or texto_campo(colaborador.get("perde"))

        else:
            continue

        pessoas_com_leitura.add(chave)
        linhas.append(
            {
                "Período": mapa_nomes_periodo.get(periodo_id, "LEGADO / SEM PERÍODO"),
                "Data/Hora": registro.get("data_hora"),
                "Matrícula": registro.get("matricula"),
                "Crachá": registro.get("id_cracha"),
                "Nome": registro.get("nome"),
                "Setor": registro.get("setor"),
                "Cesta Normal": int(registro.get("cesta_normal") or 0),
                "Cesta Especial": int(registro.get("cesta_especial") or 0),
                "Situação": situacao,
                "Motivo": motivo,
            }
        )

    # Quem perdeu a cesta pela planilha, mas nunca passou no terminal.
    if incluir_sem_leitura:
        for (periodo_id, chave_mat), colaborador in colaboradores.items():
            if (periodo_id, chave_mat) in pessoas_com_leitura:
                continue
            if not perdeu_todas(colaborador):
                continue
            linhas.append(
                {
                    "Período": mapa_nomes_periodo.get(periodo_id, f"Período {periodo_id}"),
                    "Data/Hora": "",
                    "Matrícula": colaborador.get("matricula"),
                    "Crachá": colaborador.get("id_mat"),
                    "Nome": colaborador.get("nome"),
                    "Setor": colaborador.get("setor"),
                    "Cesta Normal": 0,
                    "Cesta Especial": 0,
                    "Situação": "PERDEU A CESTA (SEM LEITURA)",
                    "Motivo": texto_campo(colaborador.get("perde")),
                }
            )

    return pd.DataFrame(
        linhas,
        columns=[
            "Período", "Data/Hora", "Matrícula", "Crachá", "Nome", "Setor",
            "Cesta Normal", "Cesta Especial", "Situação", "Motivo",
        ],
    )


def tela_relatorios():
    st.title("📑 Relatórios")
    st.caption(
        "Mostra quem retirou e também as leituras de quem perdeu a cesta. "
        "Cada pessoa aparece uma vez por período."
    )

    periodos = listar_periodos()
    mapa = {
        periodo["id"]: periodo
        for periodo in periodos
    }
    nomes_periodo = {
        pid: (periodo.get("nome") or f"Período {pid}")
        for pid, periodo in mapa.items()
    }

    opcoes = ["__TODOS__"]
    opcoes.extend(
        periodo["id"]
        for periodo in periodos
    )
    opcoes.append("__LEGADO__")

    def formatar(valor):
        if valor == "__TODOS__":
            return "Todos os registros"
        if valor == "__LEGADO__":
            return "Histórico legado / sem período"

        periodo = mapa[valor]
        return (
            f"{periodo.get('nome', f'Período {valor}')} "
            f"— {str(periodo.get('status') or '').upper()}"
        )

    selecao = st.selectbox(
        "📅 Período do relatório",
        opcoes,
        format_func=formatar,
        key="relatorio_periodo",
    )

    if selecao == "__TODOS__":
        registros = obter_historico_geral(
            limite=100000,
        )
        nome_arquivo = "todos_periodos"
        periodos_relatorio = nomes_periodo

    elif selecao == "__LEGADO__":
        registros = obter_historico_legado(
            limite=100000,
        )
        nome_arquivo = "legado"
        periodos_relatorio = {}

    else:
        registros = obter_historico(
            limite=100000,
            periodo_id=selecao,
        )
        nome_arquivo = str(
            mapa[selecao].get("nome") or selecao
        )
        periodos_relatorio = {selecao: nomes_periodo[selecao]}

    incluir_sem_leitura = st.checkbox(
        "Incluir também quem perdeu a cesta e não passou no terminal",
        value=False,
        key="relatorio_incluir_sem_leitura",
        disabled=selecao == "__LEGADO__",
    )

    with st.spinner("Montando relatório..."):
        df = montar_relatorio(
            registros,
            periodos_relatorio if selecao != "__LEGADO__" else {},
            incluir_sem_leitura=incluir_sem_leitura and selecao != "__LEGADO__",
        )

    if df.empty:
        st.info("Nenhum dado disponível para o filtro selecionado.")
        return

    retiradas = df[df["Situação"].str.startswith("RETIROU")]
    perderam = df[df["Situação"].str.startswith("PERDEU")]
    parciais = df[df["Situação"] == "RETIROU (PERDA PARCIAL)"]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👥 Pessoas que retiraram", len(retiradas))
    with col2:
        st.metric("🥫 Cestas normais", int(retiradas["Cesta Normal"].sum()))
    with col3:
        st.metric("⭐ Cestas especiais", int(retiradas["Cesta Especial"].sum()))

    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric("🚫 Perderam a cesta", len(perderam))
    with col5:
        st.metric("⚠️ Retiraram com perda parcial", len(parciais))
    with col6:
        st.metric("📋 Total de pessoas no relatório", len(df))

    situacao = st.selectbox(
        "Situação",
        ["Todas", "Retiraram", "Retiraram com perda parcial", "Perderam a cesta"],
        key="relatorio_situacao",
    )

    if situacao == "Retiraram":
        df_exibir = retiradas
    elif situacao == "Retiraram com perda parcial":
        df_exibir = parciais
    elif situacao == "Perderam a cesta":
        df_exibir = perderam
    else:
        df_exibir = df

    if selecao != "__TODOS__":
        df_exibir = df_exibir.drop(columns=["Período"])

    st.caption(f"{len(df_exibir)} linha(s).")

    st.dataframe(
        df_exibir,
        use_container_width=True,
        hide_index=True,
    )

    csv = df_exibir.to_csv(
        index=False,
        encoding="utf-8-sig",
    )

    nome_seguro = (
        nome_arquivo
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )

    st.download_button(
        "⬇️ Exportar relatório",
        data=csv,
        file_name=f"relatorio_{nome_seguro}.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# CADASTRO PERMANENTE DE COLABORADORES
# ============================================================

def tela_colaboradores():
    st.title("🪪 Cadastro de colaboradores")
    st.caption(
        "Cadastro permanente: matrícula, nome, setor e ID do crachá. "
        "Vale para todos os períodos. É atualizado pela importação da "
        "planilha e sempre que um crachá é cadastrado no Terminal."
    )

    if not cadastro.cadastro_disponivel():
        st.error(
            "A tabela do cadastro ainda não existe no Supabase. Abra o "
            "Supabase → SQL Editor e execute o arquivo "
            "sql/001_cadastro_colaboradores.sql do GitHub."
        )
        if st.button("🔄 Verificar novamente"):
            cadastro.cadastro_disponivel.clear()
            st.rerun()
        return

    registros = cadastro.listar_cadastro()

    total = len(registros)
    com_cracha = sum(1 for r in registros if r.get("id_cracha") is not None)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👥 Colaboradores", total)
    with col2:
        st.metric("🪪 Com crachá", com_cracha)
    with col3:
        st.metric("⚠️ Sem crachá", total - com_cracha)

    st.divider()
    st.subheader("✏️ Cadastrar ou trocar crachá manualmente")
    st.caption(
        "No Terminal, use o botão 🪪 Atualizar crachá. Aqui é para "
        "ajustes do administrador (dá para usar o leitor no campo do crachá)."
    )

    with st.form("form_cracha_manual", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            matricula_manual = st.text_input("Matrícula", key="cad_matricula")
        with col_b:
            cracha_manual = st.text_input("ID do crachá", key="cad_cracha")
        salvar = st.form_submit_button(
            "💾 Salvar crachá", type="primary", use_container_width=True
        )

    if salvar:
        try:
            periodo = obter_periodo_ativo()
            retorno = cadastro.definir_cracha_por_matricula(
                matricula_manual,
                cracha_manual,
                periodo["id"],
                usuario=st.session_state.usuario,
            )
            if retorno["sucesso"]:
                registrar_historico(
                    tipo_identificacao="SISTEMA",
                    id_cracha=retorno.get("id_cracha"),
                    matricula=texto_campo(matricula_manual),
                    resultado="CRACHA_ATUALIZADO",
                    motivo=(
                        "Alterado na tela de cadastro. "
                        f"Usuário: {st.session_state.usuario or '-'}"
                    ),
                )
                st.success("Crachá salvo.")
                st.rerun()
            else:
                st.error(retorno["motivo"])
        except Exception as erro:
            st.error(f"Não foi possível salvar: {erro}")

    with st.expander("🗑️ Remover crachá (crachá perdido ou devolvido)"):
        matricula_remover = st.text_input(
            "Matrícula", key="cad_remover_matricula"
        )
        confirmar = st.checkbox(
            "Confirmo que desejo remover o crachá desta matrícula.",
            key="cad_remover_confirmar",
        )
        if st.button(
            "Remover crachá",
            disabled=not confirmar or not texto_campo(matricula_remover),
            key="cad_remover_botao",
        ):
            try:
                periodo = obter_periodo_ativo()
                cadastro.remover_cracha(matricula_remover, periodo["id"])
                st.success(
                    "Crachá removido. Na próxima leitura pela matrícula, "
                    "o Terminal pedirá o cadastro de um novo crachá."
                )
            except Exception as erro:
                st.error(f"Não foi possível remover: {erro}")

    st.divider()
    st.subheader("📋 Colaboradores cadastrados")

    if not registros:
        st.info(
            "Cadastro vazio. Importe a planilha do período para preenchê-lo."
        )
        return

    df = pd.DataFrame(
        [
            {
                "Matrícula": texto_campo(r.get("matricula")),
                "Nome": texto_campo(r.get("nome")),
                "Setor": texto_campo(r.get("setor")),
                "ID Crachá": texto_campo(r.get("id_cracha")),
                "Atualizado em": texto_campo(r.get("atualizado_em"))[:16].replace("T", " "),
                "Atualizado por": texto_campo(r.get("atualizado_por")),
            }
            for r in registros
        ]
    )

    filtro1, filtro2 = st.columns([2, 1])
    with filtro1:
        busca = st.text_input(
            "Buscar",
            placeholder="Nome, matrícula, setor ou crachá...",
            key="cad_busca",
        )
    with filtro2:
        situacao = st.selectbox(
            "Crachá",
            ["Todos", "Com crachá", "Sem crachá"],
            key="cad_situacao",
        )

    if busca:
        mascara = (
            df[["Matrícula", "Nome", "Setor", "ID Crachá"]]
            .astype(str)
            .apply(
                lambda coluna: coluna.str.contains(
                    str(busca).strip(), case=False, na=False, regex=False
                )
            )
            .any(axis=1)
        )
        df = df[mascara]

    if situacao == "Com crachá":
        df = df[df["ID Crachá"] != ""]
    elif situacao == "Sem crachá":
        df = df[df["ID Crachá"] == ""]

    st.caption(f"{len(df)} colaborador(es).")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Exportar cadastro",
        data=df.to_csv(index=False, encoding="utf-8-sig"),
        file_name="cadastro_colaboradores.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# ROTEAMENTO
# ============================================================

pagina = st.session_state.pagina

if pagina == "Terminal":
    tela_terminal()
elif pagina == "Consulta":
    tela_consulta()
elif pagina == "Dashboard":
    tela_dashboard()
elif pagina == "Histórico" and eh_admin:
    tela_historico()
elif pagina == "Períodos" and eh_admin:
    tela_periodos()
elif pagina == "Colaboradores" and eh_admin:
    tela_colaboradores()
elif pagina == "Áudios" and eh_admin:
    tela_audios()
elif pagina == "Estoque" and eh_admin:
    tela_estoque()
elif pagina == "Importação" and eh_admin:
    tela_importacao()
elif pagina == "Usuários" and eh_admin:
    tela_usuarios()
elif pagina == "Relatórios" and eh_admin:
    tela_relatorios()
else:
    tela_terminal()


# ============================================================
# RODAPÉ
# ============================================================

render_html(
    """
    <div class="rodape">
        Sistema de Entrega de Cestas Básicas • Controle de distribuição
    </div>
    """
)
