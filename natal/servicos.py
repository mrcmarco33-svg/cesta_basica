"""Regras e acesso ao banco do app de cestas natalinas.

Tabelas: natal_campanhas, natal_lista, natal_historico (sql/003_natal.sql).
Reaproveita o cadastro permanente de crachás (cadastro_colaboradores).
"""

import unicodedata
from datetime import datetime

import streamlit as st

from services import cadastro
from services.supabase_client import obter_supabase
from services.tempo import agora_iso, fuso_local


# ============================================================
# UTILITÁRIOS
# ============================================================

def _cliente():
    return obter_supabase()


def texto(valor):
    if valor is None:
        return ""
    t = str(valor).strip()
    return "" if t.lower() in {"", "nan", "none", "null", "nat"} else t


def numero(valor):
    t = texto(valor)
    if not t:
        return None
    try:
        return int(float(t.replace(",", ".")))
    except Exception:
        return None


def matricula_normalizada(valor):
    """'007682', 7682.0 e ' 7682 ' viram a mesma matrícula."""
    t = texto(valor)
    if not t:
        return None
    if t.endswith(".0"):
        t = t[:-2]
    return t


def data_hora_local(valor):
    """Converte o horário do banco (UTC) para o horário local."""
    t = texto(valor)
    if not t:
        return ""
    try:
        data = datetime.fromisoformat(t.replace("Z", "+00:00"))
        if data.tzinfo is not None:
            data = data.astimezone(fuso_local())
        return data.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return t


def _lotes(lista, tamanho=500):
    for i in range(0, len(lista), tamanho):
        yield lista[i: i + tamanho]


def _paginado(consulta_fn, pagina=1000, limite=200000):
    registros = []
    inicio = 0
    while len(registros) < limite:
        lote = consulta_fn().range(inicio, inicio + pagina - 1).execute().data or []
        registros.extend(lote)
        if len(lote) < pagina:
            break
        inicio += pagina
    return registros[:limite]


# ============================================================
# CAMPANHAS
# ============================================================

@st.cache_data(ttl=10, show_spinner=False)
def campanha_ativa():
    resposta = (
        _cliente()
        .table("natal_campanhas")
        .select("*")
        .eq("ativa", True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return resposta.data[0] if resposta.data else None


def limpar_cache():
    campanha_ativa.clear()


def listar_campanhas():
    resposta = (
        _cliente()
        .table("natal_campanhas")
        .select("*")
        .order("id", desc=True)
        .execute()
    )
    return resposta.data or []


def criar_campanha(nome, estoque=None, usuario=None):
    nome = texto(nome)
    if not nome:
        raise ValueError("Informe o nome da campanha.")

    cliente = _cliente()
    cliente.table("natal_campanhas").update({"ativa": False}).eq("ativa", True).execute()
    resposta = cliente.table("natal_campanhas").insert(
        {
            "nome": nome,
            "ativa": True,
            "status": "ABERTA",
            "estoque_inicial": estoque,
            "criado_por": usuario,
        }
    ).execute()
    limpar_cache()
    return resposta.data[0] if resposta.data else None


def ativar_campanha(campanha_id):
    cliente = _cliente()
    cliente.table("natal_campanhas").update({"ativa": False}).eq("ativa", True).execute()
    cliente.table("natal_campanhas").update({"ativa": True}).eq("id", campanha_id).execute()
    limpar_cache()


def finalizar_campanha(campanha_id, usuario=None):
    _cliente().table("natal_campanhas").update(
        {"status": "FINALIZADA", "finalizado_em": agora_iso(), "finalizado_por": usuario}
    ).eq("id", campanha_id).execute()
    limpar_cache()


def reabrir_campanha(campanha_id):
    _cliente().table("natal_campanhas").update(
        {"status": "ABERTA", "finalizado_em": None, "finalizado_por": None}
    ).eq("id", campanha_id).execute()
    limpar_cache()


def definir_estoque(campanha_id, estoque):
    _cliente().table("natal_campanhas").update(
        {"estoque_inicial": estoque}
    ).eq("id", campanha_id).execute()
    limpar_cache()


# ============================================================
# IMPORTAÇÃO DA LISTA
# ============================================================

def _chave_coluna(nome):
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return "".join(c for c in t.lower() if c.isalnum())


SINONIMOS = {
    "matricula": {"matricula", "mat", "chapa", "registro", "re", "codigo", "matriculafuncionario"},
    "nome": {"nome", "nomecompleto", "colaborador", "funcionario", "nomedocolaborador"},
    "setor": {"setor", "departamento", "area", "centrodecusto", "cc", "lotacao"},
}


def mapear_colunas(colunas):
    """Descobre quais colunas da planilha são matrícula, nome e setor."""
    mapa = {}
    for coluna in colunas:
        chave = _chave_coluna(coluna)
        for campo, nomes in SINONIMOS.items():
            if campo not in mapa and chave in nomes:
                mapa[campo] = coluna
    return mapa


def preparar_lista(linhas, colunas):
    """Valida as linhas da planilha.

    Retorna (itens, erros, avisos). Cada pessoa tem direito a 1 cesta.
    """
    mapa = mapear_colunas(colunas)
    erros, avisos = [], []

    if "matricula" not in mapa:
        erros.append(
            "Não encontrei a coluna de matrícula. Use um cabeçalho como "
            "\"Matrícula\" (também aceito: Chapa, Registro, Código)."
        )
        return [], erros, avisos

    if "nome" not in mapa:
        avisos.append("Planilha sem coluna \"Nome\": os nomes virão do cadastro, se existir.")

    itens, vistos = [], {}
    for indice, linha in enumerate(linhas, start=2):  # linha 1 = cabeçalho
        matricula = matricula_normalizada(linha.get(mapa["matricula"]))
        nome = texto(linha.get(mapa.get("nome"))) if "nome" in mapa else ""
        setor = texto(linha.get(mapa.get("setor"))) if "setor" in mapa else ""

        if not matricula:
            if nome or setor:
                avisos.append(f"Linha {indice}: sem matrícula, ignorada ({nome or setor}).")
            continue

        chave = numero(matricula) if numero(matricula) is not None else matricula
        if chave in vistos:
            avisos.append(
                f"Linha {indice}: matrícula {matricula} repetida (já na linha {vistos[chave]}), ignorada."
            )
            continue
        vistos[chave] = indice

        itens.append(
            {
                "matricula": matricula,
                "matricula_num": numero(matricula),
                "nome": nome or None,
                "setor": setor or None,
            }
        )

    if not itens and not erros:
        erros.append("Nenhuma matrícula válida encontrada na planilha.")

    return itens, erros, avisos


def completar_com_cadastro(itens):
    """Preenche nome/setor vazios a partir do cadastro permanente."""
    faltando = [i["matricula"] for i in itens if not i.get("nome") or not i.get("setor")]
    if not faltando:
        return itens
    try:
        mapa = cadastro.mapa_por_matriculas(faltando)
    except Exception:
        return itens
    for item in itens:
        registro = mapa.get(item["matricula"])
        if registro:
            item["nome"] = item.get("nome") or registro.get("nome")
            item["setor"] = item.get("setor") or registro.get("setor")
    return itens


def importar_lista(campanha_id, itens):
    """Grava a lista. Quem já retirou continua como retirado:
    o upsert envia só matrícula/nome/setor, nunca o campo 'retirado'."""
    existentes = {
        str(r["matricula"])
        for r in _paginado(
            lambda: _cliente().table("natal_lista").select("matricula")
            .eq("campanha_id", campanha_id).order("id")
        )
    }

    payload = [dict(item, campanha_id=campanha_id) for item in itens]
    for lote in _lotes(payload, 500):
        _cliente().table("natal_lista").upsert(
            lote, on_conflict="campanha_id,matricula"
        ).execute()

    novos = sum(1 for i in itens if i["matricula"] not in existentes)
    return {"novos": novos, "atualizados": len(itens) - novos, "total": len(itens)}


def listar_lista(campanha_id):
    return _paginado(
        lambda: _cliente().table("natal_lista").select("*")
        .eq("campanha_id", campanha_id).order("nome")
    )


def adicionar_pessoa(campanha_id, matricula, nome, setor):
    matricula = matricula_normalizada(matricula)
    if not matricula:
        raise ValueError("Informe a matrícula.")
    item = completar_com_cadastro(
        [{"matricula": matricula, "matricula_num": numero(matricula),
          "nome": texto(nome) or None, "setor": texto(setor) or None}]
    )[0]
    _cliente().table("natal_lista").upsert(
        dict(item, campanha_id=campanha_id), on_conflict="campanha_id,matricula"
    ).execute()


def limpar_lista_sem_retirada(campanha_id):
    """Remove da lista quem ainda não retirou (para reimportar do zero)."""
    _cliente().table("natal_lista").delete().eq("campanha_id", campanha_id).eq(
        "retirado", False
    ).execute()


# ============================================================
# IDENTIFICAÇÃO E RETIRADA
# ============================================================

def _buscar_na_lista(campanha_id, matricula=None, matricula_num=None):
    consulta = _cliente().table("natal_lista").select("*").eq("campanha_id", campanha_id)
    if matricula_num is not None:
        resposta = consulta.eq("matricula_num", matricula_num).limit(1).execute()
        if resposta.data:
            return resposta.data[0]
        consulta = _cliente().table("natal_lista").select("*").eq("campanha_id", campanha_id)
    if matricula:
        resposta = consulta.eq("matricula", matricula).limit(1).execute()
        if resposta.data:
            return resposta.data[0]
    return None


def identificar(valor, campanha_id):
    """Crachá (pelo cadastro permanente) ou matrícula.

    Retorna {"item": linha da lista | None, "forma": "CRACHÁ"|"MATRÍCULA"|None,
             "pessoa": {matricula, nome, setor} | None}
    """
    lido = texto(valor)
    num = numero(lido)

    # 1) Crachá cadastrado no app de cestas básicas.
    dono = None
    if num is not None:
        try:
            dono = cadastro.buscar_por_cracha(num)
        except Exception:
            dono = None

    if dono:
        item = _buscar_na_lista(
            campanha_id,
            matricula=matricula_normalizada(dono.get("matricula")),
            matricula_num=numero(dono.get("matricula")),
        )
        return {
            "item": item,
            "forma": "CRACHÁ",
            "pessoa": {
                "matricula": dono.get("matricula"),
                "nome": (item or {}).get("nome") or dono.get("nome"),
                "setor": (item or {}).get("setor") or dono.get("setor"),
            },
        }

    # 2) Matrícula digitada.
    item = _buscar_na_lista(campanha_id, matricula=matricula_normalizada(lido), matricula_num=num)
    if item:
        return {"item": item, "forma": "MATRÍCULA", "pessoa": item}

    # 3) Não está na lista: tenta ao menos mostrar o nome pelo cadastro.
    pessoa = None
    try:
        pessoa = cadastro.buscar_por_matricula(matricula_normalizada(lido))
    except Exception:
        pessoa = None
    return {"item": None, "forma": "MATRÍCULA" if pessoa else None, "pessoa": pessoa}


def retirar(item, usuario, forma):
    resposta = _cliente().rpc(
        "natal_retirar",
        {"p_lista_id": item["id"], "p_usuario": usuario, "p_forma": forma},
    ).execute()
    dados = resposta.data
    if isinstance(dados, list):
        dados = dados[0] if dados else {}
    return dados or {"resultado": "ERRO"}


def registrar_leitura(campanha_id, valor_lido, forma, pessoa, resultado, motivo, usuario):
    try:
        pessoa = pessoa or {}
        _cliente().table("natal_historico").insert(
            {
                "campanha_id": campanha_id,
                "tipo_identificacao": forma,
                "valor_lido": texto(valor_lido),
                "matricula": texto(pessoa.get("matricula")) or None,
                "nome": texto(pessoa.get("nome")) or None,
                "setor": texto(pessoa.get("setor")) or None,
                "resultado": resultado,
                "motivo": motivo,
                "usuario": usuario,
            }
        ).execute()
    except Exception:
        pass


def processar_leitura(valor, campanha, usuario):
    """Fluxo completo de uma leitura no terminal. Retorna o resultado para a tela."""
    campanha_id = campanha["id"]
    achado = identificar(valor, campanha_id)
    item, forma, pessoa = achado["item"], achado["forma"], achado["pessoa"] or {}

    base = {
        "valor_lido": texto(valor),
        "forma": forma,
        "matricula": texto(pessoa.get("matricula")),
        "nome": texto(pessoa.get("nome")),
        "setor": texto(pessoa.get("setor")),
    }

    if str(campanha.get("status")).upper() != "ABERTA":
        resultado = dict(base, resultado="FINALIZADA")
    elif item is None:
        resultado = dict(base, resultado="NAO_ESTA_NA_LISTA")
    else:
        retorno = retirar(item, usuario, forma)
        resultado = dict(
            base,
            resultado=retorno.get("resultado", "ERRO"),
            data_hora=data_hora_local(retorno.get("data_hora_retirada")),
            retirado_por=retorno.get("retirado_por"),
        )

    motivos = {
        "ENTREGUE": "Cesta natalina entregue.",
        "JA_RETIROU": f"Já retirou em {resultado.get('data_hora') or '-'}.",
        "NAO_ESTA_NA_LISTA": "Não está na lista da campanha.",
        "SEM_ESTOQUE": "Estoque de cestas natalinas esgotado.",
        "FINALIZADA": "Campanha finalizada.",
    }
    resultado["motivo"] = motivos.get(resultado["resultado"], "Erro ao registrar a retirada.")

    registrar_leitura(
        campanha_id, valor, forma, pessoa, resultado["resultado"], resultado["motivo"], usuario
    )
    limpar_cache()
    return resultado


# ============================================================
# INDICADORES, HISTÓRICO E RELATÓRIO
# ============================================================

def indicadores(campanha):
    lista = _paginado(
        lambda: _cliente().table("natal_lista").select("id,retirado,setor")
        .eq("campanha_id", campanha["id"]).order("id")
    )
    total = len(lista)
    entregues = sum(1 for r in lista if r.get("retirado"))
    estoque = campanha.get("estoque_inicial")

    por_setor = {}
    for r in lista:
        setor = texto(r.get("setor")) or "SEM SETOR"
        dados = por_setor.setdefault(setor, {"Setor": setor, "Total": 0, "Entregues": 0})
        dados["Total"] += 1
        dados["Entregues"] += 1 if r.get("retirado") else 0
    for dados in por_setor.values():
        dados["Pendentes"] = dados["Total"] - dados["Entregues"]

    return {
        "total": total,
        "entregues": entregues,
        "pendentes": total - entregues,
        "percentual": (entregues / total * 100) if total else 0.0,
        "estoque": estoque,
        "estoque_restante": (estoque - entregues) if estoque is not None else None,
        "por_setor": sorted(por_setor.values(), key=lambda d: d["Setor"]),
    }


def historico(campanha_id, limite=5000):
    return _paginado(
        lambda: _cliente().table("natal_historico").select("*")
        .eq("campanha_id", campanha_id).order("id", desc=True),
        limite=limite,
    )
