import hashlib

from database.database import conectar


# ============================================================
# HASH DA SENHA
# ============================================================

def gerar_hash_senha(
    senha
):

    return hashlib.sha256(
        senha.encode("utf-8")
    ).hexdigest()


# ============================================================
# INICIALIZAR USUÁRIOS
# ============================================================

def inicializar_usuarios():

    conexao = conectar()

    try:

        conexao.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                usuario TEXT UNIQUE NOT NULL,

                nome TEXT NOT NULL,

                senha TEXT NOT NULL,

                perfil TEXT NOT NULL,

                ativo INTEGER DEFAULT 1,

                data_criacao TEXT

            )
        """)

        # ----------------------------------------------------
        # ADMINISTRADOR PADRÃO
        # ----------------------------------------------------

        admin = conexao.execute("""
            SELECT id
            FROM usuarios
            WHERE usuario = ?
            LIMIT 1
        """, (
            "admin",
        )).fetchone()

        if admin is None:

            from database.database import agora

            conexao.execute("""
                INSERT INTO usuarios (

                    usuario,
                    nome,
                    senha,
                    perfil,
                    ativo,
                    data_criacao

                )

                VALUES (?, ?, ?, ?, ?, ?)

            """, (

                "admin",

                "Administrador",

                gerar_hash_senha(
                    "admin123"
                ),

                "ADMIN",

                1,

                agora(),

            ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# AUTENTICAR
# ============================================================

def autenticar(
    usuario,
    senha
):

    usuario = str(
        usuario
    ).strip()

    senha = str(
        senha
    )

    if not usuario or not senha:
        return None

    senha_hash = (
        gerar_hash_senha(
            senha
        )
    )

    conexao = conectar()

    try:

        registro = conexao.execute("""
            SELECT *
            FROM usuarios

            WHERE usuario = ?
              AND senha = ?
              AND ativo = 1

            LIMIT 1

        """, (
            usuario,
            senha_hash,
        )).fetchone()

        return registro

    finally:

        conexao.close()


# ============================================================
# LISTAR USUÁRIOS
# ============================================================

def listar_usuarios():

    conexao = conectar()

    try:

        return conexao.execute("""
            SELECT
                id,
                usuario,
                nome,
                perfil,
                ativo,
                data_criacao
            FROM usuarios
            ORDER BY nome
        """).fetchall()

    finally:

        conexao.close()


# ============================================================
# CRIAR USUÁRIO
# ============================================================

def criar_usuario(
    usuario,
    nome,
    senha,
    perfil
):

    usuario = str(
        usuario
    ).strip()

    nome = str(
        nome
    ).strip()

    senha = str(
        senha
    )

    perfil = str(
        perfil
    ).strip().upper()

    if not usuario:

        raise ValueError(
            "Informe o usuário."
        )

    if not nome:

        raise ValueError(
            "Informe o nome."
        )

    if not senha:

        raise ValueError(
            "Informe a senha."
        )

    if len(senha) < 4:

        raise ValueError(
            "A senha deve possuir "
            "pelo menos 4 caracteres."
        )

    if perfil not in (
        "ADMIN",
        "OPERADOR",
    ):

        raise ValueError(
            "Perfil inválido."
        )

    conexao = conectar()

    try:

        existe = conexao.execute("""
            SELECT id
            FROM usuarios
            WHERE usuario = ?
            LIMIT 1
        """, (
            usuario,
        )).fetchone()

        if existe:

            raise ValueError(
                "Este usuário já existe."
            )

        from database.database import agora

        conexao.execute("""
            INSERT INTO usuarios (

                usuario,
                nome,
                senha,
                perfil,
                ativo,
                data_criacao

            )

            VALUES (?, ?, ?, ?, ?, ?)

        """, (

            usuario,
            nome,
            gerar_hash_senha(
                senha
            ),
            perfil,
            1,
            agora(),

        ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# ALTERAR STATUS
# ============================================================

def alterar_status_usuario(
    usuario_id,
    ativo
):

    conexao = conectar()

    try:

        conexao.execute("""
            UPDATE usuarios

            SET ativo = ?

            WHERE id = ?

        """, (
            1 if ativo else 0,
            usuario_id,
        ))

        conexao.commit()

    finally:

        conexao.close()


# ============================================================
# ALTERAR SENHA
# ============================================================

def alterar_senha_usuario(
    usuario_id,
    nova_senha
):

    nova_senha = str(
        nova_senha
    )

    if not nova_senha:

        raise ValueError(
            "Informe a nova senha."
        )

    if len(nova_senha) < 4:

        raise ValueError(
            "A senha deve possuir "
            "pelo menos 4 caracteres."
        )

    conexao = conectar()

    try:

        conexao.execute("""
            UPDATE usuarios

            SET senha = ?

            WHERE id = ?

        """, (

            gerar_hash_senha(
                nova_senha
            ),

            usuario_id,

        ))

        conexao.commit()

    finally:

        conexao.close()