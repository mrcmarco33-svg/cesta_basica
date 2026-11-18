from services.supabase_client import obter_supabase
from services import cadastro
from database.database import obter_periodo_ativo_id


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_id_cracha(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    try:
        return int(float(texto))
    except Exception:
        return None


def normalizar_matricula(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    try:
        return int(float(texto))
    except Exception:
        return None


def _cliente():
    return obter_supabase()


# ============================================================
# BUSCAS INDIVIDUAIS NO PERÍODO ATIVO
# ============================================================

def buscar_por_id_cracha(id_cracha):
    id_cracha = normalizar_id_cracha(
        id_cracha
    )

    if id_cracha is None:
        return None

    periodo_id = obter_periodo_ativo_id()
    cliente = _cliente()

    resposta = (
        cliente
        .table("colaboradores")
        .select("*")
        .eq("periodo_id", periodo_id)
        .eq("id_mat", id_cracha)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    return resposta.data[0]


def buscar_por_matricula(matricula):
    matricula_num = normalizar_matricula(
        matricula
    )

    if matricula_num is None:
        return None

    periodo_id = obter_periodo_ativo_id()
    cliente = _cliente()

    resposta = (
        cliente
        .table("colaboradores")
        .select("*")
        .eq("periodo_id", periodo_id)
        .eq("matricula_num", matricula_num)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    return resposta.data[0]


def buscar_demitido(chapa):
    chapa_num = normalizar_matricula(
        chapa
    )

    if chapa_num is None:
        return None

    periodo_id = obter_periodo_ativo_id()
    cliente = _cliente()

    resposta = (
        cliente
        .table("demitidos")
        .select("*")
        .eq("periodo_id", periodo_id)
        .eq("chapa_num", chapa_num)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    return resposta.data[0]


# ============================================================
# CADASTRO DE CRACHÁ NO PERÍODO ATIVO
# ============================================================

def cracha_ja_cadastrado(id_cracha, ignorar_colaborador_id=None):
    id_cracha = normalizar_id_cracha(
        id_cracha
    )

    if id_cracha is None:
        return None

    periodo_id = obter_periodo_ativo_id()
    cliente = _cliente()

    resposta = (
        cliente
        .table("colaboradores")
        .select("*")
        .eq("periodo_id", periodo_id)
        .eq("id_mat", id_cracha)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    colaborador = resposta.data[0]

    if (
        ignorar_colaborador_id is not None
        and int(colaborador["id"]) == int(ignorar_colaborador_id)
    ):
        return None

    return colaborador


def _colaborador_periodo_por_id(colaborador_id, periodo_id):
    resposta = (
        _cliente()
        .table("colaboradores")
        .select("*")
        .eq("periodo_id", periodo_id)
        .eq("id", colaborador_id)
        .limit(1)
        .execute()
    )

    return resposta.data[0] if resposta.data else None


def cadastrar_cracha(colaborador_id, id_cracha, usuario=None):
    """Cadastra/atualiza o crachá no cadastro permanente e no período ativo."""
    periodo_id = obter_periodo_ativo_id()
    colaborador = _colaborador_periodo_por_id(colaborador_id, periodo_id)

    if colaborador is None:
        return {
            "sucesso": False,
            "motivo": "Colaborador não localizado no período ativo.",
        }

    return cadastro.definir_cracha(
        colaborador,
        id_cracha,
        periodo_id,
        usuario=usuario,
    )


def completar_cracha_pelo_cadastro(colaborador):
    """Se a lista do período está sem crachá, mas o cadastro permanente já
    tem, copia o crachá para o período e devolve o colaborador atualizado.
    Assim o terminal só pede o crachá a quem realmente nunca cadastrou."""
    if colaborador.get("id_mat") is not None:
        return colaborador

    try:
        permanente = cadastro.buscar_por_matricula(colaborador.get("matricula"))
    except Exception:
        return colaborador

    if not permanente or permanente.get("id_cracha") is None:
        return colaborador

    periodo_id = colaborador.get("periodo_id") or obter_periodo_ativo_id()

    resultado = cadastro.definir_cracha(
        colaborador,
        permanente["id_cracha"],
        periodo_id,
        usuario="cadastro",
    )

    if resultado.get("sucesso"):
        atualizado = dict(colaborador)
        atualizado["id_mat"] = int(permanente["id_cracha"])
        return atualizado

    return colaborador


def _identificar_pelo_cadastro(valor):
    """Crachá que está no cadastro permanente, mas ainda não na lista do
    período: localiza a matrícula e sincroniza o período."""
    try:
        permanente = cadastro.buscar_por_cracha(valor)
    except Exception:
        return None

    if not permanente:
        return None

    colaborador = buscar_por_matricula(permanente.get("matricula"))

    if not colaborador:
        return None

    colaborador = completar_cracha_pelo_cadastro(colaborador)

    return {
        "tipo": "COLABORADOR",
        "identificacao": "ID CRACHÁ",
        "dados": colaborador,
    }


# ============================================================
# IDENTIFICAÇÃO OTIMIZADA VIA RPC
# ============================================================

def _identificar_rpc(valor):
    cliente = _cliente()

    resposta = (
        cliente
        .rpc(
            "identificar_pessoa_rpc",
            {
                "p_valor": str(valor).strip(),
            },
        )
        .execute()
    )

    dados = resposta.data

    if isinstance(dados, list):
        if not dados:
            return None

        dados = dados[0]

    if isinstance(dados, dict):
        return dados

    return None


# ============================================================
# IDENTIFICAÇÃO FALLBACK
# ============================================================

def _identificar_fallback(valor):
    matricula_num = normalizar_matricula(
        valor
    )

    if matricula_num is None:
        return {
            "tipo": "NAO_ENCONTRADO",
            "resultado": "Identificação inválida.",
        }

    periodo_id = obter_periodo_ativo_id()
    cliente = _cliente()

    try:
        resposta = (
            cliente
            .table("colaboradores")
            .select("*")
            .eq("periodo_id", periodo_id)
            .or_(
                f"matricula_num.eq.{matricula_num},id_mat.eq.{matricula_num}"
            )
            .limit(10)
            .execute()
        )

        colaboradores = resposta.data or []

        for colaborador in colaboradores:
            if colaborador.get("matricula_num") == matricula_num:
                return {
                    "tipo": "COLABORADOR",
                    "identificacao": "MATRÍCULA",
                    "dados": colaborador,
                }

        for colaborador in colaboradores:
            if colaborador.get("id_mat") == matricula_num:
                return {
                    "tipo": "COLABORADOR",
                    "identificacao": "ID CRACHÁ",
                    "dados": colaborador,
                }

    except Exception:
        colaborador = buscar_por_matricula(
            valor
        )

        if colaborador:
            return {
                "tipo": "COLABORADOR",
                "identificacao": "MATRÍCULA",
                "dados": colaborador,
            }

        colaborador = buscar_por_id_cracha(
            valor
        )

        if colaborador:
            return {
                "tipo": "COLABORADOR",
                "identificacao": "ID CRACHÁ",
                "dados": colaborador,
            }

    demitido = buscar_demitido(
        valor
    )

    if demitido:
        return {
            "tipo": "DEMITIDO",
            "identificacao": "CHAPA",
            "dados": demitido,
        }

    return {
        "tipo": "NAO_ENCONTRADO",
        "resultado": "ID do crachá ou matrícula não encontrado no período ativo.",
    }


# ============================================================
# IDENTIFICAÇÃO PRINCIPAL
# ============================================================

def identificar(identificacao):
    if identificacao is None:
        return {
            "tipo": "NAO_ENCONTRADO",
            "resultado": "Identificação vazia.",
        }

    valor = str(
        identificacao
    ).strip()

    if not valor:
        return {
            "tipo": "NAO_ENCONTRADO",
            "resultado": "Identificação vazia.",
        }

    resultado = None

    try:
        resultado = _identificar_rpc(
            valor
        )
    except Exception:
        resultado = None

    if not resultado:
        resultado = _identificar_fallback(
            valor
        )

    if resultado.get("tipo") == "NAO_ENCONTRADO":
        pelo_cadastro = _identificar_pelo_cadastro(valor)

        if pelo_cadastro:
            return pelo_cadastro

    return resultado