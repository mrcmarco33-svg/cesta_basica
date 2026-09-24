from datetime import datetime

from services.supabase_client import obter_supabase


# ============================================================
# CONEXÃO
# ============================================================

def conectar():
    return obter_supabase()


# ============================================================
# UTILITÁRIOS
# ============================================================

def agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _inteiro(valor, padrao=0):
    if valor is None:
        return padrao

    try:
        if str(valor).strip() == "":
            return padrao

        return int(float(str(valor).replace(",", ".")))
    except Exception:
        return padrao


def _texto(valor):
    if valor is None:
        return ""

    return str(valor).strip()


def _eh_sim(valor):
    texto = _texto(valor).upper()

    return texto in [
        "SIM",
        "S",
        "YES",
        "TRUE",
        "1",
    ]


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def inicializar_banco():
    cliente = conectar()

    try:
        resposta = (
            cliente
            .table("estoque")
            .select("*")
            .eq("id", 1)
            .limit(1)
            .execute()
        )

        if not resposta.data:
            (
                cliente
                .table("estoque")
                .insert(
                    {
                        "id": 1,
                        "cesta_normal": 0,
                        "cesta_especial": 0,
                        "atualizado_em": None,
                    }
                )
                .execute()
            )

    except Exception as erro:
        raise RuntimeError(
            "Erro ao inicializar o banco no Supabase. "
            "Verifique se as tabelas foram criadas e se os Secrets estão corretos."
        ) from erro


# ============================================================
# ESTOQUE
# ============================================================

def obter_estoque():
    cliente = conectar()

    resposta = (
        cliente
        .table("estoque")
        .select("*")
        .eq("id", 1)
        .limit(1)
        .execute()
    )

    if resposta.data:
        return resposta.data[0]

    cliente.table("estoque").insert(
        {
            "id": 1,
            "cesta_normal": 0,
            "cesta_especial": 0,
            "atualizado_em": None,
        }
    ).execute()

    return {
        "id": 1,
        "cesta_normal": 0,
        "cesta_especial": 0,
        "atualizado_em": None,
    }


def configurar_estoque(cesta_normal, cesta_especial):
    cliente = conectar()

    payload = {
        "id": 1,
        "cesta_normal": _inteiro(cesta_normal),
        "cesta_especial": _inteiro(cesta_especial),
        "atualizado_em": agora(),
    }

    (
        cliente
        .table("estoque")
        .upsert(
            payload,
            on_conflict="id",
        )
        .execute()
    )


# ============================================================
# HISTÓRICO
# ============================================================

def registrar_historico(
    tipo_identificacao=None,
    id_cracha=None,
    matricula=None,
    nome=None,
    setor=None,
    cesta_normal=0,
    cesta_especial=0,
    resultado=None,
    motivo=None,
    data_hora=None,
):
    cliente = conectar()

    payload = {
        "data_hora": data_hora or agora(),
        "tipo_identificacao": tipo_identificacao,
        "id_cracha": id_cracha,
        "matricula": matricula,
        "nome": nome,
        "setor": setor,
        "cesta_normal": _inteiro(cesta_normal),
        "cesta_especial": _inteiro(cesta_especial),
        "resultado": resultado,
        "motivo": motivo,
    }

    (
        cliente
        .table("historico")
        .insert(payload)
        .execute()
    )


def registrar_tentativa_nao_encontrada(identificacao):
    id_cracha = None

    try:
        id_cracha = int(float(str(identificacao).strip()))
    except Exception:
        id_cracha = None

    registrar_historico(
        tipo_identificacao="NÃO ENCONTRADO",
        id_cracha=id_cracha,
        matricula=str(identificacao).strip(),
        nome=None,
        setor=None,
        cesta_normal=0,
        cesta_especial=0,
        resultado="NAO_ENCONTRADO",
        motivo="ID do crachá ou matrícula não encontrado.",
    )


def obter_historico(limite=5000):
    cliente = conectar()

    resposta = (
        cliente
        .table("historico")
        .select("*")
        .order(
            "id",
            desc=True,
        )
        .limit(limite)
        .execute()
    )

    return resposta.data or []


# ============================================================
# LIBERAÇÃO DE CESTA
# ============================================================

def _buscar_colaborador_por_id(colaborador_id):
    cliente = conectar()

    resposta = (
        cliente
        .table("colaboradores")
        .select("*")
        .eq("id", colaborador_id)
        .limit(1)
        .execute()
    )

    if not resposta.data:
        return None

    return resposta.data[0]


def liberar_cesta(colaborador_id, tipo_identificacao):
    cliente = conectar()

    try:
        resposta = (
            cliente
            .rpc(
                "liberar_cesta_rpc",
                {
                    "p_colaborador_id": int(colaborador_id),
                    "p_tipo_identificacao": tipo_identificacao,
                },
            )
            .execute()
        )

        dados = resposta.data

        if isinstance(dados, list):
            if not dados:
                return {
                    "sucesso": False,
                    "resultado": "ERRO",
                    "motivo": "A função de liberação não retornou dados.",
                }

            dados = dados[0]

        if not isinstance(dados, dict):
            return {
                "sucesso": False,
                "resultado": "ERRO",
                "motivo": "Resposta inválida da função de liberação.",
            }

        return dados

    except Exception as erro:
        return {
            "sucesso": False,
            "resultado": "ERRO",
            "motivo": f"Erro ao liberar cesta no Supabase: {erro}",
        }


# ============================================================
# INDICADORES
# ============================================================

def obter_indicadores():
    cliente = conectar()

    resposta = (
        cliente
        .table("historico")
        .select("*")
        .limit(10000)
        .execute()
    )

    registros = resposta.data or []

    liberadas = 0
    negadas = 0
    duplicadas = 0
    nao_encontradas = 0
    cestas_normais = 0
    cestas_especiais = 0

    for registro in registros:
        resultado = registro.get("resultado")

        if resultado == "LIBERADO":
            liberadas += 1
            cestas_normais += _inteiro(
                registro.get("cesta_normal")
            )
            cestas_especiais += _inteiro(
                registro.get("cesta_especial")
            )

        elif resultado == "NEGADO":
            negadas += 1

        elif resultado == "DUPLICADO":
            duplicadas += 1

        elif resultado == "NAO_ENCONTRADO":
            nao_encontradas += 1

    return {
        "liberadas": liberadas,
        "negadas": negadas,
        "duplicadas": duplicadas,
        "nao_encontradas": nao_encontradas,
        "cestas_normais": cestas_normais,
        "cestas_especiais": cestas_especiais,
        "tentativas": len(registros),
    }