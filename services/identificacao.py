from services.supabase_client import obter_supabase


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
# BUSCAS INDIVIDUAIS
# ============================================================

def buscar_por_id_cracha(id_cracha):
    id_cracha = normalizar_id_cracha(
        id_cracha
    )

    if id_cracha is None:
        return None

    cliente = _cliente()

    resposta = (
        cliente
        .table("colaboradores")
        .select("*")
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

    cliente = _cliente()

    resposta = (
        cliente
        .table("colaboradores")
        .select("*")
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

    cliente = _cliente()

    resposta = (
        cliente
        .table("demitidos")
        .select("*")
        .eq("chapa_num", chapa_num)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    return resposta.data[0]


# ============================================================
# CADASTRO DE CRACHÁ
# ============================================================

def cracha_ja_cadastrado(id_cracha, ignorar_colaborador_id=None):
    id_cracha = normalizar_id_cracha(
        id_cracha
    )

    if id_cracha is None:
        return None

    cliente = _cliente()

    resposta = (
        cliente
        .table("colaboradores")
        .select("*")
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


def cadastrar_cracha(colaborador_id, id_cracha):
    id_cracha = normalizar_id_cracha(
        id_cracha
    )

    if id_cracha is None:
        return {
            "sucesso": False,
            "motivo": "ID do crachá inválido.",
        }

    duplicado = cracha_ja_cadastrado(
        id_cracha,
        ignorar_colaborador_id=colaborador_id,
    )

    if duplicado:
        return {
            "sucesso": False,
            "motivo": (
                "Este crachá já está cadastrado para "
                f"{duplicado.get('nome', 'outro colaborador')}."
            ),
        }

    cliente = _cliente()

    (
        cliente
        .table("colaboradores")
        .update(
            {
                "id_mat": id_cracha,
            }
        )
        .eq("id", colaborador_id)
        .execute()
    )

    return {
        "sucesso": True,
        "motivo": "Crachá cadastrado com sucesso.",
    }


# ============================================================
# IDENTIFICAÇÃO OTIMIZADA
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


def _identificar_fallback(valor):
    matricula_num = normalizar_matricula(
        valor
    )

    if matricula_num is None:
        return {
            "tipo": "NAO_ENCONTRADO",
            "resultado": "Identificação inválida.",
        }

    cliente = _cliente()

    try:
        resposta = (
            cliente
            .table("colaboradores")
            .select("*")
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
        "resultado": "ID do crachá ou matrícula não encontrado.",
    }


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

    try:
        resultado = _identificar_rpc(
            valor
        )

        if resultado:
            return resultado

    except Exception:
        pass

    return _identificar_fallback(
        valor
    )