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
        exist_ok=True
    )

    conexao = sqlite3.connect(
        DB_PATH
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
# INICIALIZAÇÃO
# ============================================================

def inicializar_banco():

    conexao = conectar()

    cursor = conexao.cursor()

    # ========================================================
    # COLABORADORES
    # ========================================================

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

    # ========================================================
    # DEMITIDOS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS demitidos (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            chapa TEXT UNIQUE NOT NULL,

            nome TEXT NOT NULL,

            retirado TEXT,

            data_hora TEXT

        )
    """)

    # ========================================================
    # ESTOQUE
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            cesta_normal INTEGER DEFAULT 0,

            cesta_especial INTEGER DEFAULT 0,

            data_atualizacao TEXT

        )
    """)

    # ========================================================
    # HISTÓRICO
    # ========================================================

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

    # ========================================================
    # PERÍODOS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS periodos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            data_inicio TEXT,
            data_fim TEXT,
            status TEXT NOT NULL DEFAULT 'ABERTO',
            data_criacao TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS colaboradores_periodos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo_id INTEGER NOT NULL,
            id_original INTEGER,
            id_mat INTEGER,
            matricula TEXT NOT NULL,
            nome TEXT NOT NULL,
            setor TEXT,
            cesta_normal INTEGER DEFAULT 0,
            cesta_especial INTEGER DEFAULT 0,
            perde TEXT,
            confirmacao_retirada TEXT,
            data_hora_retirada TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS demitidos_periodos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo_id INTEGER NOT NULL,
            id_original INTEGER,
            chapa TEXT NOT NULL,
            nome TEXT NOT NULL,
            retirado TEXT,
            data_hora TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque_periodos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo_id INTEGER NOT NULL UNIQUE,
            cesta_normal INTEGER DEFAULT 0,
            cesta_especial INTEGER DEFAULT 0,
            data_atualizacao TEXT
        )
    """)

    def adicionar_coluna_se_nao_existir(tabela, coluna, definicao):
        colunas = [row[1] for row in cursor.execute(f"PRAGMA table_info({tabela})").fetchall()]
        if coluna not in colunas:
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")

    adicionar_coluna_se_nao_existir("colaboradores", "periodo_id", "INTEGER")
    adicionar_coluna_se_nao_existir("demitidos", "periodo_id", "INTEGER")
    adicionar_coluna_se_nao_existir("estoque", "periodo_id", "INTEGER")
    adicionar_coluna_se_nao_existir("historico", "periodo_id", "INTEGER")

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS historico_periodo_automatico
        AFTER INSERT ON historico
        WHEN NEW.periodo_id IS NULL
        BEGIN
            UPDATE historico
            SET periodo_id = (SELECT id FROM periodos WHERE status='ABERTO' ORDER BY id DESC LIMIT 1)
            WHERE id = NEW.id;
        END;
    """)

    # ========================================================
    # ESTOQUE INICIAL
    # ========================================================

    estoque = cursor.execute("""
        SELECT id
        FROM estoque
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

    # --------------------------------------------------------
    # MIGRAÇÃO INICIAL: cria um período para os dados antigos.
    # --------------------------------------------------------
    periodo = cursor.execute("SELECT * FROM periodos ORDER BY id LIMIT 1").fetchone()
    if periodo is None:
        cursor.execute("""
            INSERT INTO periodos (nome, data_inicio, status, data_criacao)
            VALUES (?, ?, 'ABERTO', ?)
        """, ("Período legado / atual", datetime.now().strftime("%d/%m/%Y"), agora()))
        periodo_id = cursor.lastrowid
    else:
        periodo_id = periodo["id"]

    cursor.execute("UPDATE colaboradores SET periodo_id = ? WHERE periodo_id IS NULL", (periodo_id,))
    cursor.execute("UPDATE demitidos SET periodo_id = ? WHERE periodo_id IS NULL", (periodo_id,))
    cursor.execute("UPDATE historico SET periodo_id = ? WHERE periodo_id IS NULL", (periodo_id,))
    cursor.execute("UPDATE estoque SET periodo_id = ? WHERE periodo_id IS NULL", (periodo_id,))

    estoque_atual = cursor.execute("SELECT * FROM estoque ORDER BY id LIMIT 1").fetchone()
    if estoque_atual is not None:
        cursor.execute("""
            INSERT OR IGNORE INTO estoque_periodos
            (periodo_id, cesta_normal, cesta_especial, data_atualizacao)
            VALUES (?, ?, ?, ?)
        """, (periodo_id, estoque_atual["cesta_normal"], estoque_atual["cesta_especial"], estoque_atual["data_atualizacao"]))

    conexao.commit()

    conexao.close()


# ============================================================
# PERÍODOS
# ============================================================

def obter_periodos():
    conexao = conectar()
    try:
        return conexao.execute("SELECT * FROM periodos ORDER BY id DESC").fetchall()
    finally:
        conexao.close()


def obter_periodo_atual():
    conexao = conectar()
    try:
        return conexao.execute("SELECT * FROM periodos WHERE status = 'ABERTO' ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conexao.close()


def obter_periodo_ativo_id():
    """Compatibilidade com versões do importador que esperam apenas o ID do período ativo."""
    periodo = obter_periodo_atual()
    if periodo is None:
        return None
    return int(periodo["id"])


def obter_periodo(periodo_id):
    conexao = conectar()
    try:
        return conexao.execute("SELECT * FROM periodos WHERE id = ?", (int(periodo_id),)).fetchone()
    finally:
        conexao.close()


def criar_periodo(nome, data_inicio=None, data_fim=None):
    nome = str(nome or '').strip()
    if not nome:
        raise ValueError('Informe o nome do período.')

    conexao = conectar()
    try:
        atual = conexao.execute("SELECT * FROM periodos WHERE status = 'ABERTO' ORDER BY id DESC LIMIT 1").fetchone()
        if atual is not None:
            raise ValueError(f'Já existe um período aberto: {atual["nome"]}. Encerre-o antes de criar outro.')

        conexao.execute("""
            INSERT INTO periodos (nome, data_inicio, data_fim, status, data_criacao)
            VALUES (?, ?, ?, 'ABERTO', ?)
        """, (nome, data_inicio, data_fim, agora()))
        periodo_id = conexao.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Guarda um retrato do período anterior antes de limpar o cadastro ativo.
        anterior = conexao.execute("SELECT * FROM periodos WHERE id < ? ORDER BY id DESC LIMIT 1", (periodo_id,)).fetchone()
        if anterior is not None:
            old_id = anterior['id']
            qtd = conexao.execute("SELECT COUNT(*) FROM colaboradores_periodos WHERE periodo_id = ?", (old_id,)).fetchone()[0]
            if qtd == 0:
                rows = conexao.execute("SELECT * FROM colaboradores WHERE periodo_id = ? OR periodo_id IS NULL", (old_id,)).fetchall()
                for r in rows:
                    conexao.execute("""INSERT INTO colaboradores_periodos
                        (periodo_id,id_original,id_mat,matricula,nome,setor,cesta_normal,cesta_especial,perde,confirmacao_retirada,data_hora_retirada)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (old_id,r['id'],r['id_mat'],r['matricula'],r['nome'],r['setor'],r['cesta_normal'],r['cesta_especial'],r['perde'],r['confirmacao_retirada'],r['data_hora_retirada']))
                rowsd = conexao.execute("SELECT * FROM demitidos WHERE periodo_id = ? OR periodo_id IS NULL", (old_id,)).fetchall()
                for r in rowsd:
                    conexao.execute("""INSERT INTO demitidos_periodos
                        (periodo_id,id_original,chapa,nome,retirado,data_hora) VALUES (?,?,?,?,?,?)""", (old_id,r['id'],r['chapa'],r['nome'],r['retirado'],r['data_hora']))
                stock = conexao.execute("SELECT * FROM estoque WHERE id = (SELECT id FROM estoque ORDER BY id LIMIT 1)").fetchone()
                if stock is not None:
                    conexao.execute("""INSERT OR REPLACE INTO estoque_periodos
                        (periodo_id,cesta_normal,cesta_especial,data_atualizacao) VALUES (?,?,?,?)""", (old_id,stock['cesta_normal'],stock['cesta_especial'],stock['data_atualizacao']))

        conexao.execute("DELETE FROM colaboradores")
        conexao.execute("DELETE FROM demitidos")
        conexao.execute("""UPDATE estoque SET cesta_normal=0,cesta_especial=0,data_atualizacao=?,periodo_id=?
                           WHERE id=(SELECT id FROM estoque ORDER BY id LIMIT 1)""", (agora(), periodo_id))
        conexao.commit()
        return periodo_id
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def encerrar_periodo(periodo_id):
    conexao = conectar()
    try:
        periodo = conexao.execute("SELECT * FROM periodos WHERE id = ?", (int(periodo_id),)).fetchone()
        if periodo is None:
            raise ValueError('Período não encontrado.')
        if periodo['status'] == 'ENCERRADO':
            return
        conexao.execute("UPDATE periodos SET status='ENCERRADO', data_fim=COALESCE(data_fim, ?) WHERE id=?", (datetime.now().strftime('%d/%m/%Y'), int(periodo_id)))
        conexao.commit()
    finally:
        conexao.close()


def preparar_periodo_para_importacao(periodo_id):
    conexao = conectar()
    try:
        p = conexao.execute("SELECT * FROM periodos WHERE id=?", (int(periodo_id),)).fetchone()
        if p is None or p['status'] != 'ABERTO':
            raise ValueError('O período selecionado não está aberto.')
        atual = conexao.execute("SELECT periodo_id FROM colaboradores LIMIT 1").fetchone()
        if atual is not None and atual['periodo_id'] != int(periodo_id):
            raise ValueError('O período selecionado não é o período ativo.')
    finally:
        conexao.close()


def obter_estoque():

    conexao = conectar()

    try:

        estoque = conexao.execute("""
            SELECT *
            FROM estoque
            ORDER BY id
            LIMIT 1
        """).fetchone()

        return estoque

    finally:

        conexao.close()


def configurar_estoque(
    cesta_normal,
    cesta_especial
):

    cesta_normal = int(
        cesta_normal
    )

    cesta_especial = int(
        cesta_especial
    )

    if cesta_normal < 0:

        raise ValueError(
            "A quantidade de cesta normal "
            "não pode ser negativa."
        )

    if cesta_especial < 0:

        raise ValueError(
            "A quantidade de cesta especial "
            "não pode ser negativa."
        )

    conexao = conectar()

    try:

        periodo = conexao.execute("SELECT id FROM periodos WHERE status='ABERTO' ORDER BY id DESC LIMIT 1").fetchone()
        periodo_id = periodo["id"] if periodo else None
        conexao.execute("""
            UPDATE estoque
            SET
                cesta_normal = ?,
                cesta_especial = ?,
                data_atualizacao = ?,
                periodo_id = ?
            WHERE id = (
                SELECT id
                FROM estoque
                ORDER BY id
                LIMIT 1
            )
        """, (
            cesta_normal,
            cesta_especial,
            agora(),
            periodo_id
        ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# REGISTRAR HISTÓRICO
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
    estoque_especial_depois=None,
    periodo_id=None,
):
    """Registra uma operação vinculada ao período aberto atual."""
    conexao = conectar()

    try:
        if periodo_id is None:
            periodo = conexao.execute(
                "SELECT id FROM periodos WHERE status='ABERTO' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            periodo_id = periodo["id"] if periodo else None

        conexao.execute("""
            INSERT INTO historico (
                data_hora, tipo_identificacao, id_cracha, matricula,
                nome, setor, cesta_normal, cesta_especial, resultado, motivo,
                estoque_normal_antes, estoque_normal_depois,
                estoque_especial_antes, estoque_especial_depois, periodo_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data_hora, tipo_identificacao, id_cracha, matricula, nome, setor,
            cesta_normal, cesta_especial, resultado, motivo,
            estoque_normal_antes, estoque_normal_depois,
            estoque_especial_antes, estoque_especial_depois, periodo_id,
        ))
        conexao.commit()
    finally:
        conexao.close()


# ============================================================
# TENTATIVA NÃO ENCONTRADA
# ============================================================

def registrar_tentativa_nao_encontrada(
    identificacao,
    periodo_id=None,
):
    """Registra uma identificação não encontrada no período atual."""
    conexao = conectar()

    try:
        if periodo_id is None:
            periodo = conexao.execute(
                "SELECT id FROM periodos WHERE status='ABERTO' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            periodo_id = periodo["id"] if periodo else None

        conexao.execute("""
            INSERT INTO historico (
                data_hora, tipo_identificacao, id_cracha, matricula,
                nome, setor, cesta_normal, cesta_especial, resultado, motivo, periodo_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agora(),
            "NÃO IDENTIFICADO",
            None,
            str(identificacao),
            None,
            None,
            0,
            0,
            "NAO_ENCONTRADO",
            "ID do crachá ou matrícula não encontrado.",
            periodo_id,
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
    """Libera a cesta com validação e desconto atômico do estoque."""
    conexao = conectar()

    try:
        # IMMEDIATE evita duas liberações simultâneas consumirem o mesmo estoque.
        conexao.execute("BEGIN IMMEDIATE")
        cursor = conexao.cursor()

        periodo = cursor.execute(
            "SELECT id FROM periodos WHERE status='ABERTO' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if periodo is None:
            conexao.rollback()
            return {
                "sucesso": False,
                "resultado": "ERRO",
                "motivo": "Não existe período aberto para realizar a entrega."
            }
        periodo_id = int(periodo["id"])

        colaborador = cursor.execute("""
            SELECT *
            FROM colaboradores
            WHERE id = ?
            LIMIT 1
        """, (colaborador_id,)).fetchone()

        if colaborador is None:
            conexao.rollback()
            return {
                "sucesso": False,
                "resultado": "ERRO",
                "motivo": "Colaborador não encontrado."
            }

        if colaborador["periodo_id"] is not None and int(colaborador["periodo_id"]) != periodo_id:
            conexao.rollback()
            return {
                "sucesso": False,
                "resultado": "ERRO",
                "motivo": "O colaborador não pertence ao período ativo."
            }

        perde = str(colaborador["perde"] or "").strip()
        if perde and perde.lower() not in {"nan", "none", "null", "nat"}:
            motivo = perde
            cursor.execute("""
                INSERT INTO historico (
                    data_hora, tipo_identificacao, id_cracha, matricula,
                    nome, setor, cesta_normal, cesta_especial, resultado, motivo, periodo_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora(), tipo_identificacao, colaborador["id_mat"],
                colaborador["matricula"], colaborador["nome"], colaborador["setor"],
                colaborador["cesta_normal"], colaborador["cesta_especial"],
                "NEGADO", motivo, periodo_id,
            ))
            conexao.commit()
            return {
                "sucesso": False,
                "resultado": "NEGADO",
                "motivo": motivo,
                "perde": motivo,
            }

        if colaborador["confirmacao_retirada"]:
            motivo = (
                "Retirada já realizada em "
                f"{colaborador['data_hora_retirada']}"
            )
            cursor.execute("""
                INSERT INTO historico (
                    data_hora, tipo_identificacao, id_cracha, matricula,
                    nome, setor, cesta_normal, cesta_especial, resultado, motivo, periodo_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora(), tipo_identificacao, colaborador["id_mat"],
                colaborador["matricula"], colaborador["nome"], colaborador["setor"],
                colaborador["cesta_normal"], colaborador["cesta_especial"],
                "DUPLICADO", "Retirada já realizada.", periodo_id,
            ))
            conexao.commit()
            return {"sucesso": False, "resultado": "DUPLICADO", "motivo": motivo}

        cesta_normal_necessaria = int(colaborador["cesta_normal"] or 0)
        cesta_especial_necessaria = int(colaborador["cesta_especial"] or 0)

        if cesta_normal_necessaria <= 0 and cesta_especial_necessaria <= 0:
            motivo = "Colaborador não possui cesta normal ou especial."
            cursor.execute("""
                INSERT INTO historico (
                    data_hora, tipo_identificacao, id_cracha, matricula,
                    nome, setor, cesta_normal, cesta_especial, resultado, motivo, periodo_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora(), tipo_identificacao, colaborador["id_mat"],
                colaborador["matricula"], colaborador["nome"], colaborador["setor"],
                0, 0, "NEGADO", motivo, periodo_id,
            ))
            conexao.commit()
            return {"sucesso": False, "resultado": "NEGADO", "motivo": motivo}

        estoque = cursor.execute("""
            SELECT * FROM estoque ORDER BY id LIMIT 1
        """).fetchone()

        if estoque is None:
            cursor.execute("""
                INSERT INTO estoque (cesta_normal, cesta_especial, data_atualizacao)
                VALUES (0, 0, ?)
            """, (agora(),))
            estoque = cursor.execute("""
                SELECT * FROM estoque ORDER BY id LIMIT 1
            """).fetchone()

        # O estoque único representa sempre o período aberto.
        if estoque["periodo_id"] is not None and int(estoque["periodo_id"]) != periodo_id:
            cursor.execute("""
                UPDATE estoque SET periodo_id = ? WHERE id = ?
            """, (periodo_id, estoque["id"]))
            estoque = cursor.execute("SELECT * FROM estoque WHERE id = ?", (estoque["id"],)).fetchone()

        estoque_normal_antes = int(estoque["cesta_normal"] or 0)
        estoque_especial_antes = int(estoque["cesta_especial"] or 0)

        if cesta_normal_necessaria > estoque_normal_antes:
            motivo = (
                f"Estoque insuficiente de cestas normais. "
                f"Necessário: {cesta_normal_necessaria}; "
                f"disponível: {estoque_normal_antes}."
            )
            cursor.execute("""
                INSERT INTO historico (
                    data_hora, tipo_identificacao, id_cracha, matricula,
                    nome, setor, cesta_normal, cesta_especial, resultado, motivo,
                    estoque_normal_antes, estoque_normal_depois,
                    estoque_especial_antes, estoque_especial_depois, periodo_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora(), tipo_identificacao, colaborador["id_mat"],
                colaborador["matricula"], colaborador["nome"], colaborador["setor"],
                cesta_normal_necessaria, cesta_especial_necessaria, "SEM_ESTOQUE", motivo,
                estoque_normal_antes, estoque_normal_antes,
                estoque_especial_antes, estoque_especial_antes,
                periodo_id,
            ))
            conexao.commit()
            return {"sucesso": False, "resultado": "SEM_ESTOQUE", "motivo": motivo}

        if cesta_especial_necessaria > estoque_especial_antes:
            motivo = (
                f"Estoque insuficiente de cestas especiais. "
                f"Necessário: {cesta_especial_necessaria}; "
                f"disponível: {estoque_especial_antes}."
            )
            cursor.execute("""
                INSERT INTO historico (
                    data_hora, tipo_identificacao, id_cracha, matricula,
                    nome, setor, cesta_normal, cesta_especial, resultado, motivo,
                    estoque_normal_antes, estoque_normal_depois,
                    estoque_especial_antes, estoque_especial_depois, periodo_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora(), tipo_identificacao, colaborador["id_mat"],
                colaborador["matricula"], colaborador["nome"], colaborador["setor"],
                cesta_normal_necessaria, cesta_especial_necessaria, "SEM_ESTOQUE", motivo,
                estoque_normal_antes, estoque_normal_antes,
                estoque_especial_antes, estoque_especial_antes,
                periodo_id,
            ))
            conexao.commit()
            return {"sucesso": False, "resultado": "SEM_ESTOQUE", "motivo": motivo}

        estoque_normal_depois = estoque_normal_antes - cesta_normal_necessaria
        estoque_especial_depois = estoque_especial_antes - cesta_especial_necessaria
        data_retirada = agora()

        cursor.execute("""
            UPDATE estoque
            SET cesta_normal = ?, cesta_especial = ?, data_atualizacao = ?
            WHERE id = ?
        """, (
            estoque_normal_depois, estoque_especial_depois,
            data_retirada, estoque["id"],
        ))

        cursor.execute("""
            UPDATE colaboradores
            SET confirmacao_retirada = ?, data_hora_retirada = ?
            WHERE id = ?
        """, ("SIM", data_retirada, colaborador["id"]))

        cursor.execute("""
            INSERT INTO historico (
                data_hora, tipo_identificacao, id_cracha, matricula,
                nome, setor, cesta_normal, cesta_especial, resultado, motivo,
                estoque_normal_antes, estoque_normal_depois,
                estoque_especial_antes, estoque_especial_depois, periodo_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data_retirada, tipo_identificacao, colaborador["id_mat"],
            colaborador["matricula"], colaborador["nome"], colaborador["setor"],
            cesta_normal_necessaria, cesta_especial_necessaria,
            "LIBERADO", "Retirada realizada com sucesso.",
            estoque_normal_antes, estoque_normal_depois,
            estoque_especial_antes, estoque_especial_depois,
            periodo_id,
        ))

        conexao.commit()

        return {
            "sucesso": True,
            "resultado": "LIBERADO",
            "data_hora": data_retirada,
            "cesta_normal": cesta_normal_necessaria,
            "cesta_especial": cesta_especial_necessaria,
            "estoque_normal_antes": estoque_normal_antes,
            "estoque_normal_depois": estoque_normal_depois,
            "estoque_especial_antes": estoque_especial_antes,
            "estoque_especial_depois": estoque_especial_depois,
        }

    except Exception as erro:
        conexao.rollback()
        return {
            "sucesso": False,
            "resultado": "ERRO",
            "motivo": str(erro),
        }
    finally:
        conexao.close()


# ============================================================
# HISTÓRICO
# ============================================================

def obter_historico(
    limite=5000,
    periodo_id=None
):

    conexao = conectar()

    try:

        if periodo_id is None:
            registros = conexao.execute("""
                SELECT * FROM historico ORDER BY id DESC LIMIT ?
            """, (limite,)).fetchall()
        else:
            registros = conexao.execute("""
                SELECT * FROM historico WHERE periodo_id = ? ORDER BY id DESC LIMIT ?
            """, (int(periodo_id), limite)).fetchall()

        return registros

    finally:

        conexao.close()


# ============================================================
# INDICADORES
# ============================================================

def obter_indicadores(periodo_id=None):
    conexao = conectar()
    try:
        filtro = ""
        params = ()
        if periodo_id is not None:
            filtro = " AND periodo_id = ?"
            params = (int(periodo_id),)

        def contar(resultado):
            return conexao.execute(f"SELECT COUNT(*) FROM historico WHERE resultado = ?{filtro}", (resultado,) + params).fetchone()[0]

        liberadas = contar("LIBERADO")
        negadas = contar("NEGADO")
        duplicadas = contar("DUPLICADO")
        nao_encontradas = contar("NAO_ENCONTRADO")
        cestas_normais = conexao.execute(f"SELECT COALESCE(SUM(cesta_normal),0) FROM historico WHERE resultado='LIBERADO'{filtro}", params).fetchone()[0]
        cestas_especiais = conexao.execute(f"SELECT COALESCE(SUM(cesta_especial),0) FROM historico WHERE resultado='LIBERADO'{filtro}", params).fetchone()[0]
        tentativas = conexao.execute(f"SELECT COUNT(*) FROM historico WHERE 1=1{filtro}", params).fetchone()[0]
        return {
            "liberadas": liberadas,
            "negadas": negadas,
            "duplicadas": duplicadas,
            "nao_encontradas": nao_encontradas,
            "cestas_normais": cestas_normais,
            "cestas_especiais": cestas_especiais,
            "tentativas": tentativas,
        }
    finally:
        conexao.close()
