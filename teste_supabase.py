import streamlit as st
import psycopg2


print("=" * 60)
print("TESTE DE CONEXÃO COM SUPABASE")
print("=" * 60)

try:
    # --------------------------------------------------------
    # LÊ A STRING DO .streamlit/secrets.toml
    # --------------------------------------------------------

    database_url = st.secrets["DATABASE_URL"]

    print("DATABASE_URL encontrada.")
    print("Tentando conectar ao Supabase...")

    # --------------------------------------------------------
    # CONEXÃO
    # --------------------------------------------------------

    conexao = psycopg2.connect(
        database_url,
        sslmode="require",
        connect_timeout=10
    )

    cursor = conexao.cursor()

    # --------------------------------------------------------
    # TESTA O BANCO
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            current_database(),
            current_user,
            version()
    """)

    resultado = cursor.fetchone()

    print()
    print("✅ CONEXÃO REALIZADA COM SUCESSO!")
    print()
    print("Banco:", resultado[0])
    print("Usuário:", resultado[1])
    print("PostgreSQL:", resultado[2][:100])
    print()

    # --------------------------------------------------------
    # TESTA UMA TABELA SIMPLES
    # --------------------------------------------------------

    cursor.execute("""
        SELECT 1
    """)

    teste = cursor.fetchone()

    if teste[0] == 1:
        print("✅ Consulta de teste executada com sucesso.")

    cursor.close()
    conexao.close()

    print()
    print("=" * 60)
    print("SUPABASE ESTÁ FUNCIONANDO")
    print("=" * 60)

except KeyError:
    print()
    print("❌ ERRO: DATABASE_URL não encontrada.")
    print()
    print("Verifique se existe:")
    print()
    print(".streamlit\\secrets.toml")
    print()
    print("E se contém:")
    print()
    print('DATABASE_URL = "sua_string_do_supabase"')

except psycopg2.OperationalError as erro:

    print()
    print("❌ ERRO DE CONEXÃO COM O SUPABASE")
    print()
    print(erro)
    print()
    print("Verifique:")
    print("1. A senha do banco.")
    print("2. A Session Pooler.")
    print("3. O host.")
    print("4. A porta 5432.")
    print("5. O usuário.")
    print()

except Exception as erro:

    print()
    print("❌ ERRO INESPERADO")
    print()
    print(type(erro).__name__)
    print(erro)

finally:

    print()
    print("Teste encerrado.")