import time
import textwrap
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

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
)
from services.importador import importar_excel
from services.identificacao import identificar, cadastrar_cracha, buscar_por_matricula
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
# ÁUDIO DA RETIRADA
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "assets" / "audio"


def obter_audio_retirada(cesta_normal, cesta_especial):
    """
    Retorna o arquivo e a frase correspondente às cestas liberadas.

    Regra:
        normal > 0 e especial == 0 -> Uma cesta normal
        normal == 0 e especial > 0 -> Uma cesta especial
        normal > 0 e especial > 0 -> Uma cesta normal e uma especial
    """

    try:
        normal = int(cesta_normal or 0)
    except (TypeError, ValueError):
        normal = 0

    try:
        especial = int(cesta_especial or 0)
    except (TypeError, ValueError):
        especial = 0

    if normal > 0 and especial > 0:
        return (
            AUDIO_DIR / "cesta_normal_especial.wav",
            "Uma cesta normal e uma especial.",
        )

    if normal > 0:
        return (
            AUDIO_DIR / "cesta_normal.wav",
            "Uma cesta normal.",
        )

    if especial > 0:
        return (
            AUDIO_DIR / "cesta_especial.wav",
            "Uma cesta especial.",
        )

    return None, ""


def tocar_audio_retirada(resultado):
    """
    Reproduz o aviso somente uma vez para cada retirada liberada.

    O identificador da operação usa matrícula + data/hora + quantidades,
    evitando que o áudio repita em cada rerun do Streamlit.
    """

    if not resultado or not resultado.get("sucesso"):
        return

    arquivo, frase = obter_audio_retirada(
        resultado.get("cesta_normal", 0),
        resultado.get("cesta_especial", 0),
    )

    if arquivo is None:
        return

    identificador = "|".join(
        [
            texto_campo(resultado.get("matricula")),
            texto_campo(resultado.get("data_hora")),
            str(resultado.get("cesta_normal", 0)),
            str(resultado.get("cesta_especial", 0)),
        ]
    )

    if st.session_state.get("ultimo_audio_operacao") == identificador:
        return

    if arquivo.exists():
        st.audio(
            str(arquivo),
            format="audio/wav",
            autoplay=True,
        )
        st.session_state.ultimo_audio_operacao = identificador
        st.session_state.ultima_frase_audio = frase
    else:
        # Não bloqueia a retirada se os arquivos de áudio não existirem.
        st.session_state.ultima_frase_audio = ""


# ============================================================
# BANCO
# ============================================================

inicializar_banco()
inicializar_usuarios()


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
    "ultimo_audio_operacao": None,
    "ultima_frase_audio": "",
}

for chave, valor in valores_iniciais.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


# ============================================================
# LOGIN
# ============================================================

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
        "fundo": "#F6F8FB",
        "card": "#FFFFFF",
        "texto": "#172033",
        "secundario": "#667085",
        "borda": "#D8DEE9",
        "verde_fundo": "#EAFBF2",
        "verde_borda": "#16A66A",
        "verde_texto": "#057647",
        "vermelho_fundo": "#FFF0EF",
        "vermelho_borda": "#E5484D",
        "vermelho_texto": "#B42318",
        "laranja_fundo": "#FFF7E6",
        "laranja_borda": "#F59E0B",
        "laranja_texto": "#A15C00",
        "azul_borda": "#2E90FA",
        "cinza_fundo": "#F2F4F7",
        "cinza_borda": "#98A2B3",
        "cinza_texto": "#344054",
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
        "cinza_borda": "#667085",
        "cinza_texto": "#E2E8F0",
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
    return resultado_liberacao


def obter_motivo_perda(colaborador):
    """Retorna exatamente o conteúdo válido da coluna Perde."""
    try:
        return texto_campo(colaborador["perde"])
    except (KeyError, IndexError):
        return ""


def processar_colaborador(colaborador, tipo_identificacao, cracha_cadastrado=False):
    """
    Regra central da retirada.
    A coluna Perde SEMPRE tem prioridade sobre cadastro de crachá e liberação.
    """
    perde = obter_motivo_perda(colaborador)

    if perde:
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
        st.session_state.aguardando_cracha = False
        st.session_state.colaborador_cracha_id = None
        st.session_state.matricula_cracha = None
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
        cadastro = cadastrar_cracha(colaborador_id, valor)

        if not cadastro["sucesso"]:
            st.session_state.resultado_liberacao = {
                "sucesso": False,
                "resultado": "ERRO_CRACHA",
                "motivo": cadastro["motivo"],
            }
            st.session_state.limpar_entrada = True
            return

        st.session_state.aguardando_cracha = False
        st.session_state.colaborador_cracha_id = None
        st.session_state.matricula_cracha = None

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
        # 1º: COLUNA PERDE TEM PRIORIDADE ABSOLUTA
        # ----------------------------------------------------
        perde = obter_motivo_perda(colaborador)
        if perde:
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
            st.session_state.aguardando_cracha = False
            st.session_state.colaborador_cracha_id = None
            st.session_state.matricula_cracha = None
            st.session_state.limpar_entrada = True
            return

        # ----------------------------------------------------
        # 2º: MATRÍCULA SEM CRACHÁ -> SOLICITAR CADASTRO
        # ----------------------------------------------------
        if (
            resultado["identificacao"] == "MATRÍCULA"
            and colaborador["id_mat"] is None
        ):
            st.session_state.aguardando_cracha = True
            st.session_state.colaborador_cracha_id = colaborador["id"]
            st.session_state.matricula_cracha = colaborador["matricula"]
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

    st.session_state.pagina = st.radio(
        "Menu",
        paginas,
        index=paginas.index(st.session_state.pagina),
    )

    st.divider()

    novo_tema = st.radio(
        "🎨 Tema",
        ["Claro", "Escuro"],
        index=0 if st.session_state.tema == "Claro" else 1,
    )

    if novo_tema != st.session_state.tema:
        st.session_state.tema = novo_tema
        st.rerun()

    st.divider()

    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.logado = False
        st.session_state.usuario_id = None
        st.session_state.usuario = None
        st.session_state.nome_usuario = None
        st.session_state.perfil = None
        st.session_state.pagina = "Terminal"
        st.session_state.identificacao = ""
        st.session_state.resultado_liberacao = None
        st.session_state.resultado_consulta = None
        st.session_state.aguardando_cracha = False
        st.session_state.colaborador_cracha_id = None
        st.session_state.matricula_cracha = None
        st.rerun()


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

    resumo = obter_resumo_consulta(
        periodo_id=periodo_id,
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

    registros = obter_consulta_retiradas(
        situacao="TODOS",
        periodo_id=periodo_id,
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

            if motivo:
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
        resultado_atual = st.session_state.resultado_liberacao or {}
        render_html(
            """
            <div class="aguardando-card">🟡 CADASTRO DE CRACHÁ NECESSÁRIO</div>
            """
        )
        render_html(
            f"""
            <div class="dados-card">
                👤 <strong>{valor_seguro(resultado_atual.get('nome', ''))}</strong>
                &nbsp; • &nbsp;
                🆔 Matrícula: <strong>{valor_seguro(resultado_atual.get('matricula', ''))}</strong>
                &nbsp; • &nbsp;
                🪪 Aproxime o novo crachá
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
    else:
        render_html(
            """
            <div class="pronto">🟢 SISTEMA PRONTO PARA A PRÓXIMA LEITURA</div>
            """
        )

    resultado = st.session_state.resultado_liberacao
    if not resultado:
        return

    status_resultado = resultado.get("resultado", "")

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

        # Aviso por voz da quantidade/tipo de cesta liberada.
        tocar_audio_retirada(resultado)

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
                arquivo
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

def tela_relatorios():
    st.title("📑 Relatórios")

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
            limite=20000,
        )
        nome_arquivo = "todos_periodos"

    elif selecao == "__LEGADO__":
        registros = obter_historico_legado(
            limite=20000,
        )
        nome_arquivo = "legado"

    else:
        registros = obter_historico(
            limite=10000,
            periodo_id=selecao,
        )
        nome_arquivo = str(
            mapa[selecao].get("nome") or selecao
        )

    if not registros:
        st.info("Nenhum dado disponível para o filtro selecionado.")
        return

    dados = []

    for registro in registros:
        dados.append(
            {
                "Data/Hora": registro.get("data_hora"),
                "Matrícula": registro.get("matricula"),
                "Crachá": registro.get("id_cracha"),
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

    retiradas = df[
        df["Resultado"] == "LIBERADO"
    ].copy()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "👥 Pessoas que retiraram",
            len(retiradas),
        )

    with col2:
        st.metric(
            "🥫 Cestas normais",
            int(retiradas["Cesta Normal"].fillna(0).sum())
            if not retiradas.empty
            else 0,
        )

    with col3:
        st.metric(
            "⭐ Cestas especiais",
            int(retiradas["Cesta Especial"].fillna(0).sum())
            if not retiradas.empty
            else 0,
        )

    st.dataframe(
        retiradas,
        use_container_width=True,
        hide_index=True,
    )

    csv = retiradas.to_csv(
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
        "⬇️ Exportar retiradas",
        data=csv,
        file_name=f"relatorio_retiradas_{nome_seguro}.csv",
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
elif pagina == "Estoque" and eh_admin:
    tela_estoque()
elif pagina == "Importação" and eh_admin:
    tela_importacao()
elif pagina == "Usuários" and eh_admin:
    tela_usuarios()
elif pagina == "Relatórios" and eh_admin:
    tela_relatorios()
else:
    st.session_state.pagina = "Terminal"
    st.rerun()


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
