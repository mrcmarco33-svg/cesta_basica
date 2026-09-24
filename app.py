import time
from io import BytesIO

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
    obter_status_entrega,
    finalizar_entrega,
    reabrir_entrega,
    obter_consulta_retiradas,
    obter_resumo_consulta,
    iniciar_nova_entrega,
    obter_periodo_ativo,
    listar_periodos,
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

# ============================================================
# PERÍODOS
# ============================================================

def selecionar_periodo(prefixo, label="📅 Período"):
    periodos = listar_periodos()

    if not periodos:
        st.warning("Nenhum período encontrado.")
        return None

    periodo_ativo = obter_periodo_ativo()
    periodo_ativo_id = periodo_ativo.get("id")

    opcoes = {
        periodo["id"]: periodo
        for periodo in periodos
    }

    ids = list(opcoes.keys())

    indice_padrao = 0

    if periodo_ativo_id in ids:
        indice_padrao = ids.index(periodo_ativo_id)

    def formatar_periodo(periodo_id):
        periodo = opcoes[periodo_id]

        nome = periodo.get("nome", f"Período {periodo_id}")
        status = periodo.get("status", "")
        ativo = periodo.get("ativo", False)

        marcador = "🟢 Ativo" if ativo else "⚪ Antigo"

        return f"{nome} — {status} — {marcador}"

    periodo_id_selecionado = st.selectbox(
        label,
        ids,
        index=indice_padrao,
        format_func=formatar_periodo,
        key=f"{prefixo}_periodo_id",
    )

    return opcoes[periodo_id_selecionado]

for chave, valor in valores_iniciais.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


# ============================================================
# ESTILO VISUAL
# ============================================================

def aplicar_estilo():
    if st.session_state.tema == "Escuro":
        fundo = "#0f172a"
        texto = "#f8fafc"
        card = "#1e293b"
        borda = "#334155"
        input_bg = "#1e293b"
    else:
        fundo = "#f5f7fa"
        texto = "#101828"
        card = "#ffffff"
        borda = "#d0d5dd"
        input_bg = "#ffffff"

    st.markdown(
        f"""
<style>
.stApp {{
    background-color: {fundo};
    color: {texto};
}}

header[data-testid="stHeader"] {{
    background-color: {fundo} !important;
    box-shadow: none !important;
}}

div[data-testid="stDecoration"] {{
    display: none !important;
}}

.block-container {{
    padding-top: 2.2rem !important;
    padding-bottom: 1rem;
    max-width: 1500px;
}}

section[data-testid="stSidebar"] {{
    background-color: {card};
    border-right: 1px solid {borda};
}}

h1, h2, h3, h4, h5, h6, p, label, span {{
    color: {texto} !important;
}}

div[data-testid="stTextInput"] input {{
    min-height: 54px;
    font-size: 20px;
    font-weight: 700;
    text-align: center;
    border-radius: 10px;
    background-color: {input_bg};
    color: {texto};
    border: 1px solid {borda};
}}

div[data-testid="stMetric"] {{
    background-color: {card};
    border: 1px solid {borda};
    padding: 14px;
    border-radius: 12px;
}}

.stButton button {{
    border-radius: 10px;
    font-weight: 700;
}}

div[data-testid="stForm"] {{
    border: 1px solid {borda};
    border-radius: 12px;
    padding: 20px;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


aplicar_estilo()


# ============================================================
# LOGIN
# ============================================================

def tela_login():
    col_esq, col_centro, col_dir = st.columns([1, 2, 1])

    with col_centro:
        st.title("🥫 Cestas Básicas")
        st.caption("Sistema de controle de distribuição")

        with st.form("form_login"):
            usuario = st.text_input(
                "Usuário",
                placeholder="Digite o usuário",
                key="login_usuario",
            )

            senha = st.text_input(
                "Senha",
                type="password",
                placeholder="Digite a senha",
                key="login_senha",
            )

            entrar = st.form_submit_button(
                "🔐 Entrar",
                type="primary",
                use_container_width=True,
            )

            if entrar:
                registro = autenticar(
                    usuario,
                    senha,
                )

                if registro is None:
                    st.error("Usuário ou senha inválidos.")
                else:
                    st.session_state.logado = True
                    st.session_state.usuario_id = registro["id"]
                    st.session_state.usuario = registro["usuario"]
                    st.session_state.nome_usuario = registro["nome"]
                    st.session_state.perfil = registro["perfil"]
                    st.session_state.pagina = "Terminal"
                    st.session_state.resultado_liberacao = None
                    st.session_state.identificacao = ""
                    st.rerun()


if not st.session_state.logado:
    tela_login()
    st.stop()


# ============================================================
# PERFIL
# ============================================================

eh_admin = st.session_state.perfil == "ADMIN"


# ============================================================
# LIMPAR ENTRADA
# ============================================================

if st.session_state.limpar_entrada:
    st.session_state.identificacao = ""
    st.session_state.limpar_entrada = False


# ============================================================
# PROCESSAR IDENTIFICAÇÃO
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

    if (
        valor == st.session_state.ultima_leitura
        and timestamp - st.session_state.ultimo_timestamp < 2
    ):
        st.session_state.limpar_entrada = True
        return

    st.session_state.ultima_leitura = valor
    st.session_state.ultimo_timestamp = timestamp

    # ========================================================
    # MODO CADASTRO DE CRACHÁ
    # ========================================================

    if st.session_state.aguardando_cracha:
        colaborador_id = st.session_state.colaborador_cracha_id

        cadastro = cadastrar_cracha(
            colaborador_id,
            valor,
        )

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

        resultado = identificar(
            valor
        )

        if resultado["tipo"] != "COLABORADOR":
            st.session_state.resultado_liberacao = {
                "sucesso": False,
                "resultado": "ERRO",
                "motivo": (
                    "O crachá foi cadastrado, "
                    "mas o colaborador não foi localizado."
                ),
            }

            st.session_state.limpar_entrada = True
            return

        colaborador = resultado["dados"]

        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            "ID CRACHÁ",
        )

        resultado_liberacao["nome"] = colaborador["nome"]
        resultado_liberacao["matricula"] = colaborador["matricula"]
        resultado_liberacao["setor"] = colaborador["setor"]
        resultado_liberacao["cracha_cadastrado"] = True

        st.session_state.resultado_liberacao = resultado_liberacao
        st.session_state.limpar_entrada = True
        return

    # ========================================================
    # IDENTIFICAÇÃO NORMAL
    # ========================================================

    resultado = identificar(
        valor
    )

    if resultado["tipo"] == "COLABORADOR":
        colaborador = resultado["dados"]

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

        resultado_liberacao = liberar_cesta(
            colaborador["id"],
            resultado["identificacao"],
        )

        resultado_liberacao["nome"] = colaborador["nome"]
        resultado_liberacao["matricula"] = colaborador["matricula"]
        resultado_liberacao["setor"] = colaborador["setor"]

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
        registrar_tentativa_nao_encontrada(
            valor
        )

        st.session_state.resultado_liberacao = {
            "sucesso": False,
            "resultado": "NAO_ENCONTRADO",
            "motivo": "ID do crachá ou matrícula não encontrado.",
        }

    else:
        st.session_state.resultado_liberacao = {
            "sucesso": False,
            "resultado": "ERRO",
            "motivo": resultado.get(
                "resultado",
                "Erro durante a identificação.",
            ),
        }

    st.session_state.limpar_entrada = True


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.title("🥫 Cestas Básicas")

    st.caption(f"👤 {st.session_state.nome_usuario}")

    if eh_admin:
        st.caption("🔴 Administrador")
    else:
        st.caption("🟢 Operador")
    try:
        periodo_ativo = obter_periodo_ativo()

        st.caption(
            f"📅 Período ativo: {periodo_ativo.get('nome', '-')}"
        )
    except Exception:
        st.caption("📅 Período ativo: não carregado")
    st.divider()

    if eh_admin:
        paginas = [
    "Terminal",
    "Dashboard",
    "Consulta",
    "Histórico",
    "Estoque",
    "Importação",
    "Usuários",
    "Relatórios",
]
        
    else:
        paginas = paginas = [
    "Terminal",
    "Dashboard",
    "Consulta",
]

    if st.session_state.pagina not in paginas:
        st.session_state.pagina = "Terminal"

    pagina_escolhida = st.radio(
        "Menu",
        paginas,
        index=paginas.index(
            st.session_state.pagina
        ),
        key="menu_principal",
    )

    st.session_state.pagina = pagina_escolhida

    st.divider()

    tema_novo = st.radio(
        "🎨 Tema",
        [
            "Claro",
            "Escuro",
        ],
        index=0 if st.session_state.tema == "Claro" else 1,
        key="tema_sistema",
    )

    if tema_novo != st.session_state.tema:
        st.session_state.tema = tema_novo
        st.rerun()

    st.divider()

    if st.button(
        "🚪 Sair",
        use_container_width=True,
        key="botao_sair",
    ):
        st.session_state.logado = False
        st.session_state.usuario_id = None
        st.session_state.usuario = None
        st.session_state.nome_usuario = None
        st.session_state.perfil = None
        st.session_state.pagina = "Terminal"
        st.session_state.identificacao = ""
        st.session_state.resultado_liberacao = None
        st.session_state.aguardando_cracha = False
        st.session_state.colaborador_cracha_id = None
        st.session_state.matricula_cracha = None
        st.rerun()


# ============================================================
# TERMINAL
# ============================================================

def tela_terminal():
    st.title("🥫 ENTREGA DE CESTAS BÁSICAS")
    st.caption("Terminal automático de distribuição")
        
    periodo_ativo = obter_periodo_ativo()

    st.info(
        f"📅 Período ativo: **{periodo_ativo.get('nome', '-')}**"
    )
    status_entrega = obter_status_entrega()

    if str(status_entrega.get("status", "")).upper() == "FINALIZADA":
        st.error("🔴 Entrega finalizada")
        st.warning(
            "O terminal está bloqueado para novas retiradas. "
            "Acesse a tela Consulta para verificar pendências."
        )

        if status_entrega.get("data_finalizacao"):
            st.info(
                f"Finalizada em: {status_entrega.get('data_finalizacao')}"
            )

        return
    estoque = obter_estoque()

    normal = estoque["cesta_normal"] if estoque else 0
    especial = estoque["cesta_especial"] if estoque else 0

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "🥫 Cestas normais disponíveis",
            normal,
        )

    with col2:
        st.metric(
            "⭐ Cestas especiais disponíveis",
            especial,
        )

    st.divider()

    if st.session_state.aguardando_cracha:
        resultado_atual = st.session_state.resultado_liberacao or {}

        st.warning("🟡 Cadastro de crachá necessário")

        st.info(
            f"👤 **{resultado_atual.get('nome', '')}**  \n"
            f"🆔 Matrícula: **{resultado_atual.get('matricula', '')}**  \n\n"
            "🪪 Aproxime o crachá para cadastrá-lo."
        )
    else:
        st.subheader("🪪 Leitura do crachá")

    placeholder = (
        "Aproxime o crachá para cadastrar..."
        if st.session_state.aguardando_cracha
        else "Aproxime o crachá ou digite a matrícula..."
    )

    st.text_input(
        "ID do Crachá ou Matrícula",
        key="identificacao",
        placeholder=placeholder,
        on_change=processar_identificacao,
        label_visibility="collapsed",
    )

    if st.session_state.aguardando_cracha:
        st.warning("🪪 Aguardando leitura do crachá")
    else:
        st.success("🟢 Sistema pronto para a próxima leitura")

    resultado = st.session_state.resultado_liberacao

    if not resultado:
        return

    st.divider()
    st.subheader("📋 Última operação")

    if resultado["resultado"] == "AGUARDANDO_CRACHA":
        st.warning("🟡 Aguardando cadastro do crachá")
        st.write(f"👤 **{resultado.get('nome', '')}**")
        st.write(f"🆔 Matrícula: **{resultado.get('matricula', '')}**")
        st.write(f"🏢 Setor: **{resultado.get('setor', '')}**")
        return

    if resultado["resultado"] == "ERRO_CRACHA":
        st.error("🔴 Crachá não pode ser cadastrado")
        st.error(resultado["motivo"])
        return

    if resultado["sucesso"]:
        st.success("🟢 CESTA LIBERADA")

        st.write(f"## 👤 {resultado.get('nome', '')}")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.write("**Matrícula**")
            st.write(resultado.get("matricula", ""))

        with col2:
            st.write("**Setor**")
            st.write(resultado.get("setor", ""))

        with col3:
            st.write("**Data/Hora**")
            st.write(resultado.get("data_hora", ""))

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "🥫 Cesta normal",
                resultado.get("cesta_normal", 0),
            )

        with col2:
            st.metric(
                "⭐ Cesta especial",
                resultado.get("cesta_especial", 0),
            )

        if resultado.get("cracha_cadastrado"):
            st.success("🪪 Crachá cadastrado e cesta liberada automaticamente.")
        else:
            st.success("Retirada registrada automaticamente.")

        return

    if resultado["resultado"] == "DUPLICADO":
        st.warning("🟠 RETIRADA JÁ REALIZADA")
        st.write(f"## 👤 {resultado.get('nome', '')}")
        st.warning(resultado["motivo"])
        return

    if resultado["resultado"] == "NEGADO":
        st.error("🔴 RETIRADA NÃO AUTORIZADA")
        if resultado.get("nome"):
            st.write(f"## 👤 {resultado.get('nome')}")
        st.error(resultado["motivo"])
        return

    if resultado["resultado"] == "SEM_ESTOQUE":
        st.error("🚫 ESTOQUE INSUFICIENTE")
        if resultado.get("nome"):
            st.write(f"## 👤 {resultado.get('nome')}")
        st.warning(resultado["motivo"])
        return

    if resultado["resultado"] == "DEMITIDO":
        st.error("⚫ COLABORADOR DEMITIDO")
        st.write(f"## 👤 {resultado.get('nome', '')}")
        st.error(resultado["motivo"])
        return

    if resultado["resultado"] == "NAO_ENCONTRADO":
        st.error("❌ NÃO ENCONTRADO")
        st.error(resultado["motivo"])
        return

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
    st.title("📊 Dashboard")

    indicadores = obter_indicadores()
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
        st.metric("🥫 Cestas normais entregues", indicadores["cestas_normais"])

    with col2:
        st.metric("⭐ Cestas especiais entregues", indicadores["cestas_especiais"])

    with col3:
        st.metric("📋 Total de tentativas", indicadores["tentativas"])

    st.divider()

    if estoque:
        st.subheader("📦 Estoque atual")

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Cestas normais", estoque["cesta_normal"])

        with col2:
            st.metric("Cestas especiais", estoque["cesta_especial"])

# ============================================================
# CONSULTA DE RETIRADAS
# ============================================================

def tela_consulta():
    st.title("🔎 Consulta de retiradas")

    periodo_selecionado = selecionar_periodo(
        "consulta",
        label="📅 Selecione o período para consulta",
    )

    if not periodo_selecionado:
        return

    periodo_id = periodo_selecionado["id"]

    periodo_ativo = obter_periodo_ativo()
    periodo_ativo_id = periodo_ativo.get("id")

    status_atual = str(
        periodo_selecionado.get("status", "ABERTA")
    ).upper()

    st.info(
        f"Período selecionado: **{periodo_selecionado.get('nome', '-')}**"
    )

    if periodo_id != periodo_ativo_id:
        st.warning(
            "Você está consultando um período antigo. "
            "As ações de finalizar, reabrir e criar novo período sempre se aplicam ao período ativo."
        )

    if status_atual == "FINALIZADA":
        st.error("🔴 Entrega finalizada neste período")

        st.caption(
            f"Finalizada em: {periodo_selecionado.get('data_finalizacao') or '-'}"
        )

        if periodo_selecionado.get("usuario_finalizacao"):
            st.caption(
                f"Finalizada por: {periodo_selecionado.get('usuario_finalizacao')}"
            )

        if periodo_selecionado.get("observacao"):
            st.info(
                periodo_selecionado.get("observacao")
            )
    else:
        st.success("🟢 Entrega aberta neste período")

    resumo = obter_resumo_consulta(
        periodo_id=periodo_id
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "👥 Autorizados",
            resumo["autorizados"],
        )

    with col2:
        st.metric(
            "⏳ Faltam retirar",
            resumo["pendentes"],
        )

    with col3:
        st.metric(
            "✅ Já retiraram",
            resumo["retirados"],
        )

    with col4:
        st.metric(
            "🚫 Não autorizados",
            resumo["nao_autorizados"],
        )

    st.divider()

    col1, col2 = st.columns([2, 3])

    with col1:
        opcao = st.selectbox(
            "Situação",
            [
                "Faltam retirar",
                "Já retiraram",
                "Não autorizados",
                "Todos",
            ],
            key="consulta_situacao",
        )

    with col2:
        busca = st.text_input(
            "Buscar",
            placeholder="Nome, matrícula, crachá ou setor...",
            key="consulta_busca",
        )

    mapa_situacao = {
        "Faltam retirar": "PENDENTES",
        "Já retiraram": "RETIRADOS",
        "Não autorizados": "NAO_AUTORIZADOS",
        "Todos": "TODOS",
    }

    registros = obter_consulta_retiradas(
        situacao=mapa_situacao[opcao],
        busca=busca,
        periodo_id=periodo_id,
    )

    dados = []

    for registro in registros:
        dados.append(
            {
                "Período": periodo_selecionado.get("nome"),
                "Situação": registro.get("situacao"),
                "Matrícula": registro.get("matricula"),
                "Crachá": registro.get("id_mat"),
                "Nome": registro.get("nome"),
                "Setor": registro.get("setor"),
                "Cesta Normal": registro.get("cesta_normal"),
                "Cesta Especial": registro.get("cesta_especial"),
                "Retirou": registro.get("confirmacao_retirada"),
                "Data/Hora Retirada": registro.get("data_hora_retirada"),
                "Perde": registro.get("perde"),
            }
        )

    df = pd.DataFrame(
        dados
    )

    st.caption(
        f"{len(df)} registro(s) encontrado(s)."
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    arquivo_excel = gerar_excel_relatorio(
        df
    )

    st.download_button(
        "⬇️ Exportar consulta em Excel",
        data=arquivo_excel,
        file_name=f"consulta_retiradas_{periodo_selecionado.get('nome', 'periodo')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="download_consulta_retiradas_excel",
    )

    csv = df.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )

    st.download_button(
        "⬇️ Exportar consulta em CSV",
        data=csv,
        file_name=f"consulta_retiradas_{periodo_selecionado.get('nome', 'periodo')}.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_consulta_retiradas_csv",
    )

    if eh_admin:
        st.divider()
        st.subheader("🔒 Controle do período ativo")

        status_ativo = str(
            periodo_ativo.get("status", "ABERTA")
        ).upper()

        st.info(
            f"Período ativo atual: **{periodo_ativo.get('nome', '-')}**"
        )

        if status_ativo != "FINALIZADA":
            st.warning(
                "Ao finalizar a entrega, o terminal ficará bloqueado "
                "para novas retiradas no período ativo."
            )

            observacao = st.text_area(
                "Observação da finalização",
                placeholder="Exemplo: entrega encerrada no final do turno.",
                key="observacao_finalizacao",
            )

            confirmar = st.checkbox(
                "Confirmo que desejo finalizar a entrega do período ativo.",
                key="confirmar_finalizacao_entrega",
            )

            if st.button(
                "🔴 Finalizar entrega",
                type="primary",
                use_container_width=True,
                disabled=not confirmar,
                key="botao_finalizar_entrega",
            ):
                finalizar_entrega(
                    usuario=st.session_state.usuario,
                    observacao=observacao,
                )

                st.success("Entrega finalizada.")
                st.rerun()

        else:
            st.warning(
                "A entrega do período ativo está finalizada. "
                "Reabrir permitirá novas retiradas nesse período."
            )

            if st.button(
                "🟢 Reabrir entrega",
                use_container_width=True,
                key="botao_reabrir_entrega",
            ):
                reabrir_entrega(
                    usuario=st.session_state.usuario,
                )

                st.success("Entrega reaberta.")
                st.rerun()

        st.divider()
        st.subheader("🆕 Novo período de entrega")

        st.warning(
            "Essa ação cria um novo período ativo. "
            "O período atual será arquivado/finalizado e os dados antigos continuarão disponíveis para consulta."
        )

        nome_novo_periodo = st.text_input(
            "Nome do novo período",
            placeholder="Exemplo: Outubro/2026 ou Entrega Outubro 2026",
            key="nome_novo_periodo",
        )

        observacao_nova_entrega = st.text_area(
            "Observação do novo período",
            placeholder="Exemplo: Entrega referente ao mês de outubro.",
            key="observacao_nova_entrega",
        )

        zerar_estoque_nova_entrega = st.checkbox(
            "Zerar estoque ao iniciar novo período",
            value=True,
            key="zerar_estoque_nova_entrega",
        )

        confirmar_nova_entrega = st.checkbox(
            "Confirmo que desejo criar um novo período de entrega.",
            key="confirmar_nova_entrega",
        )

        if st.button(
            "🆕 Criar novo período",
            type="primary",
            use_container_width=True,
            disabled=not confirmar_nova_entrega,
            key="botao_iniciar_nova_entrega",
        ):
            if not nome_novo_periodo.strip():
                st.error("Informe o nome do novo período.")
            else:
                iniciar_nova_entrega(
                    usuario=st.session_state.usuario,
                    observacao=observacao_nova_entrega,
                    zerar_estoque=zerar_estoque_nova_entrega,
                    nome=nome_novo_periodo,
                )

                st.success("Novo período criado com sucesso.")
                st.rerun()

# ============================================================
# HISTÓRICO
# ============================================================

def tela_historico():
    st.title("📜 Histórico de operações")

    periodo_selecionado = selecionar_periodo(
        "historico",
        label="📅 Selecione o período do histórico",
    )

    if not periodo_selecionado:
        return

    periodo_id = periodo_selecionado["id"]

    st.info(
        f"Histórico do período: **{periodo_selecionado.get('nome', '-')}**"
    )

    registros = obter_historico(
        limite=5000,
        periodo_id=periodo_id,
    )

    if not registros:
        st.info("Nenhuma operação registrada neste período.")
        return

    dados = []

    for registro in registros:
        dados.append(
            {
                "Período": periodo_selecionado.get("nome"),
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
            placeholder="Nome, matrícula, crachá ou setor...",
            key="historico_busca",
        )

    with col2:
        opcoes = ["TODOS"] + sorted(
            df["Resultado"].dropna().unique().tolist()
        )

        filtro_resultado = st.selectbox(
            "Resultado",
            opcoes,
            key="historico_resultado",
        )

    if filtro:
        mascara = (
            df.astype(str)
            .apply(
                lambda coluna: coluna.str.contains(
                    filtro,
                    case=False,
                    na=False,
                )
            )
            .any(axis=1)
        )

        df = df[mascara]

    if filtro_resultado != "TODOS":
        df = df[
            df["Resultado"] == filtro_resultado
        ]

    st.caption(f"{len(df)} registro(s) encontrado(s).")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    arquivo_excel = gerar_excel_relatorio(
        df
    )

    st.download_button(
        "⬇️ Exportar histórico em Excel",
        data=arquivo_excel,
        file_name=f"historico_{periodo_selecionado.get('nome', 'periodo')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="download_historico_excel",
    )


# ============================================================
# ESTOQUE
# ============================================================

def tela_estoque():
    st.title("📦 Controle de estoque")

    estoque = obter_estoque()

    atual_normal = int(
        estoque["cesta_normal"]
    )

    atual_especial = int(
        estoque["cesta_especial"]
    )

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "🥫 Cestas normais",
            atual_normal,
        )

        nova_normal = st.number_input(
            "Nova quantidade de cestas normais",
            min_value=0,
            step=1,
            value=atual_normal,
            key="estoque_nova_normal",
        )

    with col2:
        st.metric(
            "⭐ Cestas especiais",
            atual_especial,
        )

        nova_especial = st.number_input(
            "Nova quantidade de cestas especiais",
            min_value=0,
            step=1,
            value=atual_especial,
            key="estoque_nova_especial",
        )

    if st.button(
        "💾 Atualizar estoque",
        type="primary",
        use_container_width=True,
        key="botao_atualizar_estoque",
    ):
        configurar_estoque(
            nova_normal,
            nova_especial,
        )

        st.success("Estoque atualizado.")
        st.rerun()


# ============================================================
# IMPORTAÇÃO
# ============================================================

def tela_importacao():
    st.title("📥 Importação de planilha")

    periodo_ativo = obter_periodo_ativo()

    st.success(
        f"📅 Os dados importados serão vinculados ao período ativo: "
        f"**{periodo_ativo.get('nome', '-')}**"
    )

    st.info(
        'A planilha deve conter as abas '
        '"BANCO DE DADOS" e "Cesta demitidos".'
    )

    arquivo = st.file_uploader(
        "Selecione o arquivo Excel",
        type=["xlsx"],
        key="upload_planilha",
    )

    if arquivo is None:
        return

    if st.button(
        "📥 Importar dados",
        type="primary",
        use_container_width=True,
        key="botao_importar_planilha",
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
                st.metric("Colaboradores", resultado["colaboradores"])

            with col2:
                st.metric("Demitidos", resultado["demitidos"])


# ============================================================
# USUÁRIOS
# ============================================================

def tela_usuarios():
    st.title("👥 Gerenciamento de usuários")

    st.subheader("➕ Criar usuário")

    with st.form("form_novo_usuario"):
        col1, col2 = st.columns(2)

        with col1:
            usuario = st.text_input(
                "Usuário",
                key="novo_usuario_login",
            )

            nome = st.text_input(
                "Nome",
                key="novo_usuario_nome",
            )

        with col2:
            senha = st.text_input(
                "Senha",
                type="password",
                key="novo_usuario_senha",
            )

            perfil = st.selectbox(
                "Perfil",
                [
                    "OPERADOR",
                    "ADMIN",
                ],
                key="novo_usuario_perfil",
            )

        criar = st.form_submit_button(
            "Criar usuário",
            type="primary",
            use_container_width=True,
        )

        if criar:
            try:
                criar_usuario(
                    usuario,
                    nome,
                    senha,
                    perfil,
                )

                st.success("Usuário criado.")
                st.rerun()

            except Exception as erro:
                st.error(str(erro))

    st.divider()

    st.subheader("👤 Usuários cadastrados")

    usuarios = listar_usuarios()

    for usuario in usuarios:
        col1, col2, col3, col4 = st.columns(
            [2, 3, 2, 2]
        )

        with col1:
            st.write(f"**{usuario['usuario']}**")

        with col2:
            st.write(usuario["nome"])

        with col3:
            st.write(usuario["perfil"])

        with col4:
            if usuario["ativo"]:
                if st.button(
                    "🔴 Desativar",
                    key=f"desativar_{usuario['id']}",
                ):
                    alterar_status_usuario(
                        usuario["id"],
                        False,
                    )

                    st.rerun()
            else:
                if st.button(
                    "🟢 Ativar",
                    key=f"ativar_{usuario['id']}",
                ):
                    alterar_status_usuario(
                        usuario["id"],
                        True,
                    )

                    st.rerun()

    st.divider()

    st.subheader("🔑 Alterar senha")

    usuarios_ativos = [
        usuario
        for usuario in usuarios
        if usuario["ativo"]
    ]

    if usuarios_ativos:
        opcoes = {
            usuario["id"]: f"{usuario['nome']} ({usuario['usuario']})"
            for usuario in usuarios_ativos
        }

        usuario_senha = st.selectbox(
            "Usuário",
            list(opcoes.keys()),
            format_func=lambda x: opcoes[x],
            key="usuario_alterar_senha",
        )

        nova_senha = st.text_input(
            "Nova senha",
            type="password",
            key="nova_senha_usuario",
        )

        if st.button(
            "🔑 Alterar senha",
            use_container_width=True,
            key="botao_alterar_senha",
        ):
            try:
                alterar_senha_usuario(
                    usuario_senha,
                    nova_senha,
                )

                st.success("Senha alterada com sucesso.")

            except Exception as erro:
                st.error(str(erro))


# ============================================================
# RELATÓRIOS
# ============================================================

# ============================================================
# RELATÓRIOS
# ============================================================

def gerar_excel_relatorio(df):
    arquivo = BytesIO()

    with pd.ExcelWriter(
        arquivo,
        engine="openpyxl",
    ) as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Retiradas",
        )

        planilha = writer.sheets["Retiradas"]

        for coluna in planilha.columns:
            maior_tamanho = 0
            letra_coluna = coluna[0].column_letter

            for celula in coluna:
                valor = celula.value

                if valor is None:
                    tamanho = 0
                else:
                    tamanho = len(str(valor))

                if tamanho > maior_tamanho:
                    maior_tamanho = tamanho

            planilha.column_dimensions[letra_coluna].width = maior_tamanho + 3

    arquivo.seek(0)

    return arquivo


# ============================================================
# RELATÓRIOS
# ============================================================

def tela_relatorios():
    st.title("📑 Relatórios")

    periodo_selecionado = selecionar_periodo(
        "relatorios",
        label="📅 Selecione o período do relatório",
    )

    if not periodo_selecionado:
        return

    periodo_id = periodo_selecionado["id"]

    st.info(
        f"Relatório do período: **{periodo_selecionado.get('nome', '-')}**"
    )

    registros = obter_historico(
        limite=10000,
        periodo_id=periodo_id,
    )

    if not registros:
        st.info("Nenhum dado disponível neste período.")
        return

    dados = []

    for registro in registros:
        dados.append(
            {
                "Período": periodo_selecionado.get("nome"),
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

    st.metric(
        "👥 Pessoas que retiraram",
        len(retiradas),
    )

    st.dataframe(
        retiradas,
        use_container_width=True,
        hide_index=True,
    )

    arquivo_excel = gerar_excel_relatorio(
        retiradas
    )

    st.download_button(
        "⬇️ Exportar retiradas em Excel",
        data=arquivo_excel,
        file_name=f"relatorio_retiradas_{periodo_selecionado.get('nome', 'periodo')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="download_relatorio_retiradas_excel",
    )

    csv = retiradas.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )

    st.download_button(
        "⬇️ Exportar retiradas em CSV",
        data=csv,
        file_name=f"relatorio_retiradas_{periodo_selecionado.get('nome', 'periodo')}.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_relatorio_retiradas_csv",
    )


# ============================================================
# ROTEAMENTO
# ============================================================

pagina = st.session_state.pagina

if pagina == "Terminal":
    tela_terminal()

elif pagina == "Dashboard":
    tela_dashboard()

elif pagina == "Consulta":
    tela_consulta()

elif pagina == "Histórico" and eh_admin:
    tela_historico()

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

st.caption(
    "Sistema de Entrega de Cestas Básicas • Controle de distribuição"
)