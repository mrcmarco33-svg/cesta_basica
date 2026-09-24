import sqlite3
from pathlib import Path
from datetime import datetime


# ============================================================
# CAMINHOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

DB_PATH = DATA_DIR / "cestas.db"


# ============================================================
# CONEXÃO
# ============================================================

def conectar():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    conexao = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    conexao.row_factory = sqlite3.Row

    return conexao


# ============================================================
# DATA / HORA
# ============================================================

def agora():

    return datetime.now().strftime(
        "%d/%m/%Y %H:%M:%S"
    )


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

def inicializar_banco():

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        # ====================================================
        # COLABORADORES
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS colaboradores (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                id_mat INTEGER UNIQUE,

                matricula TEXT UNIQUE NOT NULL,

                nome TEXT NOT NULL,

                setor TEXT,

                cesta_normal INTEGER DEFAULT 0,

                cesta_especial INTEGER DEFAULT 0,

                perde TEXT,

                confirmacao_retirada TEXT,

                data_hora_retirada TEXT

            )
        """)

        # ====================================================
        # DEMITIDOS
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demitidos (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                chapa TEXT UNIQUE NOT NULL,

                nome TEXT NOT NULL,

                retirado TEXT,

                data_hora TEXT

            )
        """)

        # ====================================================
        # ESTOQUE
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estoque (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                cesta_normal INTEGER DEFAULT 0,

                cesta_especial INTEGER DEFAULT 0,

                data_atualizacao TEXT

            )
        """)

        # ====================================================
        # HISTÓRICO
        # ====================================================

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                data_hora TEXT NOT NULL,

                tipo_identificacao TEXT,

                id_cracha INTEGER,

                matricula TEXT,

                nome TEXT,

                setor TEXT,

                cesta_normal INTEGER DEFAULT 0,

                cesta_especial INTEGER DEFAULT 0,

                resultado TEXT,

                motivo TEXT,

                estoque_normal_antes INTEGER,

                estoque_normal_depois INTEGER,

                estoque_especial_antes INTEGER,

                estoque_especial_depois INTEGER

            )
        """)

        # ====================================================
        # ESTOQUE INICIAL
        # ====================================================

        estoque = cursor.execute("""
            SELECT id
            FROM estoque
            ORDER BY id
            LIMIT 1
        """).fetchone()

        if estoque is None:

            cursor.execute("""
                INSERT INTO estoque (
                    cesta_normal,
                    cesta_especial,
                    data_atualizacao
                )
                VALUES (?, ?, ?)
            """, (
                0,
                0,
                agora()
            ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# ESTOQUE
# ============================================================

def obter_estoque():

    conexao = conectar()

    try:

        return conexao.execute("""
            SELECT *
            FROM estoque
            ORDER BY id
            LIMIT 1
        """).fetchone()

    finally:

        conexao.close()


def configurar_estoque(
    cesta_normal,
    cesta_especial
):

    cesta_normal = int(cesta_normal)

    cesta_especial = int(cesta_especial)

    if cesta_normal < 0:

        raise ValueError(
            "A quantidade de cestas normais "
            "não pode ser negativa."
        )

    if cesta_especial < 0:

        raise ValueError(
            "A quantidade de cestas especiais "
            "não pode ser negativa."
        )

    conexao = conectar()

    try:

        conexao.execute("""
            UPDATE estoque

            SET
                cesta_normal = ?,
                cesta_especial = ?,
                data_atualizacao = ?

            WHERE id = (
                SELECT id
                FROM estoque
                ORDER BY id
                LIMIT 1
            )
        """, (
            cesta_normal,
            cesta_especial,
            agora()
        ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# HISTÓRICO
# ============================================================

def registrar_historico(
    data_hora,
    tipo_identificacao,
    id_cracha,
    matricula,
    nome,
    setor,
    cesta_normal,
    cesta_especial,
    resultado,
    motivo,
    estoque_normal_antes=None,
    estoque_normal_depois=None,
    estoque_especial_antes=None,
    estoque_especial_depois=None
):

    conexao = conectar()

    try:

        conexao.execute("""
            INSERT INTO historico (

                data_hora,
                tipo_identificacao,
                id_cracha,
                matricula,
                nome,
                setor,
                cesta_normal,
                cesta_especial,
                resultado,
                motivo,
                estoque_normal_antes,
                estoque_normal_depois,
                estoque_especial_antes,
                estoque_especial_depois

            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            data_hora,
            tipo_identificacao,
            id_cracha,
            matricula,
            nome,
            setor,
            cesta_normal,
            cesta_especial,
            resultado,
            motivo,
            estoque_normal_antes,
            estoque_normal_depois,
            estoque_especial_antes,
            estoque_especial_depois

        ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# TENTATIVA NÃO ENCONTRADA
# ============================================================

def registrar_tentativa_nao_encontrada(
    identificacao
):

    conexao = conectar()

    try:

        identificacao = str(
            identificacao
        ).strip()

        conexao.execute("""
            INSERT INTO historico (

                data_hora,
                tipo_identificacao,
                id_cracha,
                matricula,
                nome,
                setor,
                cesta_normal,
                cesta_especial,
                resultado,
                motivo

            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            agora(),

            "NÃO IDENTIFICADO",

            None,

            identificacao,

            None,

            None,

            0,

            0,

            "NAO_ENCONTRADO",

            "ID do crachá ou matrícula não encontrado."

        ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# LIBERAÇÃO DA CESTA
# ============================================================

def liberar_cesta(
    colaborador_id,
    tipo_identificacao
):

    conexao = conectar()

    try:

        cursor = conexao.cursor()

        # ====================================================
        # LOCALIZAR COLABORADOR
        # ====================================================

        colaborador = cursor.execute("""
            SELECT *
            FROM colaboradores
            WHERE id = ?
            LIMIT 1
        """, (
            colaborador_id,
        )).fetchone()

        if colaborador is None:

            return {
                "sucesso": False,
                "resultado": "ERRO",
                "motivo": "Colaborador não encontrado."
            }

        # ====================================================
        # PERDE
        # ====================================================

        if colaborador["perde"]:

            motivo = colaborador["perde"]

            cursor.execute("""
                INSERT INTO historico (

                    data_hora,
                    tipo_identificacao,
                    id_cracha,
                    matricula,
                    nome,
                    setor,
                    cesta_normal,
                    cesta_especial,
                    resultado,
                    motivo

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                agora(),

                tipo_identificacao,

                colaborador["id_mat"],

                colaborador["matricula"],

                colaborador["nome"],

                colaborador["setor"],

                colaborador["cesta_normal"],

                colaborador["cesta_especial"],

                "NEGADO",

                motivo

            ))

            conexao.commit()

            return {
                "sucesso": False,
                "resultado": "NEGADO",
                "motivo": motivo
            }

        # ====================================================
        # RETIRADA DUPLICADA
        # ====================================================

        if colaborador["confirmacao_retirada"]:

            data_anterior = (
                colaborador["data_hora_retirada"]
                or "data não informada"
            )

            motivo = (
                "Retirada já realizada em "
                f"{data_anterior}."
            )

            cursor.execute("""
                INSERT INTO historico (

                    data_hora,
                    tipo_identificacao,
                    id_cracha,
                    matricula,
                    nome,
                    setor,
                    cesta_normal,
                    cesta_especial,
                    resultado,
                    motivo

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                agora(),

                tipo_identificacao,

                colaborador["id_mat"],

                colaborador["matricula"],

                colaborador["nome"],

                colaborador["setor"],

                colaborador["cesta_normal"],

                colaborador["cesta_especial"],

                "DUPLICADO",

                motivo

            ))

            conexao.commit()

            return {
                "sucesso": False,
                "resultado": "DUPLICADO",
                "motivo": motivo
            }

        # ====================================================
        # QUANTIDADES
        # ====================================================

        cesta_normal = int(
            colaborador["cesta_normal"] or 0
        )

        cesta_especial = int(
            colaborador["cesta_especial"] or 0
        )

        # ====================================================
        # NENHUMA CESTA
        # ====================================================

        if cesta_normal <= 0 and cesta_especial <= 0:

            motivo = (
                "Colaborador não possui "
                "cesta normal ou especial."
            )

            cursor.execute("""
                INSERT INTO historico (

                    data_hora,
                    tipo_identificacao,
                    id_cracha,
                    matricula,
                    nome,
                    setor,
                    cesta_normal,
                    cesta_especial,
                    resultado,
                    motivo

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                agora(),

                tipo_identificacao,

                colaborador["id_mat"],

                colaborador["matricula"],

                colaborador["nome"],

                colaborador["setor"],

                0,

                0,

                "NEGADO",

                motivo

            ))

            conexao.commit()

            return {
                "sucesso": False,
                "resultado": "NEGADO",
                "motivo": motivo
            }

        # ====================================================
        # ESTOQUE
        # ====================================================

        estoque = cursor.execute("""
            SELECT *
            FROM estoque
            ORDER BY id
            LIMIT 1
        """).fetchone()

        if estoque is None:

            raise Exception(
                "Registro de estoque não encontrado."
            )

        normal_antes = int(
            estoque["cesta_normal"] or 0
        )

        especial_antes = int(
            estoque["cesta_especial"] or 0
        )

        # ====================================================
        # VALIDAR ESTOQUE NORMAL
        # ====================================================

        if cesta_normal > normal_antes:

            motivo = (
                "Estoque insuficiente de "
                "cestas normais."
            )

            cursor.execute("""
                INSERT INTO historico (

                    data_hora,
                    tipo_identificacao,
                    id_cracha,
                    matricula,
                    nome,
                    setor,
                    cesta_normal,
                    cesta_especial,
                    resultado,
                    motivo,
                    estoque_normal_antes,
                    estoque_normal_depois,
                    estoque_especial_antes,
                    estoque_especial_depois

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                agora(),

                tipo_identificacao,

                colaborador["id_mat"],

                colaborador["matricula"],

                colaborador["nome"],

                colaborador["setor"],

                cesta_normal,

                cesta_especial,

                "SEM_ESTOQUE",

                motivo,

                normal_antes,

                normal_antes,

                especial_antes,

                especial_antes

            ))

            conexao.commit()

            return {
                "sucesso": False,
                "resultado": "SEM_ESTOQUE",
                "motivo": motivo
            }

        # ====================================================
        # VALIDAR ESTOQUE ESPECIAL
        # ====================================================

        if cesta_especial > especial_antes:

            motivo = (
                "Estoque insuficiente de "
                "cestas especiais."
            )

            cursor.execute("""
                INSERT INTO historico (

                    data_hora,
                    tipo_identificacao,
                    id_cracha,
                    matricula,
                    nome,
                    setor,
                    cesta_normal,
                    cesta_especial,
                    resultado,
                    motivo,
                    estoque_normal_antes,
                    estoque_normal_depois,
                    estoque_especial_antes,
                    estoque_especial_depois

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                agora(),

                tipo_identificacao,

                colaborador["id_mat"],

                colaborador["matricula"],

                colaborador["nome"],

                colaborador["setor"],

                cesta_normal,

                cesta_especial,

                "SEM_ESTOQUE",

                motivo,

                normal_antes,

                normal_antes,

                especial_antes,

                especial_antes

            ))

            conexao.commit()

            return {
                "sucesso": False,
                "resultado": "SEM_ESTOQUE",
                "motivo": motivo
            }

        # ====================================================
        # NOVO ESTOQUE
        # ====================================================

        normal_depois = (
            normal_antes - cesta_normal
        )

        especial_depois = (
            especial_antes - cesta_especial
        )

        data_retirada = agora()

        # ====================================================
        # ATUALIZAR ESTOQUE
        # ====================================================

        cursor.execute("""
            UPDATE estoque

            SET
                cesta_normal = ?,
                cesta_especial = ?,
                data_atualizacao = ?

            WHERE id = ?
        """, (

            normal_depois,

            especial_depois,

            data_retirada,

            estoque["id"]

        ))

        # ====================================================
        # REGISTRAR RETIRADA
        # ====================================================

        cursor.execute("""
            UPDATE colaboradores

            SET
                confirmacao_retirada = ?,
                data_hora_retirada = ?

            WHERE id = ?
        """, (

            "SIM",

            data_retirada,

            colaborador["id"]

        ))

        # ====================================================
        # HISTÓRICO
        # ====================================================

        cursor.execute("""
            INSERT INTO historico (

                data_hora,
                tipo_identificacao,
                id_cracha,
                matricula,
                nome,
                setor,
                cesta_normal,
                cesta_especial,
                resultado,
                motivo,
                estoque_normal_antes,
                estoque_normal_depois,
                estoque_especial_antes,
                estoque_especial_depois

            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            data_retirada,

            tipo_identificacao,

            colaborador["id_mat"],

            colaborador["matricula"],

            colaborador["nome"],

            colaborador["setor"],

            cesta_normal,

            cesta_especial,

            "LIBERADO",

            "Retirada realizada com sucesso.",

            normal_antes,

            normal_depois,

            especial_antes,

            especial_depois

        ))

        conexao.commit()

        return {

            "sucesso": True,

            "resultado": "LIBERADO",

            "data_hora": data_retirada,

            "cesta_normal": cesta_normal,

            "cesta_especial": cesta_especial,

            "estoque_normal_antes": normal_antes,

            "estoque_normal_depois": normal_depois,

            "estoque_especial_antes": especial_antes,

            "estoque_especial_depois": especial_depois

        }

    except Exception as erro:

        conexao.rollback()

        return {

            "sucesso": False,

            "resultado": "ERRO",

            "motivo": str(erro)

        }

    finally:

        conexao.close()


# ============================================================
# OBTER HISTÓRICO
# ============================================================

def obter_historico(
    limite=5000
):

    conexao = conectar()

    try:

        return conexao.execute("""
            SELECT *
            FROM historico
            ORDER BY id DESC
            LIMIT ?
        """, (
            limite,
        )).fetchall()

    finally:

        conexao.close()


# ============================================================
# INDICADORES
# ============================================================

def obter_indicadores():

    conexao = conectar()

    try:

        liberadas = conexao.execute("""
            SELECT COUNT(*)
            FROM historico
            WHERE resultado = 'LIBERADO'
        """).fetchone()[0]

        negadas = conexao.execute("""
            SELECT COUNT(*)
            FROM historico
            WHERE resultado = 'NEGADO'
        """).fetchone()[0]

        duplicadas = conexao.execute("""
            SELECT COUNT(*)
            FROM historico
            WHERE resultado = 'DUPLICADO'
        """).fetchone()[0]

        nao_encontradas = conexao.execute("""
            SELECT COUNT(*)
            FROM historico
            WHERE resultado = 'NAO_ENCONTRADO'
        """).fetchone()[0]

        sem_estoque = conexao.execute("""
            SELECT COUNT(*)
            FROM historico
            WHERE resultado = 'SEM_ESTOQUE'
        """).fetchone()[0]

        cestas_normais = conexao.execute("""
            SELECT COALESCE(
                SUM(cesta_normal),
                0
            )
            FROM historico
            WHERE resultado = 'LIBERADO'
        """).fetchone()[0]

        cestas_especiais = conexao.execute("""
            SELECT COALESCE(
                SUM(cesta_especial),
                0
            )
            FROM historico
            WHERE resultado = 'LIBERADO'
        """).fetchone()[0]

        tentativas = conexao.execute("""
            SELECT COUNT(*)
            FROM historico
        """).fetchone()[0]

        return {

            "liberadas": liberadas,

            "negadas": negadas,

            "duplicadas": duplicadas,

            "nao_encontradas":
                nao_encontradas,

            "sem_estoque":
                sem_estoque,

            "cestas_normais":
                cestas_normais,

            "cestas_especiais":
                cestas_especiais,

            "tentativas":
                tentativas

        }

    finally:

        conexao.close()