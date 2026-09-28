import time
import textwrap
from html import escape

import pandas as pd
import streamlit as st

from database.database import (
    inicializar_banco,
    obter_estoque,
    configurar_estoque,
    liberar_cesta,
    registrar_tentativa_nao_encontrada,
    obter_historico,
    obter_indicadores,
)

from services.importador import importar_excel

from services.identificacao import (
    identificar,
    cadastrar_cracha,
)

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

    return escape(
        str(valor)
    )


def render_html(conteudo):

    conteudo = textwrap.dedent(
        str(conteudo)
    ).strip()

    if hasattr(
        st,
        "html",
    ):

        st.html(
            conteudo
        )

    else:

        conteudo = " ".join(
            linha.strip()
            for linha in conteudo.splitlines()
        )

        st.markdown(
            conteudo,
            unsafe_allow_html=True,
        )


def texto_campo(valor):
    """
    Normaliza campos vindos do SQLite/Excel.

    Impede que valores vazios como None, nan ou NaT
    sejam interpretados como texto válido.
    """

    if valor is None:
        return ""

    texto = str(
        valor
    ).strip()

    if texto.lower() in {
        "",
        "nan",
        "none",
        "null",
        "nat",
    }:

        return ""

    return texto


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

    "aguardando_cracha": False,

    "colaborador_cracha_id": None,

    "matricula_cracha": None,

}


for chave, valor in valores_iniciais.items():

    if chave not in st.session_state:

        st.session_state[
            chave
        ] = valor


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

        .login-icon {
            font-size: 56px;
            line-height: 1;
            margin-bottom: 8px;
        }

        .login-title {
            font-size: 34px;
            font-weight: 900;
            margin-bottom: 5px;
        }

        .login-subtitle {
            font-size: 15px;
            color: #98A2B3;
            margin-bottom: 18px;
        }

        </style>

        <div class="login-container">

            <div class="login-icon">
                🥫
            </div>

            <div class="login-title">
                Cestas Básicas
            </div>

            <div class="login-subtitle">
                Sistema de controle de distribuição
            </div>

        </div>
        """
    )

    _, centro, _ = st.columns(
        [
            1,
            1.5,
            1,
        ]
    )

    with centro:

        with st.form(
            "form_login"
        ):

            usuario = st.text_input(
                "Usuário",
                placeholder="Digite o usuário",
            )

            senha = st.text_input(
                "Senha",
                type="password",
                placeholder="Digite a senha",
            )

            entrar = (
                st.form_submit_button(
                    "🔐 Entrar",
                    type="primary",
                    use_container_width=True,
                )
            )

            if entrar:

                registro = autenticar(
                    usuario,
                    senha,
                )

                if registro is None:

                    st.error(
                        "Usuário ou senha inválidos."
                    )

                else:

                    st.session_state.logado = True

                    st.session_state.usuario_id = (
                        registro["id"]
                    )

                    st.session_state.usuario = (
                        registro["usuario"]
                    )

                    st.session_state.nome_usuario = (
                        registro["nome"]
                    )

                    st.session_state.perfil = (
                        registro["perfil"]
                    )

                    st.session_state.pagina = (
                        "Terminal"
                    )

                    st.rerun()


# ============================================================
# EXIGIR LOGIN
# ============================================================

if not st.session_state.logado:

    tela_login()

    st.stop()


# ============================================================
# PERFIL
# ============================================================

eh_admin = (
    st.session_state.perfil
    == "ADMIN"
)


# ============================================================
# LIMPAR CAMPO RFID / MATRÍCULA
# ============================================================

if st.session_state.limpar_entrada:

    st.session_state.identificacao = ""

    st.session_state.limpar_entrada = False


# ============================================================
# CORES
# ============================================================

if st.session_state.tema == "Claro":

    CORES = {

        "fundo":
            "#F6F8FB",

        "card":
            "#FFFFFF",

        "texto":
            "#172033",

        "secundario":
            "#667085",

        "borda":
            "#D8DEE9",

        "verde_fundo":
            "#EAFBF2",

        "verde_borda":
            "#16A66A",

        "verde_texto":
            "#057647",

        "vermelho_fundo":
            "#FFF0EF",

        "vermelho_borda":
            "#E5484D",

        "vermelho_texto":
            "#B42318",

        "laranja_fundo":
            "#FFF7E6",

        "laranja_borda":
            "#F59E0B",

        "laranja_texto":
            "#A15C00",

        "azul_borda":
            "#2E90FA",

        "cinza_fundo":
            "#F2F4F7",

        "cinza_borda":
            "#98A2B3",

        "cinza_texto":
            "#344054",

    }

else:

    CORES = {

        "fundo":
            "#0E1729",

        "card":
            "#182236",

        "texto":
            "#F8FAFC",

        "secundario":
            "#B7C1D1",

        "borda":
            "#394861",

        "verde_fundo":
            "#07382A",

        "verde_borda":
            "#32D583",

        "verde_texto":
            "#75E0A7",

        "vermelho_fundo":
            "#4A1717",

        "vermelho_borda":
            "#F97066",

        "vermelho_texto":
            "#FDA29B",

        "laranja_fundo":
            "#402409",

        "laranja_borda":
            "#FDB022",

        "laranja_texto":
            "#FEC84B",

        "azul_borda":
            "#53B1FD",

        "cinza_fundo":
            "#29364A",

        "cinza_borda":
            "#667085",

        "cinza_texto":
            "#E2E8F0",

    }


# ============================================================
# CSS
# ============================================================

render_html(
    f"""
    <style>

    html,
    body,
    .stApp {{

        background-color:
            {CORES["fundo"]} !important;

        color:
            {CORES["texto"]} !important;

    }}


    header[data-testid="stHeader"] {{

        background-color:
            {CORES["fundo"]} !important;

        box-shadow:
            none !important;

    }}


    div[data-testid="stDecoration"] {{

        display:
            none !important;

    }}


    .block-container {{

        padding-top:
            1.8rem !important;

        padding-bottom:
            0.4rem !important;

        max-width:
            1450px !important;

    }}


    h1,
    h2,
    h3,
    h4,
    h5,
    h6 {{

        color:
            {CORES["texto"]} !important;

    }}


    p,
    span,
    label {{

        color:
            {CORES["texto"]};

    }}


    section[data-testid="stSidebar"] {{

        background-color:
            {CORES["card"]} !important;

        border-right:
            1px solid {CORES["borda"]};

    }}


    section[data-testid="stSidebar"] * {{

        color:
            {CORES["texto"]};

    }}


    div[data-testid="stForm"] {{

        background-color:
            {CORES["card"]};

        border:
            1px solid {CORES["borda"]};

        border-radius:
            12px;

    }}


    div[data-testid="stTextInput"] input {{

        height:
            52px !important;

        font-size:
            21px !important;

        font-weight:
            700 !important;

        text-align:
            center !important;

        background-color:
            {CORES["card"]} !important;

        color:
            {CORES["texto"]} !important;

        border:
            2px solid
            {CORES["borda"]} !important;

        border-radius:
            10px !important;

    }}


    div[data-testid="stTextInput"]
    input:focus {{

        border-color:
            {CORES["azul_borda"]} !important;

        box-shadow:
            0 0 0 2px
            rgba(
                46,
                144,
                250,
                .13
            ) !important;

    }}


    .titulo {{

        text-align:
            center;

        color:
            {CORES["texto"]};

        font-size:
            28px;

        font-weight:
            900;

        line-height:
            1.1;

        margin:
            0 0 2px 0;

    }}


    .subtitulo {{

        text-align:
            center;

        color:
            {CORES["secundario"]};

        font-size:
            12px;

        margin-bottom:
            8px;

    }}


    .estoque-card {{

        background-color:
            {CORES["card"]};

        border:
            1px solid
            {CORES["borda"]};

        border-radius:
            10px;

        text-align:
            center;

        padding:
            8px 10px;

        min-height:
            58px;

    }}


    .estoque-label {{

        color:
            {CORES["secundario"]};

        font-size:
            11px;

        font-weight:
            800;

        line-height:
            1.1;

    }}


    .estoque-numero {{

        color:
            {CORES["texto"]};

        font-size:
            25px;

        font-weight:
            900;

        line-height:
            1.15;

        margin-top:
            3px;

    }}


    .pronto {{

        background-color:
            {CORES["verde_fundo"]};

        color:
            {CORES["verde_texto"]};

        border:
            1px solid
            {CORES["verde_borda"]};

        border-radius:
            8px;

        text-align:
            center;

        font-size:
            12px;

        font-weight:
            900;

        padding:
            5px;

        margin:
            5px 0 6px 0;

    }}


    .status {{

        border-radius:
            10px;

        text-align:
            center;

        font-size:
            20px;

        font-weight:
            900;

        padding:
            8px;

        margin:
            5px 0 6px 0;

    }}


    .status-verde {{

        background-color:
            {CORES["verde_fundo"]};

        color:
            {CORES["verde_texto"]};

        border:
            2px solid
            {CORES["verde_borda"]};

    }}


    .status-vermelho {{

        background-color:
            {CORES["vermelho_fundo"]};

        color:
            {CORES["vermelho_texto"]};

        border:
            2px solid
            {CORES["vermelho_borda"]};

    }}


    .status-laranja {{

        background-color:
            {CORES["laranja_fundo"]};

        color:
            {CORES["laranja_texto"]};

        border:
            2px solid
            {CORES["laranja_borda"]};

    }}


    .status-cinza {{

        background-color:
            {CORES["cinza_fundo"]};

        color:
            {CORES["cinza_texto"]};

        border:
            2px solid
            {CORES["cinza_borda"]};

    }}


    .nome-card {{

        background-color:
            {CORES["card"]};

        border:
            1px solid
            {CORES["borda"]};

        border-radius:
            9px;

        color:
            {CORES["texto"]};

        text-align:
            center;

        font-size:
            20px;

        font-weight:
            900;

        padding:
            7px;

        margin-bottom:
            5px;

    }}


    .dados-card {{

        background-color:
            {CORES["card"]};

        border:
            1px solid
            {CORES["borda"]};

        border-radius:
            9px;

        color:
            {CORES["texto"]};

        text-align:
            center;

        font-size:
            13px;

        padding:
            7px;

        margin-bottom:
            5px;

    }}


    .dados-card strong {{

        color:
            {CORES["texto"]};

    }}


    .motivo-card {{

        background-color:
            {CORES["vermelho_fundo"]};

        border:
            2px solid
            {CORES["vermelho_borda"]};

        border-radius:
            10px;

        text-align:
            center;

        padding:
            10px;

        margin-top:
            5px;

    }}


    .motivo-titulo {{

        color:
            {CORES["vermelho_texto"]};

        font-size:
            12px;

        font-weight:
            900;

        margin-bottom:
            3px;

    }}


    .motivo-texto {{

        color:
            {CORES["vermelho_texto"]};

        font-size:
            19px;

        font-weight:
            900;

        line-height:
            1.2;

    }}


    .aguardando-card {{

        background-color:
            {CORES["laranja_fundo"]};

        border:
            2px solid
            {CORES["laranja_borda"]};

        color:
            {CORES["laranja_texto"]};

        border-radius:
            10px;

        text-align:
            center;

        font-size:
            17px;

        font-weight:
            900;

        padding:
            8px;

        margin:
            5px 0;

    }}


    div[data-testid="stMetric"] {{

        background-color:
            {CORES["card"]};

        border:
            1px solid
            {CORES["borda"]};

        border-radius:
            9px;

        padding:
            7px 10px;

    }}


    .stButton button,
    .stFormSubmitButton button,
    .stDownloadButton button {{

        border-radius:
            8px !important;

        font-weight:
            700 !important;

    }}


    .rodape {{

        text-align:
            center;

        color:
            {CORES["secundario"]};

        font-size:
            9px;

        margin-top:
            5px;

    }}

    </style>
    """
)


# ============================================================
# AJUDANTES DE REGRA DE NEGÓCIO
# ============================================================

def preencher_dados_colaborador(
    resultado_liberacao,
    colaborador,
):

    resultado_liberacao[
        "nome"
    ] = colaborador["nome"]

    resultado_liberacao[
        "matricula"
    ] = colaborador["matricula"]

    resultado_liberacao[
        "setor"
    ] = colaborador["setor"]

    return resultado_liberacao


def obter_motivo_perda(
    colaborador
):
    """
    Retorna exatamente o conteúdo válido da coluna Perde.
    """

    try:

        return texto_campo(
            colaborador["perde"]
        )

    except (
        KeyError,
        IndexError,
    ):

        return ""


def processar_colaborador(
    colaborador,
    tipo_identificacao,
    cracha_cadastrado=False,
):
    """
    Regra central para o fluxo após cadastro de crachá.

    A coluna Perde tem prioridade sobre a liberação.
    """

    perde = obter_motivo_perda(
        colaborador
    )

    # ========================================================
    # PERDEU A CESTA
    # ========================================================

    if perde:

        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            tipo_identificacao,
        )

        resultado_liberacao = (
            preencher_dados_colaborador(
                resultado_liberacao,
                colaborador,
            )
        )

        # ====================================================
        # GARANTIA:
        # MOSTRAR EXATAMENTE A COLUNA PERDE
        # ====================================================

        resultado_liberacao[
            "sucesso"
        ] = False

        resultado_liberacao[
            "resultado"
        ] = "NEGADO"

        resultado_liberacao[
            "perde"
        ] = perde

        resultado_liberacao[
            "motivo"
        ] = perde

        st.session_state.resultado_liberacao = (
            resultado_liberacao
        )

        st.session_state.aguardando_cracha = False

        st.session_state.colaborador_cracha_id = None

        st.session_state.matricula_cracha = None

        st.session_state.limpar_entrada = True

        return True


    # ========================================================
    # CRACHÁ RECÉM-CADASTRADO
    # ========================================================

    if cracha_cadastrado:

        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            tipo_identificacao,
        )

        resultado_liberacao = (
            preencher_dados_colaborador(
                resultado_liberacao,
                colaborador,
            )
        )

        resultado_liberacao[
            "cracha_cadastrado"
        ] = True

        st.session_state.resultado_liberacao = (
            resultado_liberacao
        )

        st.session_state.limpar_entrada = True

        return True


    return False


# ============================================================
# PROCESSAMENTO DA LEITURA
# ============================================================

def processar_identificacao():

    valor = str(
        st.session_state.get(
            "identificacao",
            "",
        )
    ).strip()


    if not valor:

        return


    timestamp = time.time()


    # ========================================================
    # PROTEÇÃO CONTRA DUPLA LEITURA
    # ========================================================

    if (
        valor
        == st.session_state.ultima_leitura
        and
        (
            timestamp
            - st.session_state.ultimo_timestamp
        ) < 2
    ):

        st.session_state.limpar_entrada = True

        return


    st.session_state.ultima_leitura = valor

    st.session_state.ultimo_timestamp = (
        timestamp
    )


    # ========================================================
    # CADASTRO DE CRACHÁ
    # ========================================================

    if st.session_state.aguardando_cracha:

        colaborador_id = (
            st.session_state.colaborador_cracha_id
        )

        cadastro = cadastrar_cracha(
            colaborador_id,
            valor,
        )


        if not cadastro["sucesso"]:

            st.session_state.resultado_liberacao = {

                "sucesso":
                    False,

                "resultado":
                    "ERRO_CRACHA",

                "motivo":
                    cadastro["motivo"],

            }

            st.session_state.limpar_entrada = True

            return


        st.session_state.aguardando_cracha = False

        st.session_state.colaborador_cracha_id = None

        st.session_state.matricula_cracha = None


        resultado = identificar(
            valor
        )


        if resultado["tipo"] != "COLABORADOR":

            st.session_state.resultado_liberacao = {

                "sucesso":
                    False,

                "resultado":
                    "ERRO",

                "motivo":
                    (
                        "Crachá cadastrado, "
                        "mas o colaborador "
                        "não foi localizado."
                    ),

            }

            st.session_state.limpar_entrada = True

            return


        colaborador = resultado["dados"]


        # ====================================================
        # MESMO APÓS CADASTRAR O CRACHÁ,
        # PERDE CONTINUA TENDO PRIORIDADE
        # ====================================================

        if processar_colaborador(

            colaborador,

            "ID CRACHÁ",

            cracha_cadastrado=True,

        ):

            return


    # ========================================================
    # IDENTIFICAÇÃO NORMAL
    # ========================================================

    resultado = identificar(
        valor
    )


    # ========================================================
    # COLABORADOR
    # ========================================================

    if resultado["tipo"] == "COLABORADOR":

        colaborador = resultado["dados"]


        # ====================================================
        # 1º - COLUNA PERDE
        #
        # ESTA VERIFICAÇÃO É FEITA ANTES
        # DO CADASTRO DE CRACHÁ E DA LIBERAÇÃO.
        # ====================================================

        perde = obter_motivo_perda(
            colaborador
        )


        if perde:

            resultado_liberacao = liberar_cesta(
                colaborador["id"],
                resultado[
                    "identificacao"
                ],
            )


            resultado_liberacao = (
                preencher_dados_colaborador(
                    resultado_liberacao,
                    colaborador,
                )
            )


            # =================================================
            # GARANTIR QUE O TEXTO DA TELA
            # SEJA EXATAMENTE O VALOR DE PERDE
            # =================================================

            resultado_liberacao[
                "sucesso"
            ] = False

            resultado_liberacao[
                "resultado"
            ] = "NEGADO"

            resultado_liberacao[
                "perde"
            ] = perde

            resultado_liberacao[
                "motivo"
            ] = perde


            st.session_state.resultado_liberacao = (
                resultado_liberacao
            )

            st.session_state.aguardando_cracha = False

            st.session_state.colaborador_cracha_id = None

            st.session_state.matricula_cracha = None

            st.session_state.limpar_entrada = True

            return


        # ====================================================
        # 2º - MATRÍCULA SEM CRACHÁ
        # ====================================================

        if (
            resultado["identificacao"]
            == "MATRÍCULA"

            and

            colaborador["id_mat"]
            is None
        ):

            st.session_state.aguardando_cracha = True

            st.session_state.colaborador_cracha_id = (
                colaborador["id"]
            )

            st.session_state.matricula_cracha = (
                colaborador["matricula"]
            )


            st.session_state.resultado_liberacao = {

                "sucesso":
                    False,

                "resultado":
                    "AGUARDANDO_CRACHA",

                "nome":
                    colaborador["nome"],

                "matricula":
                    colaborador["matricula"],

                "setor":
                    colaborador["setor"],

                "motivo":
                    "Colaborador sem crachá cadastrado.",

            }


            st.session_state.limpar_entrada = True

            return


        # ====================================================
        # 3º - LIBERAÇÃO NORMAL
        # ====================================================

        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            resultado["identificacao"],
        )


        resultado_liberacao = (
            preencher_dados_colaborador(
                resultado_liberacao,
                colaborador,
            )
        )


        st.session_state.resultado_liberacao = (
            resultado_liberacao
        )


    # ========================================================
    # DEMITIDO
    # ========================================================

    elif resultado["tipo"] == "DEMITIDO":

        demitido = resultado["dados"]


        st.session_state.resultado_liberacao = {

            "sucesso":
                False,

            "resultado":
                "DEMITIDO",

            "motivo":
                (
                    "Colaborador cadastrado "
                    "na lista de demitidos."
                ),

            "nome":
                demitido["nome"],

            "matricula":
                demitido["chapa"],

        }


    # ========================================================
    # NÃO ENCONTRADO
    # ========================================================

    elif resultado["tipo"] == "NAO_ENCONTRADO":

        registrar_tentativa_nao_encontrada(
            valor
        )


        st.session_state.resultado_liberacao = {

            "sucesso":
                False,

            "resultado":
                "NAO_ENCONTRADO",

            "motivo":
                (
                    "ID do crachá ou matrícula "
                    "não encontrado."
                ),

        }


    # ========================================================
    # ERRO
    # ========================================================

    else:

        st.session_state.resultado_liberacao = {

            "sucesso":
                False,

            "resultado":
                "ERRO",

            "motivo":
                resultado.get(
                    "resultado",
                    "Erro durante a identificação.",
                ),

        }


    st.session_state.limpar_entrada = True


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## 🥫 Cestas Básicas"
    )


    st.caption(
        f"👤 {st.session_state.nome_usuario}"
    )


    if eh_admin:

        st.caption(
            "🔴 Administrador"
        )

    else:

        st.caption(
            "🟢 Operador"
        )


    st.divider()


    # ========================================================
    # MENU
    # ========================================================

    if eh_admin:

        paginas = [

            "Terminal",

            "Dashboard",

            "Histórico",

            "Estoque",

            "Importação",

            "Usuários",

            "Relatórios",

        ]

    else:

        paginas = [

            "Terminal",

            "Dashboard",

        ]


    if st.session_state.pagina not in paginas:

        st.session_state.pagina = (
            "Terminal"
        )


    st.session_state.pagina = st.radio(

        "Menu",

        paginas,

        index=paginas.index(
            st.session_state.pagina
        ),

    )


    st.divider()


    # ========================================================
    # TEMA
    # ========================================================

    novo_tema = st.radio(

        "🎨 Tema",

        [
            "Claro",
            "Escuro",
        ],

        index=(
            0
            if st.session_state.tema
            == "Claro"
            else 1
        ),

    )


    if novo_tema != st.session_state.tema:

        st.session_state.tema = (
            novo_tema
        )

        st.rerun()


    st.divider()


    # ========================================================
    # LOGOUT
    # ========================================================

    if st.button(

        "🚪 Sair",

        use_container_width=True,

    ):

        st.session_state.logado = False

        st.session_state.usuario_id = None

        st.session_state.usuario = None

        st.session_state.nome_usuario = None

        st.session_state.perfil = None

        st.session_state.pagina = (
            "Terminal"
        )

        st.session_state.identificacao = ""

        st.session_state.resultado_liberacao = (
            None
        )

        st.session_state.aguardando_cracha = (
            False
        )

        st.session_state.colaborador_cracha_id = (
            None
        )

        st.session_state.matricula_cracha = (
            None
        )

        st.rerun()


# ============================================================
# TERMINAL
# ============================================================

def tela_terminal():

    # ========================================================
    # CABEÇALHO
    # ========================================================

    render_html(
        """
        <div class="titulo">
            🥫 ENTREGA DE CESTAS BÁSICAS
        </div>

        <div class="subtitulo">
            Terminal automático de distribuição
        </div>
        """
    )


    # ========================================================
    # ESTOQUE
    # ========================================================

    estoque = obter_estoque()


    normal = (
        estoque["cesta_normal"]
        if estoque
        else 0
    )


    especial = (
        estoque["cesta_especial"]
        if estoque
        else 0
    )


    col1, col2 = st.columns(
        2
    )


    with col1:

        render_html(
            f"""
            <div class="estoque-card">

                <div class="estoque-label">
                    🥫 CESTAS NORMAIS
                </div>

                <div class="estoque-numero">
                    {valor_seguro(normal)}
                </div>

            </div>
            """
        )


    with col2:

        render_html(
            f"""
            <div class="estoque-card">

                <div class="estoque-label">
                    ⭐ CESTAS ESPECIAIS
                </div>

                <div class="estoque-numero">
                    {valor_seguro(especial)}
                </div>

            </div>
            """
        )


    # ========================================================
    # AGUARDANDO CADASTRO DE CRACHÁ
    # ========================================================

    if st.session_state.aguardando_cracha:

        resultado_atual = (
            st.session_state.resultado_liberacao
            or {}
        )


        render_html(
            """
            <div class="aguardando-card">
                🟡 CADASTRO DE CRACHÁ NECESSÁRIO
            </div>
            """
        )


        render_html(
            f"""
            <div class="dados-card">

                👤
                <strong>
                    {valor_seguro(
                        resultado_atual.get(
                            "nome",
                            ""
                        )
                    )}
                </strong>

                &nbsp; • &nbsp;

                🆔 Matrícula:
                <strong>
                    {valor_seguro(
                        resultado_atual.get(
                            "matricula",
                            ""
                        )
                    )}
                </strong>

                &nbsp; • &nbsp;

                🪪 Aproxime o novo crachá

            </div>
            """
        )


    else:

        st.markdown(
            "### 🪪 Leitura do crachá"
        )


    # ========================================================
    # CAMPO DE LEITURA
    # ========================================================

    placeholder = (

        "Aproxime o crachá para cadastrar..."

        if st.session_state.aguardando_cracha

        else

        "Aproxime o crachá ou digite a matrícula..."

    )


    st.text_input(

        "ID do Crachá ou Matrícula",

        key="identificacao",

        placeholder=placeholder,

        on_change=processar_identificacao,

        label_visibility="collapsed",

    )


    # ========================================================
    # SISTEMA PRONTO
    # ========================================================

    if st.session_state.aguardando_cracha:

        render_html(
            """
            <div class="aguardando-card">
                🪪 AGUARDANDO LEITURA DO NOVO CRACHÁ
            </div>
            """
        )

    else:

        render_html(
            """
            <div class="pronto">
                🟢 SISTEMA PRONTO PARA A PRÓXIMA LEITURA
            </div>
            """
        )


    # ========================================================
    # RESULTADO
    # ========================================================

    resultado = (
        st.session_state.resultado_liberacao
    )


    if not resultado:

        return


    status_resultado = (
        resultado.get(
            "resultado",
            ""
        )
    )


    # ========================================================
    # AGUARDANDO CRACHÁ
    # ========================================================

    if (
        status_resultado
        == "AGUARDANDO_CRACHA"
    ):

        render_html(
            """
            <div class="status status-laranja">
                🟡 AGUARDANDO CADASTRO DO CRACHÁ
            </div>
            """
        )


        render_html(
            f"""
            <div class="nome-card">

                👤
                {valor_seguro(
                    resultado.get(
                        "nome",
                        ""
                    )
                )}

            </div>


            <div class="dados-card">

                🆔 Matrícula:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "matricula",
                            ""
                        )
                    )}
                </strong>

                &nbsp; • &nbsp;

                🏢 Setor:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "setor",
                            ""
                        )
                    )}
                </strong>

            </div>
            """
        )

        return


    # ========================================================
    # ERRO AO CADASTRAR CRACHÁ
    # ========================================================

    if (
        status_resultado
        == "ERRO_CRACHA"
    ):

        render_html(
            """
            <div class="status status-vermelho">
                🔴 CRACHÁ NÃO PODE SER CADASTRADO
            </div>
            """
        )


        st.error(
            resultado.get(
                "motivo",
                "Erro ao cadastrar o crachá.",
            )
        )

        return


    # ========================================================
    # LIBERADO
    # ========================================================

    if resultado.get(
        "sucesso"
    ):

        render_html(
            """
            <div class="status status-verde">
                🟢 CESTA LIBERADA
            </div>
            """
        )


        render_html(
            f"""
            <div class="nome-card">

                👤
                {valor_seguro(
                    resultado.get(
                        "nome",
                        ""
                    )
                )}

            </div>


            <div class="dados-card">

                🆔 Matrícula:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "matricula",
                            ""
                        )
                    )}
                </strong>

                &nbsp; • &nbsp;

                🏢 Setor:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "setor",
                            ""
                        )
                    )}
                </strong>

                &nbsp; • &nbsp;

                🕐

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "data_hora",
                            ""
                        )
                    )}
                </strong>

            </div>
            """
        )


        col1, col2 = st.columns(
            2
        )


        with col1:

            st.metric(
                "🥫 Cesta normal",
                resultado.get(
                    "cesta_normal",
                    0,
                ),
            )


        with col2:

            st.metric(
                "⭐ Cesta especial",
                resultado.get(
                    "cesta_especial",
                    0,
                ),
            )


        if resultado.get(
            "cracha_cadastrado"
        ):

            st.success(
                "🪪 Crachá cadastrado e "
                "cesta liberada automaticamente."
            )


        return


    # ========================================================
    # PERDEU A CESTA
    # ========================================================

    if (
        status_resultado
        == "NEGADO"
    ):

        render_html(
            """
            <div class="status status-vermelho">
                🔴 CESTA NÃO LIBERADA
            </div>
            """
        )


        render_html(
            f"""
            <div class="nome-card">

                👤
                {valor_seguro(
                    resultado.get(
                        "nome",
                        ""
                    )
                )}

            </div>


            <div class="dados-card">

                🆔 Matrícula:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "matricula",
                            ""
                        )
                    )}
                </strong>

                &nbsp; • &nbsp;

                🏢 Setor:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "setor",
                            ""
                        )
                    )}
                </strong>

            </div>
            """
        )


        # ====================================================
        # PRIORIDADE:
        # 1. resultado["perde"]
        # 2. resultado["motivo"]
        # ====================================================

        motivo = (

            texto_campo(
                resultado.get(
                    "perde"
                )
            )

            or

            texto_campo(
                resultado.get(
                    "motivo"
                )
            )

            or

            "Motivo não informado na coluna Perde."

        )


        render_html(
            f"""
            <div class="motivo-card">

                <div class="motivo-titulo">
                    ⚠️ MOTIVO DA PERDA DA CESTA
                </div>

                <div class="motivo-texto">
                    {valor_seguro(motivo)}
                </div>

            </div>
            """
        )


        return


    # ========================================================
    # RETIRADA DUPLICADA
    # ========================================================

    if (
        status_resultado
        == "DUPLICADO"
    ):

        render_html(
            """
            <div class="status status-laranja">
                🟠 RETIRADA JÁ REALIZADA
            </div>
            """
        )


        render_html(
            f"""
            <div class="nome-card">

                👤
                {valor_seguro(
                    resultado.get(
                        "nome",
                        ""
                    )
                )}

            </div>


            <div class="dados-card">

                🆔 Matrícula:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "matricula",
                            ""
                        )
                    )}
                </strong>

                &nbsp; • &nbsp;

                🏢 Setor:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "setor",
                            ""
                        )
                    )}
                </strong>

            </div>
            """
        )


        st.warning(
            resultado.get(
                "motivo",
                "Retirada já realizada.",
            )
        )


        return


    # ========================================================
    # ESTOQUE INSUFICIENTE
    # ========================================================

    if (
        status_resultado
        == "SEM_ESTOQUE"
    ):

        render_html(
            """
            <div class="status status-vermelho">
                🚫 ESTOQUE INSUFICIENTE
            </div>
            """
        )


        render_html(
            f"""
            <div class="nome-card">

                👤
                {valor_seguro(
                    resultado.get(
                        "nome",
                        ""
                    )
                )}

            </div>
            """
        )


        st.warning(
            resultado.get(
                "motivo",
                "Estoque insuficiente.",
            )
        )


        return


    # ========================================================
    # DEMITIDO
    # ========================================================

    if (
        status_resultado
        == "DEMITIDO"
    ):

        render_html(
            """
            <div class="status status-cinza">
                ⚫ COLABORADOR DEMITIDO
            </div>
            """
        )


        render_html(
            f"""
            <div class="nome-card">

                👤
                {valor_seguro(
                    resultado.get(
                        "nome",
                        ""
                    )
                )}

            </div>


            <div class="dados-card">

                🆔 Chapa:

                <strong>
                    {valor_seguro(
                        resultado.get(
                            "matricula",
                            ""
                        )
                    )}
                </strong>

            </div>
            """
        )


        st.warning(
            resultado.get(
                "motivo",
                "Colaborador desligado.",
            )
        )


        return


    # ========================================================
    # NÃO ENCONTRADO
    # ========================================================

    if (
        status_resultado
        == "NAO_ENCONTRADO"
    ):

        render_html(
            """
            <div class="status status-vermelho">
                ❌ COLABORADOR NÃO ENCONTRADO
            </div>
            """
        )


        st.error(
            resultado.get(
                "motivo",
                "Colaborador não encontrado.",
            )
        )


        return


    # ========================================================
    # ERRO GENÉRICO
    # ========================================================

    st.error(
        resultado.get(
            "motivo",
            "Erro desconhecido.",
        )
    )


# ============================================================
# DASHBOARD
# ============================================================

def tela_dashboard():

    st.title(
        "📊 Dashboard"
    )


    indicadores = (
        obter_indicadores()
    )


    estoque = (
        obter_estoque()
    )


    col1, col2, col3, col4 = (
        st.columns(4)
    )


    with col1:

        st.metric(
            "🟢 Liberadas",
            indicadores[
                "liberadas"
            ],
        )


    with col2:

        st.metric(
            "🔴 Negadas",
            indicadores[
                "negadas"
            ],
        )


    with col3:

        st.metric(
            "🟠 Duplicadas",
            indicadores[
                "duplicadas"
            ],
        )


    with col4:

        st.metric(
            "❌ Não encontradas",
            indicadores[
                "nao_encontradas"
            ],
        )


    st.divider()


    col1, col2, col3 = (
        st.columns(3)
    )


    with col1:

        st.metric(
            "🥫 Normais entregues",
            indicadores[
                "cestas_normais"
            ],
        )


    with col2:

        st.metric(
            "⭐ Especiais entregues",
            indicadores[
                "cestas_especiais"
            ],
        )


    with col3:

        st.metric(
            "📋 Total de tentativas",
            indicadores[
                "tentativas"
            ],
        )


    if estoque:

        st.divider()

        st.subheader(
            "📦 Estoque atual"
        )


        col1, col2 = st.columns(
            2
        )


        with col1:

            st.metric(
                "Cestas normais",
                estoque[
                    "cesta_normal"
                ],
            )


        with col2:

            st.metric(
                "Cestas especiais",
                estoque[
                    "cesta_especial"
                ],
            )


# ============================================================
# HISTÓRICO
# ============================================================

def tela_historico():

    st.title(
        "📜 Histórico de operações"
    )


    registros = obter_historico(
        limite=5000
    )


    if not registros:

        st.info(
            "Nenhuma operação registrada."
        )

        return


    dados = []


    for registro in registros:

        dados.append(
            {

                "Data/Hora":
                    registro[
                        "data_hora"
                    ],

                "Identificação":
                    registro[
                        "tipo_identificacao"
                    ],

                "Crachá":
                    registro[
                        "id_cracha"
                    ],

                "Matrícula":
                    registro[
                        "matricula"
                    ],

                "Nome":
                    registro[
                        "nome"
                    ],

                "Setor":
                    registro[
                        "setor"
                    ],

                "Cesta Normal":
                    registro[
                        "cesta_normal"
                    ],

                "Cesta Especial":
                    registro[
                        "cesta_especial"
                    ],

                "Resultado":
                    registro[
                        "resultado"
                    ],

                "Motivo":
                    registro[
                        "motivo"
                    ],

            }
        )


    df = pd.DataFrame(
        dados
    )


    col1, col2 = st.columns(
        2
    )


    with col1:

        filtro = st.text_input(

            "🔎 Buscar",

            placeholder=(
                "Nome, matrícula, "
                "crachá ou setor..."
            ),

        )


    with col2:

        opcoes = (

            ["TODOS"]

            +

            sorted(

                df[
                    "Resultado"
                ]
                .dropna()
                .unique()
                .tolist()

            )

        )


        filtro_resultado = (
            st.selectbox(
                "Resultado",
                opcoes,
            )
        )


    if filtro:

        mascara = (

            df.astype(str)

            .apply(

                lambda coluna:
                coluna.str.contains(

                    filtro,

                    case=False,

                    na=False,

                )

            )

            .any(
                axis=1
            )

        )


        df = df[
            mascara
        ]


    if (
        filtro_resultado
        != "TODOS"
    ):

        df = df[
            df["Resultado"]
            == filtro_resultado
        ]


    st.caption(
        f"{len(df)} "
        "registro(s) encontrado(s)."
    )


    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# ESTOQUE
# ============================================================

def tela_estoque():

    st.title(
        "📦 Controle de estoque"
    )


    estoque = obter_estoque()


    atual_normal = int(
        estoque[
            "cesta_normal"
        ]
    )


    atual_especial = int(
        estoque[
            "cesta_especial"
        ]
    )


    col1, col2 = st.columns(
        2
    )


    with col1:

        st.metric(
            "🥫 Cestas normais",
            atual_normal,
        )


        nova_normal = (
            st.number_input(

                "Nova quantidade",

                min_value=0,

                step=1,

                value=atual_normal,

                key=(
                    "estoque_normal_admin"
                ),

            )
        )


    with col2:

        st.metric(
            "⭐ Cestas especiais",
            atual_especial,
        )


        nova_especial = (
            st.number_input(

                "Nova quantidade",

                min_value=0,

                step=1,

                value=atual_especial,

                key=(
                    "estoque_especial_admin"
                ),

            )
        )


    if st.button(

        "💾 Atualizar estoque",

        type="primary",

        use_container_width=True,

    ):

        configurar_estoque(
            nova_normal,
            nova_especial,
        )


        st.success(
            "Estoque atualizado."
        )


        st.rerun()


# ============================================================
# IMPORTAÇÃO
# ============================================================

def tela_importacao():

    st.title(
        "📥 Importação de planilha"
    )


    st.info(
        'A planilha deve conter as abas '
        '"BANCO DE DADOS" e '
        '"Cesta demitidos".'
    )


    arquivo = st.file_uploader(

        "Selecione o arquivo Excel",

        type=[
            "xlsx"
        ],

    )


    if arquivo is None:

        return


    if st.button(

        "📥 Importar dados",

        type="primary",

        use_container_width=True,

    ):

        with st.spinner(
            "Processando planilha..."
        ):

            resultado = (
                importar_excel(
                    arquivo
                )
            )


        if resultado["erros"]:

            st.error(
                "A importação encontrou problemas."
            )


            for erro in resultado[
                "erros"
            ]:

                st.warning(
                    erro
                )


        else:

            st.success(
                "Importação concluída!"
            )


            col1, col2 = (
                st.columns(2)
            )


            with col1:

                st.metric(

                    "Colaboradores",

                    resultado[
                        "colaboradores"
                    ],

                )


            with col2:

                st.metric(

                    "Demitidos",

                    resultado[
                        "demitidos"
                    ],

                )


# ============================================================
# USUÁRIOS
# ============================================================

def tela_usuarios():

    st.title(
        "👥 Gerenciamento de usuários"
    )


    st.subheader(
        "➕ Criar usuário"
    )


    with st.form(
        "form_novo_usuario"
    ):

        col1, col2 = (
            st.columns(2)
        )


        with col1:

            usuario = (
                st.text_input(
                    "Usuário"
                )
            )


            nome = (
                st.text_input(
                    "Nome"
                )
            )


        with col2:

            senha = st.text_input(

                "Senha",

                type="password",

            )


            perfil = (
                st.selectbox(

                    "Perfil",

                    [
                        "OPERADOR",
                        "ADMIN",
                    ],

                )
            )


        criar = (
            st.form_submit_button(

                "Criar usuário",

                type="primary",

                use_container_width=True,

            )
        )


        if criar:

            try:

                criar_usuario(
                    usuario,
                    nome,
                    senha,
                    perfil,
                )


                st.success(
                    "Usuário criado."
                )


                st.rerun()


            except Exception as erro:

                st.error(
                    str(erro)
                )


    st.divider()


    st.subheader(
        "👤 Usuários cadastrados"
    )


    usuarios = (
        listar_usuarios()
    )


    for usuario in usuarios:

        col1, col2, col3, col4 = (
            st.columns(
                [
                    2,
                    3,
                    2,
                    2,
                ]
            )
        )


        with col1:

            st.write(
                f"**{usuario['usuario']}**"
            )


        with col2:

            st.write(
                usuario["nome"]
            )


        with col3:

            st.write(
                usuario["perfil"]
            )


        with col4:

            if usuario["ativo"]:

                if st.button(

                    "🔴 Desativar",

                    key=(
                        f"desativar_"
                        f"{usuario['id']}"
                    ),

                ):

                    alterar_status_usuario(
                        usuario["id"],
                        False,
                    )


                    st.rerun()


            else:

                if st.button(

                    "🟢 Ativar",

                    key=(
                        f"ativar_"
                        f"{usuario['id']}"
                    ),

                ):

                    alterar_status_usuario(
                        usuario["id"],
                        True,
                    )


                    st.rerun()


    st.divider()


    st.subheader(
        "🔑 Alterar senha"
    )


    usuarios_ativos = [

        usuario

        for usuario in usuarios

        if usuario["ativo"]

    ]


    if usuarios_ativos:

        opcoes = {

            usuario["id"]:

            (
                f"{usuario['nome']} "
                f"({usuario['usuario']})"
            )

            for usuario
            in usuarios_ativos

        }


        usuario_senha = (
            st.selectbox(

                "Usuário",

                list(
                    opcoes.keys()
                ),

                format_func=
                    lambda x:
                    opcoes[x],

            )
        )


        nova_senha = (
            st.text_input(

                "Nova senha",

                type="password",

                key=(
                    "nova_senha_admin"
                ),

            )
        )


        if st.button(

            "🔑 Alterar senha",

            use_container_width=True,

        ):

            try:

                alterar_senha_usuario(
                    usuario_senha,
                    nova_senha,
                )


                st.success(
                    "Senha alterada."
                )


            except Exception as erro:

                st.error(
                    str(erro)
                )


# ============================================================
# RELATÓRIOS
# ============================================================

def tela_relatorios():

    st.title(
        "📑 Relatórios"
    )


    registros = obter_historico(
        limite=10000
    )


    if not registros:

        st.info(
            "Nenhum dado disponível."
        )

        return


    dados = []


    for registro in registros:

        dados.append(
            {

                "Data/Hora":
                    registro[
                        "data_hora"
                    ],

                "Matrícula":
                    registro[
                        "matricula"
                    ],

                "Crachá":
                    registro[
                        "id_cracha"
                    ],

                "Nome":
                    registro[
                        "nome"
                    ],

                "Setor":
                    registro[
                        "setor"
                    ],

                "Cesta Normal":
                    registro[
                        "cesta_normal"
                    ],

                "Cesta Especial":
                    registro[
                        "cesta_especial"
                    ],

                "Resultado":
                    registro[
                        "resultado"
                    ],

                "Motivo":
                    registro[
                        "motivo"
                    ],

            }
        )


    df = pd.DataFrame(
        dados
    )


    retiradas = df[
        df["Resultado"]
        == "LIBERADO"
    ].copy()


    st.metric(
        "👥 Pessoas que retiraram",
        len(
            retiradas
        ),
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


    st.download_button(

        "⬇️ Exportar retiradas",

        data=csv,

        file_name=(
            "relatorio_retiradas.csv"
        ),

        mime="text/csv",

        use_container_width=True,

    )


# ============================================================
# ROTEAMENTO
# ============================================================

pagina = (
    st.session_state.pagina
)


if pagina == "Terminal":

    tela_terminal()


elif pagina == "Dashboard":

    tela_dashboard()


elif (
    pagina == "Histórico"
    and eh_admin
):

    tela_historico()


elif (
    pagina == "Estoque"
    and eh_admin
):

    tela_estoque()


elif (
    pagina == "Importação"
    and eh_admin
):

    tela_importacao()


elif (
    pagina == "Usuários"
    and eh_admin
):

    tela_usuarios()


elif (
    pagina == "Relatórios"
    and eh_admin
):

    tela_relatorios()


else:

    st.session_state.pagina = (
        "Terminal"
    )

    st.rerun()


# ============================================================
# RODAPÉ
# ============================================================

render_html(
    """
    <div class="rodape">
        Sistema de Entrega de Cestas Básicas •
        Controle de distribuição
    </div>
    """
)