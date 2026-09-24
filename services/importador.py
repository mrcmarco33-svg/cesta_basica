import pandas as pd

from database.database import conectar


# ============================================================
# CONFIGURAÇÕES
# ============================================================

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
# NORMALIZAÇÃO DO ID DO CRACHÁ
# ============================================================

def normalizar_id_cracha(valor):
    """
    ID Mat é tratado como número.

    Exemplos:

        123456        -> 123456
        123456.0      -> 123456
        "123456"      -> 123456
        "000123456"   -> 123456
        "000123456.0" -> 123456

    Os zeros à esquerda são ignorados.

    Valores vazios ou inválidos retornam None.
    """

    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    if not texto:
        return None

    try:
        numero = int(float(texto))
        return numero

    except (ValueError, TypeError):
        return None


# ============================================================
# NORMALIZAÇÃO DA MATRÍCULA
# ============================================================

def normalizar_matricula(valor):
    """
    Matrícula é armazenada como texto.

    Os zeros à esquerda são preservados no banco.

    Exemplo:

        000044 -> "000044"
        000169 -> "000169"
    """

    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    # Corrige casos em que o Excel/Pandas transforma
    # uma matrícula numérica em algo como 44.0
    if texto.endswith(".0"):

        parte_numerica = texto[:-2]

        if parte_numerica.isdigit():
            texto = parte_numerica

    return texto


# ============================================================
# NORMALIZAÇÃO DE QUANTIDADES
# ============================================================

def normalizar_quantidade(valor):
    """
    Converte quantidade para inteiro.

    Exemplos:

        1       -> 1
        1.0     -> 1
        "1"     -> 1
        "1.0"   -> 1
        vazio   -> 0
    """

    if valor is None:
        return 0

    try:
        if pd.isna(valor):
            return 0
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    if not texto:
        return 0

    try:
        return int(float(texto))

    except (ValueError, TypeError):
        return 0


# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================

def normalizar_texto(valor):
    """
    Converte qualquer valor para texto limpo.
    """

    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    return str(valor).strip()


# ============================================================
# VERIFICAR DUPLICIDADE DE ID MAT
# ============================================================

def verificar_duplicidade_id_mat(df):
    """
    Verifica se existem IDs de crachá duplicados
    dentro da própria planilha.

    A comparação ocorre depois da normalização.

    Portanto:

        000123456
        123456
        123456.0

    serão considerados o mesmo ID.

    Retorna uma lista de mensagens de erro.
    """

    erros = []

    ids = []

    for indice, linha in df.iterrows():

        id_mat = normalizar_id_cracha(
            linha["ID Mat"]
        )

        if id_mat is None:
            continue

        ids.append(
            {
                "indice": indice + 2,

                "id_mat": id_mat,

                "matricula": normalizar_matricula(
                    linha["Mat"]
                ),

                "nome": normalizar_texto(
                    linha["Nome"]
                ),
            }
        )

    if not ids:
        return erros

    df_ids = pd.DataFrame(ids)

    duplicados = df_ids[
        df_ids["id_mat"].duplicated(
            keep=False
        )
    ]

    if duplicados.empty:
        return erros

    erros.append(
        "Foram encontrados IDs de crachá duplicados "
        "após a normalização:"
    )

    for id_mat, grupo in duplicados.groupby(
        "id_mat"
    ):

        detalhes = []

        for _, registro in grupo.iterrows():

            detalhes.append(
                f"Linha {registro['indice']} | "
                f"Matrícula: {registro['matricula']} | "
                f"Nome: {registro['nome']}"
            )

        erros.append(
            f"ID Mat {id_mat} aparece em mais de um registro:\n"
            + "\n".join(detalhes)
        )

    return erros


# ============================================================
# VERIFICAR CONFLITOS COM O BANCO
# ============================================================

def verificar_conflitos_banco(
    conexao,
    registros
):
    """
    Verifica conflitos de ID de crachá.

    Se o ID já existir para a mesma matrícula:
        permitido.

    Se o ID já existir para outra matrícula:
        bloqueado.

    Isso evita que um crachá seja associado
    acidentalmente a duas pessoas.
    """

    erros = []

    for registro in registros:

        id_mat = registro["id_mat"]

        matricula = registro["matricula"]

        if id_mat is None:
            continue

        existente = conexao.execute(
            """
            SELECT
                id_mat,
                matricula,
                nome
            FROM colaboradores
            WHERE id_mat = ?
            """,
            (
                id_mat,
            )
        ).fetchone()

        if existente is None:
            continue

        matricula_existente = normalizar_matricula(
            existente["matricula"]
        )

        if matricula_existente != matricula:

            erros.append(
                "CONFLITO DE ID DE CRACHÁ: "
                f"ID Mat {id_mat} já está cadastrado "
                f"para a matrícula "
                f"{matricula_existente} "
                f"({existente['nome']}), "
                f"mas a planilha informa "
                f"a matrícula {matricula} "
                f"({registro['nome']})."
            )

    return erros


# ============================================================
# IMPORTAÇÃO PRINCIPAL
# ============================================================

def importar_excel(caminho_arquivo):

    resultado = {

        "colaboradores": 0,

        "demitidos": 0,

        "erros": [],
    }

    conexao = None

    try:

        # ====================================================
        # ABRIR ARQUIVO EXCEL
        # ====================================================

        excel = pd.ExcelFile(
            caminho_arquivo
        )

        abas = excel.sheet_names

        # ====================================================
        # VERIFICAR ABA DOS COLABORADORES
        # ====================================================

        if ABA_COLABORADORES not in abas:

            resultado["erros"].append(
                f'A aba "{ABA_COLABORADORES}" '
                "não foi encontrada."
            )

        # ====================================================
        # VERIFICAR ABA DOS DEMITIDOS
        # ====================================================

        if ABA_DEMITIDOS not in abas:

            resultado["erros"].append(
                f'A aba "{ABA_DEMITIDOS}" '
                "não foi encontrada."
            )

        if resultado["erros"]:

            return resultado

        # ====================================================
        # LER BANCO DE DADOS
        # ====================================================

        df_colaboradores = pd.read_excel(

            caminho_arquivo,

            sheet_name=ABA_COLABORADORES,

            dtype={
                "Mat": str
            }
        )

        # Limpar nomes das colunas

        df_colaboradores.columns = [

            str(coluna).strip()

            for coluna
            in df_colaboradores.columns

        ]

        # ====================================================
        # VALIDAR COLUNAS DOS COLABORADORES
        # ====================================================

        colunas_faltantes = [

            coluna

            for coluna
            in COLUNAS_COLABORADORES

            if coluna
            not in df_colaboradores.columns

        ]

        if colunas_faltantes:

            resultado["erros"].append(

                f'Colunas faltantes na aba '
                f'"{ABA_COLABORADORES}": '
                + ", ".join(
                    colunas_faltantes
                )
            )

        # ====================================================
        # LER DEMITIDOS
        # ====================================================

        df_demitidos = pd.read_excel(

            caminho_arquivo,

            sheet_name=ABA_DEMITIDOS,

            dtype={
                "CHAPA": str
            }
        )

        # Limpar nomes das colunas

        df_demitidos.columns = [

            str(coluna).strip()

            for coluna
            in df_demitidos.columns

        ]

        # ====================================================
        # VALIDAR COLUNAS DOS DEMITIDOS
        # ====================================================

        colunas_faltantes_demitidos = [

            coluna

            for coluna
            in COLUNAS_DEMITIDOS

            if coluna
            not in df_demitidos.columns

        ]

        if colunas_faltantes_demitidos:

            resultado["erros"].append(

                f'Colunas faltantes na aba '
                f'"{ABA_DEMITIDOS}": '

                + ", ".join(
                    colunas_faltantes_demitidos
                )
            )

        if resultado["erros"]:

            return resultado

        # ====================================================
        # VALIDAR DUPLICIDADE DE ID MAT
        # ====================================================

        erros_duplicidade = (

            verificar_duplicidade_id_mat(
                df_colaboradores
            )

        )

        if erros_duplicidade:

            resultado["erros"].extend(
                erros_duplicidade
            )

            return resultado

        # ====================================================
        # PREPARAR COLABORADORES
        # ====================================================

        registros_colaboradores = []

        for _, linha in df_colaboradores.iterrows():

            id_mat = normalizar_id_cracha(
                linha["ID Mat"]
            )

            matricula = normalizar_matricula(
                linha["Mat"]
            )

            nome = normalizar_texto(
                linha["Nome"]
            )

            setor = normalizar_texto(
                linha["Setor"]
            )

            cesta_normal = normalizar_quantidade(
                linha["Cesta Normal"]
            )

            cesta_especial = normalizar_quantidade(
                linha["Cesta Especial"]
            )

            perde = normalizar_texto(
                linha["Perde"]
            )

            confirmacao = normalizar_texto(
                linha[
                    "Confirmação de retirada"
                ]
            )

            data_retirada = normalizar_texto(
                linha[
                    "Data e Hora retirada"
                ]
            )

            # =================================================
            # MATRÍCULA É O IDENTIFICADOR OBRIGATÓRIO
            # =================================================

            if not matricula:
                continue

            registros_colaboradores.append(

                {
                    "id_mat": id_mat,

                    "matricula": matricula,

                    "nome": nome,

                    "setor": setor,

                    "cesta_normal":
                        cesta_normal,

                    "cesta_especial":
                        cesta_especial,

                    "perde": perde,

                    "confirmacao":
                        confirmacao,

                    "data_retirada":
                        data_retirada,
                }

            )

        # ====================================================
        # CONECTAR AO BANCO
        # ====================================================

        conexao = conectar()

        # ====================================================
        # VERIFICAR CONFLITOS
        # ====================================================

        erros_banco = (

            verificar_conflitos_banco(

                conexao,

                registros_colaboradores
            )

        )

        if erros_banco:

            resultado["erros"].extend(
                erros_banco
            )

            return resultado

        cursor = conexao.cursor()

        # ====================================================
        # IMPORTAR COLABORADORES
        # ====================================================

        for registro in registros_colaboradores:

            # ------------------------------------------------
            # PRIMEIRO:
            # verificar se a matrícula já existe
            # ------------------------------------------------

            existente = cursor.execute(
                """
                SELECT id
                FROM colaboradores
                WHERE matricula = ?
                LIMIT 1
                """,
                (
                    registro["matricula"],
                )
            ).fetchone()

            if existente:

                # --------------------------------------------
                # ATUALIZAR
                # --------------------------------------------

                cursor.execute(
                    """
                    UPDATE colaboradores

                    SET
                        id_mat = ?,
                        nome = ?,
                        setor = ?,
                        cesta_normal = ?,
                        cesta_especial = ?,
                        perde = ?,
                        confirmacao_retirada = ?,
                        data_hora_retirada = ?

                    WHERE id = ?
                    """,

                    (
                        registro["id_mat"],

                        registro["nome"],

                        registro["setor"],

                        registro["cesta_normal"],

                        registro["cesta_especial"],

                        registro["perde"],

                        registro["confirmacao"],

                        registro["data_retirada"],

                        existente["id"],
                    )
                )

            else:

                # --------------------------------------------
                # NOVO CADASTRO
                # --------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO colaboradores (

                        id_mat,

                        matricula,

                        nome,

                        setor,

                        cesta_normal,

                        cesta_especial,

                        perde,

                        confirmacao_retirada,

                        data_hora_retirada

                    )

                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,

                    (
                        registro["id_mat"],

                        registro["matricula"],

                        registro["nome"],

                        registro["setor"],

                        registro["cesta_normal"],

                        registro["cesta_especial"],

                        registro["perde"],

                        registro["confirmacao"],

                        registro["data_retirada"],
                    )
                )

            resultado["colaboradores"] += 1

        # ====================================================
        # IMPORTAR DEMITIDOS
        # ====================================================

        for _, linha in df_demitidos.iterrows():

            chapa = normalizar_matricula(
                linha["CHAPA"]
            )

            if not chapa:
                continue

            nome = normalizar_texto(
                linha["NOME"]
            )

            retirado = normalizar_texto(
                linha["Retirado"]
            )

            data_hora = normalizar_texto(
                linha["Data e Hora"]
            )

            # ------------------------------------------------
            # VERIFICAR SE JÁ EXISTE
            # ------------------------------------------------

            existente = cursor.execute(
                """
                SELECT id
                FROM demitidos
                WHERE chapa = ?
                LIMIT 1
                """,
                (
                    chapa,
                )
            ).fetchone()

            if existente:

                # --------------------------------------------
                # ATUALIZAR
                # --------------------------------------------

                cursor.execute(
                    """
                    UPDATE demitidos

                    SET
                        nome = ?,
                        retirado = ?,
                        data_hora = ?

                    WHERE id = ?
                    """,

                    (
                        nome,

                        retirado,

                        data_hora,

                        existente["id"],
                    )
                )

            else:

                # --------------------------------------------
                # NOVO DEMITIDO
                # --------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO demitidos (

                        chapa,

                        nome,

                        retirado,

                        data_hora

                    )

                    VALUES (?, ?, ?, ?)
                    """,

                    (
                        chapa,

                        nome,

                        retirado,

                        data_hora,
                    )
                )

            resultado["demitidos"] += 1

        # ====================================================
        # FINALIZAR
        # ====================================================

        conexao.commit()

    except Exception as erro:

        if conexao is not None:

            conexao.rollback()

        resultado["erros"].append(

            f"Erro durante a importação: {erro}"

        )

    finally:

        if conexao is not None:

            conexao.close()

    return resultado