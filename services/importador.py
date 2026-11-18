import pandas as pd

from services.supabase_client import obter_supabase
from services import cadastro
from database.database import obter_periodo_ativo_id


ABA_COLABORADORES = "BANCO DE DADOS"
ABA_DEMITIDOS = "Cesta demitidos"

COLUNAS_COLABORADORES = [
    "ID Mat",
    "Mat",
    "Nome",
    "Setor",
    "Cesta Normal",
    "Cesta Especial",
    "Perde",
    "Confirmação de retirada",
    "Data e Hora retirada",
]

COLUNAS_DEMITIDOS = [
    "CHAPA",
    "NOME",
    "Retirado",
    "Data e Hora",
]


# ============================================================
# UTILITÁRIOS
# ============================================================

def dividir_em_lotes(lista, tamanho=500):
    for indice in range(0, len(lista), tamanho):
        yield lista[indice: indice + tamanho]


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(valor):
    if valor is None:
        return None

    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    if not texto or texto.lower() == "nan":
        return None

    return texto


def normalizar_matricula_texto(valor):
    texto = normalizar_texto(valor)

    if texto is None:
        return None

    if texto.endswith(".0"):
        try:
            texto = str(int(float(texto)))
        except Exception:
            pass

    return texto


def normalizar_numero_busca(valor):
    texto = normalizar_texto(valor)

    if texto is None:
        return None

    try:
        return int(float(texto))
    except Exception:
        return None


def normalizar_id_cracha(valor):
    return normalizar_numero_busca(valor)


def normalizar_quantidade(valor):
    texto = normalizar_texto(valor)

    if texto is None:
        return 0

    texto_upper = texto.upper()

    if texto_upper in [
        "SIM",
        "S",
        "YES",
        "X",
        "TRUE",
        "1",
    ]:
        return 1

    if texto_upper in [
        "NÃO",
        "NAO",
        "N",
        "NO",
        "FALSE",
        "0",
    ]:
        return 0

    try:
        return int(float(texto.replace(",", ".")))
    except Exception:
        return 0


# ============================================================
# VALIDAÇÕES
# ============================================================

def validar_colunas(df, colunas, nome_aba):
    erros = []

    for coluna in colunas:
        if coluna not in df.columns:
            erros.append(
                f'A aba "{nome_aba}" não possui a coluna obrigatória: {coluna}'
            )

    return erros


def verificar_duplicidade_id_mat(df):
    erros = []
    encontrados = {}

    for indice, linha in df.iterrows():
        id_mat = normalizar_id_cracha(
            linha.get("ID Mat")
        )

        matricula = normalizar_matricula_texto(
            linha.get("Mat")
        )

        if id_mat is None:
            continue

        if id_mat in encontrados:
            erros.append(
                "ID Mat duplicado na planilha: "
                f"{id_mat}. Matrículas envolvidas: "
                f"{encontrados[id_mat]} e {matricula}."
            )
        else:
            encontrados[id_mat] = matricula

    return erros


def verificar_conflitos_banco(registros, periodo_id):
    cliente = obter_supabase()

    erros = []
    mapa_id_matricula = {}

    for registro in registros:
        id_mat = registro.get("id_mat")

        if id_mat is None:
            continue

        mapa_id_matricula[id_mat] = registro.get("matricula")

    if not mapa_id_matricula:
        return erros

    ids = list(mapa_id_matricula.keys())
    existentes = []

    for lote in dividir_em_lotes(ids, 500):
        resposta = (
            cliente
            .table("colaboradores")
            .select("id,id_mat,matricula,nome,periodo_id")
            .eq("periodo_id", periodo_id)
            .in_("id_mat", lote)
            .execute()
        )

        existentes.extend(
            resposta.data or []
        )

    for existente in existentes:
        id_mat = existente.get("id_mat")

        matricula_existente = str(
            existente.get("matricula")
        )

        matricula_nova = str(
            mapa_id_matricula.get(id_mat)
        )

        if matricula_existente != matricula_nova:
            erros.append(
                "Conflito de crachá no período ativo: "
                f"ID Mat {id_mat} já pertence à matrícula "
                f"{matricula_existente} ({existente.get('nome')}) "
                f"e não pode ser usado para a matrícula {matricula_nova}."
            )

    return erros


# ============================================================
# PREPARAÇÃO DOS DADOS
# ============================================================

def preparar_colaboradores(df, periodo_id):
    registros = []
    erros = []

    for indice, linha in df.iterrows():
        matricula = normalizar_matricula_texto(
            linha.get("Mat")
        )

        if not matricula:
            continue

        registro = {
            "periodo_id": periodo_id,
            "id_mat": normalizar_id_cracha(
                linha.get("ID Mat")
            ),
            "matricula": matricula,
            "matricula_num": normalizar_numero_busca(
                linha.get("Mat")
            ),
            "nome": normalizar_texto(
                linha.get("Nome")
            ),
            "setor": normalizar_texto(
                linha.get("Setor")
            ),
            "cesta_normal": normalizar_quantidade(
                linha.get("Cesta Normal")
            ),
            "cesta_especial": normalizar_quantidade(
                linha.get("Cesta Especial")
            ),
            "perde": normalizar_texto(
                linha.get("Perde")
            ),
            "confirmacao_retirada": normalizar_texto(
                linha.get("Confirmação de retirada")
            ),
            "data_hora_retirada": normalizar_texto(
                linha.get("Data e Hora retirada")
            ),
        }

        registros.append(registro)

    return registros, erros


def preparar_demitidos(df, periodo_id):
    registros = []

    for indice, linha in df.iterrows():
        chapa = normalizar_matricula_texto(
            linha.get("CHAPA")
        )

        if not chapa:
            continue

        registro = {
            "periodo_id": periodo_id,
            "chapa": chapa,
            "chapa_num": normalizar_numero_busca(
                linha.get("CHAPA")
            ),
            "nome": normalizar_texto(
                linha.get("NOME")
            ),
            "retirado": normalizar_texto(
                linha.get("Retirado")
            ),
            "data_hora": normalizar_texto(
                linha.get("Data e Hora")
            ),
        }

        registros.append(registro)

    return registros


# ============================================================
# BUSCAS AUXILIARES
# ============================================================

def buscar_colaboradores_existentes_periodo(matriculas, periodo_id):
    cliente = obter_supabase()
    mapa = {}

    for lote in dividir_em_lotes(matriculas, 500):
        resposta = (
            cliente
            .table("colaboradores")
            .select(
                "id,matricula,id_mat,periodo_id,"
                "confirmacao_retirada,data_hora_retirada"
            )
            .eq("periodo_id", periodo_id)
            .in_("matricula", lote)
            .execute()
        )

        for registro in resposta.data or []:
            mapa[str(registro.get("matricula"))] = registro

    return mapa


def buscar_crachas_periodos_anteriores(matriculas, periodo_id):
    cliente = obter_supabase()
    mapa = {}

    for lote in dividir_em_lotes(matriculas, 500):
        resposta = (
            cliente
            .table("colaboradores")
            .select("matricula,id_mat,periodo_id")
            .lt("periodo_id", periodo_id)
            .not_.is_("id_mat", "null")
            .in_("matricula", lote)
            .order("periodo_id", desc=True)
            .execute()
        )

        for registro in resposta.data or []:
            matricula = str(registro.get("matricula"))

            if matricula not in mapa:
                mapa[matricula] = registro.get("id_mat")

    return mapa


# ============================================================
# GRAVAÇÃO EM LOTE
# ============================================================

def salvar_colaboradores(registros, periodo_id):
    """Grava a lista do período. Retorna um dicionário com os totais."""
    info = {
        "total": 0,
        "retiradas_preservadas": 0,
        "crachas_do_cadastro": 0,
        "crachas_duplicados_removidos": [],
    }

    if not registros:
        return info

    cliente = obter_supabase()

    matriculas = [
        registro["matricula"]
        for registro in registros
    ]

    existentes_periodo = buscar_colaboradores_existentes_periodo(
        matriculas,
        periodo_id,
    )

    crachas_anteriores = buscar_crachas_periodos_anteriores(
        matriculas,
        periodo_id,
    )

    cadastro_permanente = cadastro.mapa_por_matriculas(matriculas)

    payload = []
    origem_cracha = {}

    for registro in registros:
        item = dict(registro)

        matricula = str(
            item.get("matricula")
        )

        existente = existentes_periodo.get(
            matricula
        )

        permanente = cadastro_permanente.get(matricula) or {}

        # Prioridade do crachá:
        # 1. cadastro permanente do app (atualizado pelo terminal);
        # 2. crachá já gravado neste período;
        # 3. coluna ID Mat da planilha;
        # 4. crachá usado em período anterior.
        if permanente.get("id_cracha") is not None:
            item["id_mat"] = int(permanente["id_cracha"])
            origem_cracha[matricula] = "CADASTRO"
            info["crachas_do_cadastro"] += 1
        elif existente and existente.get("id_mat") is not None:
            item["id_mat"] = existente.get("id_mat")
            origem_cracha[matricula] = "PERIODO"
        elif item.get("id_mat") is not None:
            origem_cracha[matricula] = "PLANILHA"
        elif matricula in crachas_anteriores:
            item["id_mat"] = crachas_anteriores[matricula]
            origem_cracha[matricula] = "ANTERIOR"

        # Proteção contra reimportação no meio da entrega: se o banco já
        # registrou a retirada, a planilha nunca apaga essa informação.
        # Sem isso, quem já retirou voltava a ficar PENDENTE.
        if existente and normalizar_texto(
            existente.get("confirmacao_retirada")
        ):
            item["confirmacao_retirada"] = existente.get("confirmacao_retirada")
            item["data_hora_retirada"] = existente.get("data_hora_retirada")
            info["retiradas_preservadas"] += 1

        payload.append(item)

    # Um mesmo crachá não pode ficar com duas pessoas no período.
    # Fica com quem tem a origem mais confiável; os demais ficam sem crachá
    # e o terminal pedirá o cadastro quando digitarem a matrícula.
    prioridade = {"CADASTRO": 0, "PERIODO": 1, "PLANILHA": 2, "ANTERIOR": 3}
    donos = {}

    for item in payload:
        id_mat = item.get("id_mat")
        if id_mat is None:
            continue
        atual = donos.get(id_mat)
        p_item = prioridade.get(origem_cracha.get(str(item["matricula"])), 9)
        if atual is None or p_item < prioridade.get(
            origem_cracha.get(str(atual["matricula"])), 9
        ):
            donos[id_mat] = item

    for item in payload:
        id_mat = item.get("id_mat")
        if id_mat is not None and donos.get(id_mat) is not item:
            info["crachas_duplicados_removidos"].append(
                f"Crachá {id_mat} removido da matrícula {item['matricula']} "
                f"(já pertence à matrícula {donos[id_mat]['matricula']})."
            )
            item["id_mat"] = None

    for lote in dividir_em_lotes(payload, 500):
        (
            cliente
            .table("colaboradores")
            .upsert(
                lote,
                on_conflict="periodo_id,matricula",
            )
            .execute()
        )

        info["total"] += len(lote)

    return info


def salvar_demitidos(registros):
    if not registros:
        return 0

    cliente = obter_supabase()
    total = 0

    for lote in dividir_em_lotes(registros, 500):
        (
            cliente
            .table("demitidos")
            .upsert(
                lote,
                on_conflict="periodo_id,chapa",
            )
            .execute()
        )

        total += len(lote)

    return total


# ============================================================
# IMPORTAÇÃO PRINCIPAL
# ============================================================

def importar_excel(caminho_arquivo, usuario=None):
    resultado = {
        "colaboradores": 0,
        "demitidos": 0,
        "erros": [],
        "avisos": [],
        "retiradas_preservadas": 0,
        "crachas_do_cadastro": 0,
        "cadastro_sincronizado": 0,
    }

    try:
        periodo_id = obter_periodo_ativo_id()

        excel = pd.ExcelFile(
            caminho_arquivo
        )

        if ABA_COLABORADORES not in excel.sheet_names:
            resultado["erros"].append(
                f'A planilha não possui a aba "{ABA_COLABORADORES}".'
            )

        if ABA_DEMITIDOS not in excel.sheet_names:
            resultado["erros"].append(
                f'A planilha não possui a aba "{ABA_DEMITIDOS}".'
            )

        if resultado["erros"]:
            return resultado

        df_colaboradores = pd.read_excel(
            excel,
            sheet_name=ABA_COLABORADORES,
            dtype=str,
        )

        df_demitidos = pd.read_excel(
            excel,
            sheet_name=ABA_DEMITIDOS,
            dtype=str,
        )

        resultado["erros"].extend(
            validar_colunas(
                df_colaboradores,
                COLUNAS_COLABORADORES,
                ABA_COLABORADORES,
            )
        )

        resultado["erros"].extend(
            validar_colunas(
                df_demitidos,
                COLUNAS_DEMITIDOS,
                ABA_DEMITIDOS,
            )
        )

        if resultado["erros"]:
            return resultado

        resultado["erros"].extend(
            verificar_duplicidade_id_mat(
                df_colaboradores
            )
        )

        registros_colaboradores, erros_colaboradores = preparar_colaboradores(
            df_colaboradores,
            periodo_id,
        )

        resultado["erros"].extend(
            erros_colaboradores
        )

        resultado["erros"].extend(
            verificar_conflitos_banco(
                registros_colaboradores,
                periodo_id,
            )
        )

        if resultado["erros"]:
            return resultado

        registros_demitidos = preparar_demitidos(
            df_demitidos,
            periodo_id,
        )

        # Atualiza o cadastro permanente (nome/setor e crachás novos).
        try:
            resultado["cadastro_sincronizado"] = cadastro.sincronizar_da_planilha(
                registros_colaboradores,
                usuario=usuario,
            )
        except Exception as erro:
            resultado["avisos"].append(
                f"Cadastro permanente não foi atualizado: {erro}"
            )

        info = salvar_colaboradores(
            registros_colaboradores,
            periodo_id,
        )

        resultado["colaboradores"] = info["total"]
        resultado["retiradas_preservadas"] = info["retiradas_preservadas"]
        resultado["crachas_do_cadastro"] = info["crachas_do_cadastro"]
        resultado["avisos"].extend(info["crachas_duplicados_removidos"])

        resultado["demitidos"] = salvar_demitidos(
            registros_demitidos
        )

        return resultado

    except Exception as erro:
        resultado["erros"].append(
            f"Erro ao importar planilha: {erro}"
        )

        return resultado