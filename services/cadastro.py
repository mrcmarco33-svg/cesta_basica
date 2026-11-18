"""Cadastro permanente de colaboradores (matrícula → crachá).

Antes, o ID do crachá ficava só na lista do período (tabela
`colaboradores`). Agora existe a tabela `cadastro_colaboradores`, que
não depende de período: o crachá cadastrado uma vez vale para todas as
entregas seguintes.

A lista do período continua recebendo o `id_mat`, para que a função
`identificar_pessoa_rpc` (já existente no Supabase) siga funcionando.

Se a tabela ainda não foi criada (sql/001_cadastro_colaboradores.sql),
o app continua funcionando como antes, só com a lista do período.
"""

import streamlit as st

from services.supabase_client import obter_supabase
from services.tempo import agora_iso


TABELA_CADASTRO = "cadastro_colaboradores"


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_numero(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto or texto.lower() in {"nan", "none", "null"}:
        return None

    try:
        return int(float(texto))
    except Exception:
        return None


def normalizar_matricula(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto or texto.lower() in {"nan", "none", "null"}:
        return None

    if texto.endswith(".0"):
        try:
            texto = str(int(float(texto)))
        except Exception:
            pass

    return texto


def _cliente():
    return obter_supabase()


def dividir_em_lotes(lista, tamanho=500):
    for indice in range(0, len(lista), tamanho):
        yield lista[indice: indice + tamanho]


# ============================================================
# DISPONIBILIDADE
# ============================================================

@st.cache_data(ttl=120, show_spinner=False)
def cadastro_disponivel():
    """True quando a tabela cadastro_colaboradores existe no Supabase."""
    try:
        _cliente().table(TABELA_CADASTRO).select("id").limit(1).execute()
        return True
    except Exception:
        return False


# ============================================================
# CONSULTAS
# ============================================================

def buscar_por_matricula(matricula):
    matricula = normalizar_matricula(matricula)

    if not matricula or not cadastro_disponivel():
        return None

    resposta = (
        _cliente()
        .table(TABELA_CADASTRO)
        .select("*")
        .eq("matricula", matricula)
        .limit(1)
        .execute()
    )

    return resposta.data[0] if resposta.data else None


def buscar_por_cracha(id_cracha):
    id_cracha = normalizar_numero(id_cracha)

    if id_cracha is None or not cadastro_disponivel():
        return None

    resposta = (
        _cliente()
        .table(TABELA_CADASTRO)
        .select("*")
        .eq("id_cracha", id_cracha)
        .limit(1)
        .execute()
    )

    return resposta.data[0] if resposta.data else None


def mapa_por_matriculas(matriculas):
    """{matricula: registro} para uma lista de matrículas (em lotes)."""
    mapa = {}

    if not matriculas or not cadastro_disponivel():
        return mapa

    for lote in dividir_em_lotes(list(matriculas), 500):
        resposta = (
            _cliente()
            .table(TABELA_CADASTRO)
            .select("*")
            .in_("matricula", lote)
            .execute()
        )

        for registro in resposta.data or []:
            mapa[str(registro.get("matricula"))] = registro

    return mapa


def listar_cadastro(limite=50000):
    if not cadastro_disponivel():
        return []

    registros = []
    inicio = 0
    pagina = 1000

    while len(registros) < limite:
        resposta = (
            _cliente()
            .table(TABELA_CADASTRO)
            .select("*")
            .order("nome", desc=False)
            .range(inicio, inicio + pagina - 1)
            .execute()
        )

        lote = resposta.data or []
        registros.extend(lote)

        if len(lote) < pagina:
            break

        inicio += pagina

    return registros[:limite]


# ============================================================
# GRAVAÇÃO
# ============================================================

def _colaborador_periodo_com_cracha(id_cracha, periodo_id):
    resposta = (
        _cliente()
        .table("colaboradores")
        .select("id,matricula,nome")
        .eq("periodo_id", periodo_id)
        .eq("id_mat", id_cracha)
        .limit(1)
        .execute()
    )

    return resposta.data[0] if resposta.data else None


def definir_cracha(colaborador, id_cracha, periodo_id, usuario=None):
    """Grava o crachá de um colaborador no cadastro permanente e na lista
    do período ativo.

    `colaborador` é a linha da tabela `colaboradores` do período
    (precisa de id, matricula; nome e setor são copiados para o cadastro).

    Retorna {"sucesso": bool, "motivo": str, "id_cracha_anterior": int|None}.
    """
    id_cracha = normalizar_numero(id_cracha)

    if id_cracha is None:
        return {
            "sucesso": False,
            "motivo": "ID do crachá inválido. Aproxime o crachá novamente.",
        }

    matricula = normalizar_matricula(colaborador.get("matricula"))

    if not matricula:
        return {
            "sucesso": False,
            "motivo": "Colaborador sem matrícula. Não é possível cadastrar o crachá.",
        }

    # 1) O crachá já pertence a outra pessoa no cadastro permanente?
    dono_cadastro = buscar_por_cracha(id_cracha)

    if dono_cadastro and str(dono_cadastro.get("matricula")) != matricula:
        return {
            "sucesso": False,
            "motivo": (
                "Este crachá já está cadastrado para "
                f"{dono_cadastro.get('nome') or 'outro colaborador'} "
                f"(matrícula {dono_cadastro.get('matricula')})."
            ),
        }

    # 2) O crachá já pertence a outra pessoa na lista do período?
    tem_linha_periodo = colaborador.get("id") is not None and periodo_id is not None
    dono_periodo = (
        _colaborador_periodo_com_cracha(id_cracha, periodo_id)
        if periodo_id is not None
        else None
    )

    if dono_periodo and (
        not tem_linha_periodo or int(dono_periodo["id"]) != int(colaborador["id"])
    ):
        return {
            "sucesso": False,
            "motivo": (
                "Este crachá já está cadastrado neste período para "
                f"{dono_periodo.get('nome') or 'outro colaborador'} "
                f"(matrícula {dono_periodo.get('matricula')})."
            ),
        }

    anterior = colaborador.get("id_mat")

    # 3) Cadastro permanente (se a tabela existir).
    if cadastro_disponivel():
        existente = buscar_por_matricula(matricula)

        if existente and existente.get("id_cracha") is not None:
            anterior = existente.get("id_cracha")

        _cliente().table(TABELA_CADASTRO).upsert(
            {
                "matricula": matricula,
                "matricula_num": normalizar_numero(matricula),
                "nome": colaborador.get("nome"),
                "setor": colaborador.get("setor"),
                "id_cracha": id_cracha,
                "atualizado_em": agora_iso(),
                "atualizado_por": usuario,
            },
            on_conflict="matricula",
        ).execute()

    # 4) Lista do período ativo (usada pela identificação no banco).
    if tem_linha_periodo:
        (
            _cliente()
            .table("colaboradores")
            .update({"id_mat": id_cracha})
            .eq("periodo_id", periodo_id)
            .eq("id", colaborador["id"])
            .execute()
        )
    elif not cadastro_disponivel():
        return {
            "sucesso": False,
            "motivo": "Colaborador não está na lista do período ativo.",
        }

    try:
        anterior = int(anterior) if anterior is not None else None
    except (TypeError, ValueError):
        anterior = None

    return {
        "sucesso": True,
        "motivo": "Crachá cadastrado com sucesso.",
        "id_cracha": id_cracha,
        "id_cracha_anterior": anterior if anterior != id_cracha else None,
    }


def definir_cracha_por_matricula(matricula, id_cracha, periodo_id, usuario=None):
    """Usado pela tela de cadastro: localiza a pessoa pela matrícula na
    lista do período ativo ou, se não estiver nela, no cadastro permanente."""
    matricula = normalizar_matricula(matricula)

    if not matricula:
        return {"sucesso": False, "motivo": "Informe a matrícula."}

    resposta = (
        _cliente()
        .table("colaboradores")
        .select("*")
        .eq("periodo_id", periodo_id)
        .eq("matricula", matricula)
        .limit(1)
        .execute()
    )

    colaborador = resposta.data[0] if resposta.data else None

    if colaborador is None:
        permanente = buscar_por_matricula(matricula)

        if permanente is None:
            return {
                "sucesso": False,
                "motivo": f"Matrícula {matricula} não encontrada.",
            }

        colaborador = {
            "id": None,
            "matricula": matricula,
            "nome": permanente.get("nome"),
            "setor": permanente.get("setor"),
            "id_mat": permanente.get("id_cracha"),
        }

    return definir_cracha(colaborador, id_cracha, periodo_id, usuario=usuario)


def remover_cracha(matricula, periodo_id=None):
    """Tira o crachá do cadastro (ex.: crachá perdido) e da lista do período."""
    matricula = normalizar_matricula(matricula)

    if not matricula:
        return

    if cadastro_disponivel():
        _cliente().table(TABELA_CADASTRO).update(
            {"id_cracha": None, "atualizado_em": agora_iso()}
        ).eq("matricula", matricula).execute()

    if periodo_id is not None:
        _cliente().table("colaboradores").update(
            {"id_mat": None}
        ).eq("periodo_id", periodo_id).eq("matricula", matricula).execute()


def sincronizar_da_planilha(registros, usuario=None):
    """Mantém o cadastro permanente atualizado a partir da importação.

    - Nome, setor e matrícula são sempre atualizados.
    - O crachá da planilha só entra no cadastro quando a pessoa ainda não
      tem crachá e o número não está em uso por outra matrícula.
      (Crachás registrados pelo terminal nunca são apagados pela planilha.)

    Retorna quantos registros foram sincronizados (0 se a tabela não existir).
    """
    if not registros or not cadastro_disponivel():
        return 0

    cliente = _cliente()
    agora = agora_iso()

    dados_basicos = []
    vistos = set()

    for registro in registros:
        matricula = normalizar_matricula(registro.get("matricula"))

        if not matricula or matricula in vistos:
            continue

        vistos.add(matricula)
        dados_basicos.append(
            {
                "matricula": matricula,
                "matricula_num": normalizar_numero(matricula),
                "nome": registro.get("nome"),
                "setor": registro.get("setor"),
                "atualizado_em": agora,
            }
        )

    # Upsert só com essas colunas: o id_cracha existente é preservado.
    for lote in dividir_em_lotes(dados_basicos, 500):
        cliente.table(TABELA_CADASTRO).upsert(
            lote,
            on_conflict="matricula",
        ).execute()

    # Crachás vindos da planilha para quem ainda não tem.
    mapa = mapa_por_matriculas([item["matricula"] for item in dados_basicos])
    em_uso = {
        int(r["id_cracha"])
        for r in mapa.values()
        if r.get("id_cracha") is not None
    }

    for registro in registros:
        matricula = normalizar_matricula(registro.get("matricula"))
        id_cracha = normalizar_numero(registro.get("id_mat"))
        atual = mapa.get(matricula)

        if id_cracha is None or not atual or atual.get("id_cracha") is not None:
            continue

        if id_cracha in em_uso or buscar_por_cracha(id_cracha):
            continue

        try:
            cliente.table(TABELA_CADASTRO).update(
                {
                    "id_cracha": id_cracha,
                    "atualizado_em": agora,
                    "atualizado_por": usuario or "importação",
                }
            ).eq("matricula", matricula).execute()
            em_uso.add(id_cracha)
        except Exception:
            # Conflito raro de unicidade: ignora e segue.
            pass

    return len(dados_basicos)
