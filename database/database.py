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

    if entrega_esta_finalizada():
        colaborador = _buscar_colaborador_por_id(
            colaborador_id
        )

        if colaborador:
            registrar_historico(
                tipo_identificacao=tipo_identificacao,
                id_cracha=colaborador.get("id_mat"),
                matricula=colaborador.get("matricula"),
                nome=colaborador.get("nome"),
                setor=colaborador.get("setor"),
                cesta_normal=0,
                cesta_especial=0,
                resultado="NEGADO",
                motivo="Entrega finalizada. Não é possível realizar nova retirada.",
            )

        return {
            "sucesso": False,
            "resultado": "NEGADO",
            "motivo": "Entrega finalizada. Não é possível realizar nova retirada.",
        }

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
# ============================================================
# CONTROLE DE ENTREGA
# ============================================================

def obter_status_entrega():
    cliente = conectar()

    resposta = (
        cliente
        .table("controle_entrega")
        .select("*")
        .eq("id", 1)
        .limit(1)
        .execute()
    )

    if resposta.data:
        return resposta.data[0]

    payload = {
        "id": 1,
        "status": "ABERTA",
        "data_inicio": agora(),
        "data_finalizacao": None,
        "usuario_finalizacao": None,
        "observacao": None,
    }

    (
        cliente
        .table("controle_entrega")
        .insert(payload)
        .execute()
    )

    return payload


def entrega_esta_finalizada():
    status = obter_status_entrega()

    return str(
        status.get("status", "")
    ).upper() == "FINALIZADA"


def finalizar_entrega(usuario=None, observacao=None):
    cliente = conectar()

    payload = {
        "status": "FINALIZADA",
        "data_finalizacao": agora(),
        "usuario_finalizacao": usuario,
        "observacao": observacao,
        "updated_at": datetime.now().isoformat(),
    }

    (
        cliente
        .table("controle_entrega")
        .update(payload)
        .eq("id", 1)
        .execute()
    )

    return {
        "sucesso": True,
        "mensagem": "Entrega finalizada com sucesso.",
    }


def reabrir_entrega(usuario=None):
    cliente = conectar()

    payload = {
        "status": "ABERTA",
        "data_finalizacao": None,
        "usuario_finalizacao": usuario,
        "observacao": None,
        "updated_at": datetime.now().isoformat(),
    }

    (
        cliente
        .table("controle_entrega")
        .update(payload)
        .eq("id", 1)
        .execute()
    )

    return {
        "sucesso": True,
        "mensagem": "Entrega reaberta com sucesso.",
    }


# ============================================================
# CONSULTA DE RETIRADAS
# ============================================================

def _colaborador_autorizado(colaborador):
    cesta_normal = _inteiro(
        colaborador.get("cesta_normal")
    )

    cesta_especial = _inteiro(
        colaborador.get("cesta_especial")
    )

    perdeu = _eh_sim(
        colaborador.get("perde")
    )

    return (
        cesta_normal > 0
        or cesta_especial > 0
    ) and not perdeu


def _colaborador_retirou(colaborador):
    return _eh_sim(
        colaborador.get("confirmacao_retirada")
    )


def obter_consulta_retiradas(situacao="PENDENTES", busca=None):
    cliente = conectar()

    resposta = (
        cliente
        .table("colaboradores")
        .select(
            "id,id_mat,matricula,matricula_num,nome,setor,"
            "cesta_normal,cesta_especial,perde,"
            "confirmacao_retirada,data_hora_retirada"
        )
        .order(
            "nome",
            desc=False,
        )
        .limit(20000)
        .execute()
    )

    registros = resposta.data or []

    busca_texto = str(
        busca or ""
    ).strip().lower()

    resultado = []

    for colaborador in registros:
        autorizado = _colaborador_autorizado(
            colaborador
        )

        retirou = _colaborador_retirou(
            colaborador
        )

        if autorizado and retirou:
            status = "RETIRADO"
        elif autorizado and not retirou:
            status = "PENDENTE"
        else:
            status = "NÃO AUTORIZADO"

        incluir = False

        if situacao == "TODOS":
            incluir = True

        elif situacao == "PENDENTES" and status == "PENDENTE":
            incluir = True

        elif situacao == "RETIRADOS" and status == "RETIRADO":
            incluir = True

        elif situacao == "NAO_AUTORIZADOS" and status == "NÃO AUTORIZADO":
            incluir = True

        if not incluir:
            continue

        if busca_texto:
            texto_linha = " ".join(
                [
                    str(colaborador.get("matricula") or ""),
                    str(colaborador.get("id_mat") or ""),
                    str(colaborador.get("nome") or ""),
                    str(colaborador.get("setor") or ""),
                ]
            ).lower()

            if busca_texto not in texto_linha:
                continue

        item = dict(
            colaborador
        )

        item["situacao"] = status

        resultado.append(
            item
        )

    return resultado


def obter_resumo_consulta():
    todos = obter_consulta_retiradas(
        situacao="TODOS"
    )

    total = len(
        todos
    )

    autorizados = 0
    pendentes = 0
    retirados = 0
    nao_autorizados = 0

    for colaborador in todos:
        situacao = colaborador.get(
            "situacao"
        )

        if situacao == "PENDENTE":
            pendentes += 1
            autorizados += 1

        elif situacao == "RETIRADO":
            retirados += 1
            autorizados += 1

        else:
            nao_autorizados += 1

    return {
        "total": total,
        "autorizados": autorizados,
        "pendentes": pendentes,
        "retirados": retirados,
        "nao_autorizados": nao_autorizados,
    }