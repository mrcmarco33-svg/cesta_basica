from database.database import conectar


# ============================================================
# NORMALIZAR ID DO CRACHÁ
# ============================================================

def normalizar_id_cracha(valor):

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    texto = texto.replace(" ", "")

    try:

        return int(float(texto))

    except (
        ValueError,
        TypeError
    ):

        return None


# ============================================================
# NORMALIZAR MATRÍCULA
# ============================================================

def normalizar_matricula(valor):

    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    texto = texto.replace(" ", "")

    try:

        return int(float(texto))

    except (
        ValueError,
        TypeError
    ):

        return None


# ============================================================
# BUSCAR POR CRACHÁ
# ============================================================

def buscar_por_id_cracha(
    id_cracha
):

    id_normalizado = (
        normalizar_id_cracha(
            id_cracha
        )
    )

    if id_normalizado is None:
        return None

    conexao = conectar()

    try:

        return conexao.execute("""
            SELECT *
            FROM colaboradores
            WHERE id_mat = ?
            LIMIT 1
        """, (
            id_normalizado,
        )).fetchone()

    finally:

        conexao.close()


# ============================================================
# BUSCAR POR MATRÍCULA
# ============================================================

def buscar_por_matricula(
    matricula
):

    matricula_normalizada = (
        normalizar_matricula(
            matricula
        )
    )

    if matricula_normalizada is None:
        return None

    conexao = conectar()

    try:

        return conexao.execute("""
            SELECT *
            FROM colaboradores

            WHERE CAST(
                CAST(matricula AS REAL)
                AS INTEGER
            ) = ?

            LIMIT 1

        """, (
            matricula_normalizada,
        )).fetchone()

    finally:

        conexao.close()


# ============================================================
# BUSCAR DEMITIDO
# ============================================================

def buscar_demitido(
    chapa
):

    chapa_normalizada = (
        normalizar_matricula(
            chapa
        )
    )

    if chapa_normalizada is None:
        return None

    conexao = conectar()

    try:

        return conexao.execute("""
            SELECT *
            FROM demitidos

            WHERE CAST(
                CAST(chapa AS REAL)
                AS INTEGER
            ) = ?

            LIMIT 1

        """, (
            chapa_normalizada,
        )).fetchone()

    finally:

        conexao.close()


# ============================================================
# VERIFICAR CRACHÁ
# ============================================================

def cracha_ja_cadastrado(
    id_cracha,
    ignorar_colaborador_id=None
):

    id_normalizado = (
        normalizar_id_cracha(
            id_cracha
        )
    )

    if id_normalizado is None:
        return None

    conexao = conectar()

    try:

        if ignorar_colaborador_id is None:

            return conexao.execute("""
                SELECT *
                FROM colaboradores
                WHERE id_mat = ?
                LIMIT 1
            """, (
                id_normalizado,
            )).fetchone()

        return conexao.execute("""
            SELECT *
            FROM colaboradores

            WHERE id_mat = ?
              AND id != ?

            LIMIT 1

        """, (
            id_normalizado,
            ignorar_colaborador_id,
        )).fetchone()

    finally:

        conexao.close()


# ============================================================
# CADASTRAR CRACHÁ
# ============================================================

def cadastrar_cracha(
    colaborador_id,
    id_cracha
):

    id_normalizado = (
        normalizar_id_cracha(
            id_cracha
        )
    )

    if id_normalizado is None:

        return {
            "sucesso": False,
            "motivo": (
                "ID do crachá inválido."
            ),
        }

    conexao = conectar()

    try:

        # ----------------------------------------------------
        # VERIFICA DUPLICIDADE
        # ----------------------------------------------------

        existente = conexao.execute("""
            SELECT *
            FROM colaboradores

            WHERE id_mat = ?
              AND id != ?

            LIMIT 1

        """, (
            id_normalizado,
            colaborador_id,
        )).fetchone()

        if existente:

            return {
                "sucesso": False,
                "motivo": (
                    "Este crachá já está cadastrado "
                    f"para {existente['nome']} "
                    f"(matrícula "
                    f"{existente['matricula']})."
                ),
            }

        # ----------------------------------------------------
        # BUSCA COLABORADOR
        # ----------------------------------------------------

        colaborador = conexao.execute("""
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
                "motivo": (
                    "Colaborador não encontrado."
                ),
            }

        # ----------------------------------------------------
        # CADASTRA
        # ----------------------------------------------------

        conexao.execute("""
            UPDATE colaboradores

            SET id_mat = ?

            WHERE id = ?

        """, (
            id_normalizado,
            colaborador_id,
        ))

        conexao.commit()

        return {
            "sucesso": True,
            "id_cracha": id_normalizado,
            "nome": colaborador["nome"],
            "matricula": colaborador["matricula"],
        }

    except Exception as erro:

        conexao.rollback()

        return {
            "sucesso": False,
            "motivo": str(erro),
        }

    finally:

        conexao.close()


# ============================================================
# IDENTIFICAR
# ============================================================

def identificar(
    identificacao
):

    identificacao = str(
        identificacao
    ).strip()

    if not identificacao:

        return {
            "tipo": "ERRO",
            "resultado": (
                "IDENTIFICAÇÃO VAZIA"
            ),
        }

    # ========================================================
    # MATRÍCULA
    # ========================================================

    colaborador = buscar_por_matricula(
        identificacao
    )

    if colaborador:

        return {
            "tipo": "COLABORADOR",
            "dados": colaborador,
            "identificacao": "MATRÍCULA",
        }

    # ========================================================
    # CRACHÁ
    # ========================================================

    id_cracha = (
        normalizar_id_cracha(
            identificacao
        )
    )

    if id_cracha is not None:

        colaborador = (
            buscar_por_id_cracha(
                id_cracha
            )
        )

        if colaborador:

            return {
                "tipo": "COLABORADOR",
                "dados": colaborador,
                "identificacao": "ID CRACHÁ",
            }

    # ========================================================
    # DEMITIDO
    # ========================================================

    demitido = buscar_demitido(
        identificacao
    )

    if demitido:

        return {
            "tipo": "DEMITIDO",
            "dados": demitido,
            "identificacao": "CHAPA",
        }

    # ========================================================
    # NÃO ENCONTRADO
    # ========================================================

    return {
        "tipo": "NAO_ENCONTRADO",
        "resultado": "NÃO ENCONTRADO",
        "identificacao": identificacao,
    }