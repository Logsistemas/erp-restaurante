
import sqlite3
import secrets
import uuid
import unicodedata
from pathlib import Path
from datetime import date
import xml.etree.ElementTree as ET
import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image
import re
import json
import requests
import plotly.express as px
import plotly.graph_objects as go

DB_PATH = Path("estoque_restaurante.db")
META_CMV = 36.0

st.set_page_config(page_title="Estoque Restaurante | PEPS + CMV", layout="wide")
st.markdown("""
<style>

/* FUNDO GERAL */
.stApp {
    background-color: #f5f7fb;
}

.main .block-container {
    background: #f5f7fb;
    padding: 2rem 2.5rem;
}

section.main > div {
    background: #f5f7fb;
}

div[data-testid="column"] {
    background: transparent;
}

div[data-testid="stHorizontalBlock"] {
    gap: 18px;
}

div[data-testid="stMetric"] {
    background: #ffffff !important;
    border-radius: 22px !important;
    padding: 28px 24px !important;
    min-height: 130px !important;
    border: 1px solid #dbe3ef !important;
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.10) !important;
}

[data-testid="stMetricValue"] {
    font-size: 36px !important;
    font-weight: 900 !important;
}

[data-testid="stMetricLabel"] {
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #64748b !important;
}

/* REMOVE ESPAÇOS */
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}

/* CARDS */
div[data-testid="stMetric"] {
    background: white;
    padding: 26px 22px;
    border-radius: 24px;
    border: 1px solid #e5e7eb;
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 8px 24px rgba(15,23,42,0.06);
    transition: all 0.2s ease;
    min-height: 135px;
}

div[data-testid="stMetric"]:hover {
    transform: translateY(-4px);
    box-shadow:
        0 12px 30px rgba(15,23,42,0.10);
}

div[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 28px rgba(15,23,42,0.10);
}

/* TABELAS */
div[data-testid="stDataFrame"] {
    background: white;
    border-radius: 18px;
    padding: 10px;
    border: 1px solid #ececec;
    overflow: hidden;
}

/* MENU HORIZONTAL */
.stRadio > div {
    background: white;
    padding: 12px;
    border-radius: 16px;
    border: 1px solid #ececec;
    box-shadow: 0 4px 18px rgba(0,0,0,0.04);
}

/* BOTÕES */
.stButton > button {
    border-radius: 12px;
    border: none;
    background: linear-gradient(135deg, #111827, #1f2937);
    color: white;
    font-weight: 600;
}

/* TITULOS */
h1, h2, h3 {
    color: #111827;
}

/* SIDEBAR */
[data-testid="stSidebar"] {
    background-color: #ffffff;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# BANCO DE DADOS
# =========================================================
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            categoria TEXT,
            unidade TEXT DEFAULT 'UN',
            estoque_minimo REAL DEFAULT 0,
            preco_venda REAL DEFAULT 0,
            ativo INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL,
            data_entrada TEXT NOT NULL,
            qtd_inicial REAL NOT NULL,
            qtd_restante REAL NOT NULL,
            valor_unitario REAL NOT NULL,
            fornecedor TEXT,
            chave_nfe TEXT,
            observacao TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            produto_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            quantidade REAL NOT NULL,
            valor_unitario REAL,
            valor_total REAL,
            receita_venda REAL DEFAULT 0,
            cmv_peps REAL DEFAULT 0,
            custo_medio_atual REAL DEFAULT 0,
            tipo_saida TEXT DEFAULT '',
            motivo_saida TEXT DEFAULT '',
            fornecedor TEXT,
            chave_nfe TEXT,
            observacao TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            categoria TEXT NOT NULL,
            descricao TEXT,
            valor REAL NOT NULL,
            observacao TEXT,
            status TEXT DEFAULT 'Em aberto'
        )
    """)

    cur.execute("PRAGMA table_info(movimentacoes)")
    cols = [r[1] for r in cur.fetchall()]

    if "receita_venda" not in cols:
        cur.execute("ALTER TABLE movimentacoes ADD COLUMN receita_venda REAL DEFAULT 0")
    if "tipo_saida" not in cols:
        cur.execute("ALTER TABLE movimentacoes ADD COLUMN tipo_saida TEXT DEFAULT ''")
    if "motivo_saida" not in cols:
        cur.execute("ALTER TABLE movimentacoes ADD COLUMN motivo_saida TEXT DEFAULT ''")
    cur.execute("PRAGMA table_info(despesas)")
    cols_despesas = [r[1] for r in cur.fetchall()]

    if "status" not in cols_despesas:
        cur.execute("ALTER TABLE despesas ADD COLUMN status TEXT DEFAULT 'Em aberto'")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessoes_auth (
            token TEXT PRIMARY KEY,
            usuario TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            expira_em TEXT NOT NULL
        )
    """)

    cur.execute("PRAGMA table_info(produtos)")
    cols_prod = [r[1] for r in cur.fetchall()]

    if "codigo" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN codigo TEXT")
    if "codigo_barras" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN codigo_barras TEXT")
    if "custo_referencia" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN custo_referencia REAL DEFAULT 0")
    if "ncm" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN ncm TEXT DEFAULT ''")
    if "cst" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN cst TEXT DEFAULT ''")
    if "icms" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN icms REAL DEFAULT 0")
    if "pis" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN pis REAL DEFAULT 0")
    if "cofins" not in cols_prod:
        cur.execute("ALTER TABLE produtos ADD COLUMN cofins REAL DEFAULT 0")

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_produtos_codigo
        ON produtos(codigo)
        WHERE codigo IS NOT NULL AND TRIM(codigo) != ''
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_produtos_codigo_barras
        ON produtos(codigo_barras)
        WHERE codigo_barras IS NOT NULL AND TRIM(codigo_barras) != ''
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdv_vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            hora TEXT,
            operador TEXT,
            subtotal REAL NOT NULL,
            desconto REAL DEFAULT 0,
            total REAL NOT NULL,
            troco REAL DEFAULT 0,
            status TEXT DEFAULT 'FINALIZADA',
            nfce_status TEXT DEFAULT 'PENDENTE',
            nfce_chave TEXT,
            nfce_numero TEXT,
            nfce_serie TEXT,
            observacao TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdv_venda_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venda_id INTEGER NOT NULL,
            produto_id INTEGER NOT NULL,
            codigo TEXT,
            nome TEXT,
            unidade TEXT,
            quantidade REAL NOT NULL,
            preco_unitario REAL NOT NULL,
            subtotal REAL NOT NULL,
            ncm TEXT,
            cst TEXT,
            icms REAL DEFAULT 0,
            pis REAL DEFAULT 0,
            cofins REAL DEFAULT 0,
            cmv_peps REAL DEFAULT 0,
            movimentacao_id INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdv_venda_pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venda_id INTEGER NOT NULL,
            forma TEXT NOT NULL,
            valor REAL NOT NULL,
            troco REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdv_caixas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operador_abertura TEXT NOT NULL,
            operador_fechamento TEXT,
            data_abertura TEXT NOT NULL,
            hora_abertura TEXT NOT NULL,
            data_fechamento TEXT,
            hora_fechamento TEXT,
            valor_inicial REAL NOT NULL DEFAULT 0,
            valor_contado REAL,
            status TEXT NOT NULL DEFAULT 'ABERTO',
            observacao_abertura TEXT,
            observacao_fechamento TEXT,
            total_vendido REAL DEFAULT 0,
            total_descontos REAL DEFAULT 0,
            total_dinheiro REAL DEFAULT 0,
            total_pix REAL DEFAULT 0,
            total_credito REAL DEFAULT 0,
            total_debito REAL DEFAULT 0,
            qtd_vendas INTEGER DEFAULT 0,
            qtd_cancelamentos INTEGER DEFAULT 0,
            valor_esperado_dinheiro REAL DEFAULT 0,
            diferenca_dinheiro REAL DEFAULT 0,
            nfce_pendencias INTEGER DEFAULT 0
        )
    """)

    cur.execute("PRAGMA table_info(pdv_vendas)")
    cols_pdv_vendas = [r[1] for r in cur.fetchall()]
    if "caixa_id" not in cols_pdv_vendas:
        cur.execute("ALTER TABLE pdv_vendas ADD COLUMN caixa_id INTEGER")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_pdv_vendas_caixa ON pdv_vendas(caixa_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pdv_vendas_data ON pdv_vendas(data)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pdv_vendas_status ON pdv_vendas(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pdv_caixas_status ON pdv_caixas(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pdv_venda_pagamentos_venda ON pdv_venda_pagamentos(venda_id)")

    cur.execute("PRAGMA table_info(movimentacoes)")
    cols_mov = [r[1] for r in cur.fetchall()]
    if "pdv_venda_id" not in cols_mov:
        cur.execute("ALTER TABLE movimentacoes ADD COLUMN pdv_venda_id INTEGER")

    c.commit()
    c.close()

    migrar_catalogo_produtos()


def seed():
    lista = [
        ("Croissant Queijo Presunto", "Croissant", "UN", 10, 0),
        ("Croissant Carne", "Croissant", "UN", 10, 0),
        ("Croissant Ricota", "Croissant", "UN", 10, 0),
        ("Croissant Frango Requeijão", "Croissant", "UN", 10, 0),
        ("Pastel Carne", "Pastel", "UN", 20, 0),
        ("Pastel Queijo", "Pastel", "UN", 20, 0),
        ("Pastel Natural Frango", "Pastel", "UN", 20, 0),
        ("Açaí", "Açaí", "UN", 10, 0),
        ("Torta Frango", "Torta", "UN", 10, 0),
    ]

    c = conn()
    cur = c.cursor()

    for p in lista:
        cur.execute("""
            INSERT OR IGNORE INTO produtos 
            (nome, categoria, unidade, estoque_minimo, preco_venda)
            VALUES (?, ?, ?, ?, ?)
        """, p)

    c.commit()
    c.close()


def normalizar_codigo_produto(codigo):
    return str(codigo or "").strip().upper()


def normalizar_texto_ascii(texto):
    texto = str(texto or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


MAPA_PREFIXO_CATEGORIA = {
    "croissant": "CRO",
    "pastel": "PAS",
    "acai": "ACA",
    "açaí": "ACA",
    "torta": "TOR",
    "bebida": "BEB",
    "bebidas": "BEB",
    "cafe": "BEB",
    "café": "BEB",
    "suco": "BEB",
    "sucos": "BEB",
    "insumo": "INS",
    "insumos": "INS",
    "embalagem": "INS",
    "embalagens": "INS",
    "mercadoria": "PRD",
}


def gerar_prefixo_sku(categoria, nome=""):
    cat_norm = normalizar_texto_ascii(categoria)
    nome_u = normalizar_codigo_produto(nome)

    if cat_norm in MAPA_PREFIXO_CATEGORIA:
        prefixo = MAPA_PREFIXO_CATEGORIA[cat_norm]
        if prefixo != "PRD":
            return prefixo

    if "CROISSANT" in nome_u:
        return "CRO"
    if "PASTEL" in nome_u:
        return "PAS"
    if "ACAI" in nome_u or "AÇAI" in nome_u or nome_u.startswith("ACA "):
        return "ACA"
    if "TORTA" in nome_u:
        return "TOR"

    return "PRD"


def codigo_sku_legado(codigo):
    cod = normalizar_codigo_produto(codigo)
    return (not cod) or cod.startswith("SKU-")


def max_sequencial_prefixo(prefixo, cur):
    cur.execute("""
        SELECT codigo
        FROM produtos
        WHERE codigo IS NOT NULL AND TRIM(codigo) != ''
    """)
    max_num = 0
    prefixo = normalizar_codigo_produto(prefixo)
    marcador = f"{prefixo}-"

    for row in cur.fetchall():
        cod = normalizar_codigo_produto(row["codigo"])
        if not cod.startswith(marcador):
            continue
        sufixo = cod[len(marcador):]
        if sufixo.isdigit():
            max_num = max(max_num, int(sufixo))

    return max_num


def gerar_proximo_codigo_sku(categoria, nome, cur):
    prefixo = gerar_prefixo_sku(categoria, nome)
    seq = max_sequencial_prefixo(prefixo, cur) + 1
    return f"{prefixo}-{seq:03d}"


def gerar_codigo_produto_automatico(produto_id, nome="", categoria=""):
    """Compatibilidade: gera SKU categorizado."""
    c = conn()
    cur = c.cursor()
    codigo = gerar_proximo_codigo_sku(categoria, nome, cur)
    c.close()
    return codigo


def organizar_skus_produtos():
    """Organiza SKU no padrão PREFIXO-NNN (CRO-001, PAS-001, ACA-001, PRD-001)."""
    c = conn()
    cur = c.cursor()
    cur.execute("""
        SELECT id, nome, categoria, codigo
        FROM produtos
        ORDER BY id
    """)
    produtos = cur.fetchall()
    contadores = {}

    for row in produtos:
        if not codigo_sku_legado(row["codigo"]):
            continue

        prefixo = gerar_prefixo_sku(row["categoria"], row["nome"])
        if prefixo not in contadores:
            contadores[prefixo] = max_sequencial_prefixo(prefixo, cur)

        contadores[prefixo] += 1
        codigo = f"{prefixo}-{contadores[prefixo]:03d}"
        cur.execute("UPDATE produtos SET codigo = ? WHERE id = ?", (codigo, row["id"]))

    c.commit()
    c.close()


def migrar_catalogo_produtos():
    """Preenche SKU ausente ou legado SKU-00000."""
    organizar_skus_produtos()


# =========================================================
# FUNÇÕES BASE
# =========================================================
def produtos_df():
    c = conn()
    df = pd.read_sql_query("SELECT * FROM produtos WHERE ativo=1 ORDER BY nome", c)
    c.close()
    return df


def produtos_catalogo_df():
    """
    Catálogo profissional unificado para operação, estoque e CMV.
    Custo exibido: PEPS (lotes) quando existir; senão custo_referencia do cadastro.
    Estoque: saldo atual consolidado dos lotes.
    """
    c = conn()
    df = pd.read_sql_query("""
        SELECT
            p.id,
            p.codigo,
            p.codigo_barras,
            p.nome,
            p.categoria,
            p.unidade,
            p.custo_referencia,
            p.preco_venda,
            p.estoque_minimo,
            p.ncm,
            p.cst,
            p.icms,
            p.pis,
            p.cofins,
            COALESCE(SUM(l.qtd_restante), 0) AS estoque_qtd,
            COALESCE(SUM(l.qtd_restante * l.valor_unitario), 0) AS estoque_valor
        FROM produtos p
        LEFT JOIN lotes l ON l.produto_id = p.id AND l.qtd_restante > 0
        WHERE p.ativo = 1
        GROUP BY p.id
        ORDER BY p.codigo, p.nome
    """, c)
    c.close()

    if df.empty:
        return df

    df["estoque_qtd"] = pd.to_numeric(df["estoque_qtd"], errors="coerce").fillna(0)
    df["estoque_valor"] = pd.to_numeric(df["estoque_valor"], errors="coerce").fillna(0)
    df["custo_referencia"] = pd.to_numeric(df["custo_referencia"], errors="coerce").fillna(0)
    df["preco_venda"] = pd.to_numeric(df["preco_venda"], errors="coerce").fillna(0)
    df["icms"] = pd.to_numeric(df["icms"], errors="coerce").fillna(0)
    df["pis"] = pd.to_numeric(df["pis"], errors="coerce").fillna(0)
    df["cofins"] = pd.to_numeric(df["cofins"], errors="coerce").fillna(0)

    df["custo_peps"] = df.apply(
        lambda r: (r["estoque_valor"] / r["estoque_qtd"]) if r["estoque_qtd"] > 0 else 0.0,
        axis=1,
    )
    df["custo"] = df.apply(
        lambda r: r["custo_peps"] if r["custo_peps"] > 0 else r["custo_referencia"],
        axis=1,
    )

    df = df.rename(columns={
        "codigo": "Código",
        "codigo_barras": "Código de Barras",
        "nome": "Nome",
        "categoria": "Categoria",
        "unidade": "Unidade",
        "custo": "Custo",
        "preco_venda": "Preço",
        "estoque_qtd": "Estoque",
        "estoque_minimo": "Estoque Mínimo",
        "custo_peps": "Custo PEPS",
        "custo_referencia": "Custo Referência",
        "estoque_valor": "Valor Estoque",
        "ncm": "NCM",
        "cst": "CST",
        "icms": "ICMS",
        "pis": "PIS",
        "cofins": "COFINS",
    })

    return df


def buscar_produto_por_codigo_exato(codigo):
    """
    Busca exata por SKU interno ou código de barras.
    Pensado para leitor de código de barras e integrações futuras.
    """
    codigo_norm = normalizar_codigo_produto(codigo)
    if not codigo_norm:
        return None

    c = conn()
    cur = c.cursor()
    cur.execute("""
        SELECT id
        FROM produtos
        WHERE ativo = 1
          AND (
            UPPER(TRIM(codigo)) = ?
            OR UPPER(TRIM(codigo_barras)) = ?
          )
        LIMIT 1
    """, (codigo_norm, codigo_norm))
    row = cur.fetchone()
    c.close()

    if not row:
        return None

    cat = produtos_catalogo_df()
    if cat.empty:
        return None

    encontrado = cat[cat["id"] == row["id"]]
    if encontrado.empty:
        return None

    return encontrado.iloc[0].to_dict()


def buscar_produtos_catalogo(termo="", limite=50):
    """
    Busca operacional por nome, SKU ou código de barras.
    Prioriza match exato de código (barcode) e depois parcial em nome/código.
    """
    df = produtos_catalogo_df()
    if df.empty:
        return df

    termo = str(termo or "").strip()
    if not termo:
        return df.head(limite)

    exato = buscar_produto_por_codigo_exato(termo)
    if exato:
        return pd.DataFrame([exato])

    termo_lower = termo.lower()
    termo_upper = normalizar_codigo_produto(termo)

    mask = (
        df["Nome"].str.lower().str.contains(termo_lower, na=False, regex=False)
        | df["Código"].fillna("").str.upper().str.contains(termo_upper, na=False, regex=False)
        | df["Código de Barras"].fillna("").str.upper().str.contains(termo_upper, na=False, regex=False)
    )

    return df[mask].head(limite)


PDV_FORMAS_PAGAMENTO = ["Dinheiro", "PIX", "Débito", "Crédito"]
PDV_STATUS_VENDA_FINALIZADA = "FINALIZADA"
PDV_STATUS_VENDA_CANCELADA = "CANCELADA"
PDV_STATUS_CAIXA_ABERTO = "ABERTO"
PDV_STATUS_CAIXA_FECHADO = "FECHADO"


def normalizar_forma_pagamento(forma):
    texto = str(forma or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))

    if "pix" in texto:
        return "PIX"
    if "cred" in texto:
        return "Crédito"
    if "deb" in texto:
        return "Débito"
    if "din" in texto or "cash" in texto:
        return "Dinheiro"
    return str(forma or "Outros").strip() or "Outros"


def caixa_row_para_dict(row):
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def caixa_aberto():
    c = conn()
    cur = c.cursor()
    cur.execute("""
        SELECT *
        FROM pdv_caixas
        WHERE status = ?
        ORDER BY id DESC
        LIMIT 1
    """, (PDV_STATUS_CAIXA_ABERTO,))
    row = cur.fetchone()
    c.close()
    return caixa_row_para_dict(row)


def buscar_caixa(caixa_id):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT * FROM pdv_caixas WHERE id = ?", (int(caixa_id),))
    row = cur.fetchone()
    c.close()
    return caixa_row_para_dict(row)


def abrir_caixa(operador, valor_inicial, observacao=""):
    valor_inicial = float(valor_inicial or 0)
    if valor_inicial < 0:
        raise ValueError("Informe um valor inicial válido (>= 0).")

    if caixa_aberto():
        raise ValueError("Já existe um caixa aberto. Feche o caixa atual antes de abrir outro.")

    agora = pd.Timestamp.now()
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO pdv_caixas
        (operador_abertura, data_abertura, hora_abertura, valor_inicial, status, observacao_abertura)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        str(operador or "Operador"),
        str(agora.date()),
        agora.strftime("%H:%M:%S"),
        valor_inicial,
        PDV_STATUS_CAIXA_ABERTO,
        str(observacao or "").strip(),
    ))
    caixa_id = cur.lastrowid
    c.commit()
    c.close()
    return caixa_id


def _pagamentos_por_forma_caixa(cur, caixa_id):
    cur.execute("""
        SELECT p.forma, COALESCE(SUM(p.valor), 0) AS total_valor, COALESCE(SUM(p.troco), 0) AS total_troco
        FROM pdv_venda_pagamentos p
        INNER JOIN pdv_vendas v ON v.id = p.venda_id
        WHERE v.caixa_id = ?
          AND v.status = ?
        GROUP BY p.forma
    """, (int(caixa_id), PDV_STATUS_VENDA_FINALIZADA))
    rows = cur.fetchall()

    totais = {"Dinheiro": 0.0, "PIX": 0.0, "Crédito": 0.0, "Débito": 0.0, "Outros": 0.0}
    for row in rows:
        chave = normalizar_forma_pagamento(row["forma"])
        if chave not in totais:
            totais["Outros"] += float(row["total_valor"] or 0)
        else:
            totais[chave] += float(row["total_valor"] or 0)
    return totais


def resumo_caixa(caixa_id):
    caixa = buscar_caixa(caixa_id)
    if not caixa:
        raise ValueError("Caixa não encontrado.")

    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT
            COUNT(CASE WHEN status = ? THEN 1 END) AS qtd_vendas,
            COUNT(CASE WHEN status = ? THEN 1 END) AS qtd_cancelamentos,
            COALESCE(SUM(CASE WHEN status = ? THEN total ELSE 0 END), 0) AS total_vendido,
            COALESCE(SUM(CASE WHEN status = ? THEN desconto ELSE 0 END), 0) AS total_descontos,
            COALESCE(SUM(CASE WHEN status = ? THEN troco ELSE 0 END), 0) AS total_troco,
            COALESCE(SUM(CASE WHEN status = ? AND nfce_status = 'PENDENTE' THEN 1 ELSE 0 END), 0) AS nfce_pendencias
        FROM pdv_vendas
        WHERE caixa_id = ?
    """, (
        PDV_STATUS_VENDA_FINALIZADA,
        PDV_STATUS_VENDA_CANCELADA,
        PDV_STATUS_VENDA_FINALIZADA,
        PDV_STATUS_VENDA_FINALIZADA,
        PDV_STATUS_VENDA_FINALIZADA,
        PDV_STATUS_VENDA_FINALIZADA,
        int(caixa_id),
    ))
    agg = dict(cur.fetchone())
    pagamentos = _pagamentos_por_forma_caixa(cur, caixa_id)
    c.close()

    valor_inicial = float(caixa.get("valor_inicial", 0) or 0)
    total_dinheiro = float(pagamentos.get("Dinheiro", 0) or 0)
    total_troco = float(agg.get("total_troco", 0) or 0)
    valor_esperado_dinheiro = valor_inicial + total_dinheiro - total_troco
    valor_contado = caixa.get("valor_contado")
    diferenca = None
    if valor_contado is not None:
        diferenca = float(valor_contado) - valor_esperado_dinheiro

    qtd_vendas = int(agg.get("qtd_vendas", 0) or 0)
    total_vendido = float(agg.get("total_vendido", 0) or 0)

    return {
        "caixa": caixa,
        "qtd_vendas": qtd_vendas,
        "qtd_cancelamentos": int(agg.get("qtd_cancelamentos", 0) or 0),
        "total_vendido": total_vendido,
        "total_descontos": float(agg.get("total_descontos", 0) or 0),
        "total_dinheiro": total_dinheiro,
        "total_pix": float(pagamentos.get("PIX", 0) or 0),
        "total_credito": float(pagamentos.get("Crédito", 0) or 0),
        "total_debito": float(pagamentos.get("Débito", 0) or 0),
        "total_outros": float(pagamentos.get("Outros", 0) or 0),
        "valor_inicial": valor_inicial,
        "valor_esperado_dinheiro": valor_esperado_dinheiro,
        "valor_contado": valor_contado,
        "diferenca_dinheiro": diferenca,
        "total_troco": total_troco,
        "ticket_medio": (total_vendido / qtd_vendas) if qtd_vendas else 0.0,
        "nfce_pendencias": int(agg.get("nfce_pendencias", 0) or 0),
    }


def fechar_caixa(caixa_id, operador, valor_contado, observacao=""):
    caixa = buscar_caixa(caixa_id)
    if not caixa:
        raise ValueError("Caixa não encontrado.")
    if caixa.get("status") != PDV_STATUS_CAIXA_ABERTO:
        raise ValueError("Este caixa já está fechado.")

    valor_contado = float(valor_contado or 0)
    if valor_contado < 0:
        raise ValueError("Informe o valor contado em dinheiro (>= 0).")

    resumo = resumo_caixa(caixa_id)
    agora = pd.Timestamp.now()
    diferenca = valor_contado - resumo["valor_esperado_dinheiro"]

    c = conn()
    cur = c.cursor()
    cur.execute("""
        UPDATE pdv_caixas
        SET operador_fechamento = ?,
            data_fechamento = ?,
            hora_fechamento = ?,
            valor_contado = ?,
            status = ?,
            observacao_fechamento = ?,
            total_vendido = ?,
            total_descontos = ?,
            total_dinheiro = ?,
            total_pix = ?,
            total_credito = ?,
            total_debito = ?,
            qtd_vendas = ?,
            qtd_cancelamentos = ?,
            valor_esperado_dinheiro = ?,
            diferenca_dinheiro = ?,
            nfce_pendencias = ?
        WHERE id = ?
    """, (
        str(operador or "Operador"),
        str(agora.date()),
        agora.strftime("%H:%M:%S"),
        valor_contado,
        PDV_STATUS_CAIXA_FECHADO,
        str(observacao or "").strip(),
        resumo["total_vendido"],
        resumo["total_descontos"],
        resumo["total_dinheiro"],
        resumo["total_pix"],
        resumo["total_credito"],
        resumo["total_debito"],
        resumo["qtd_vendas"],
        resumo["qtd_cancelamentos"],
        resumo["valor_esperado_dinheiro"],
        diferenca,
        resumo["nfce_pendencias"],
        int(caixa_id),
    ))
    c.commit()
    c.close()
    resumo["valor_contado"] = valor_contado
    resumo["diferenca_dinheiro"] = diferenca
    resumo["caixa"] = buscar_caixa(caixa_id)
    return resumo


def relatorio_vendas_pdv(data_ini, data_fim, operador="", forma=""):
    data_ini = str(data_ini)
    data_fim = str(data_fim)
    operador = str(operador or "").strip()
    forma_filtro = normalizar_forma_pagamento(forma) if str(forma or "").strip() else ""

    c = conn()
    params = [data_ini, data_fim]
    filtro_operador = ""
    if operador:
        filtro_operador = " AND v.operador = ? "
        params.append(operador)

    df_vendas = pd.read_sql_query(f"""
        SELECT
            v.id AS venda_id,
            v.data,
            v.hora,
            v.operador,
            v.caixa_id,
            v.subtotal,
            v.desconto,
            v.total,
            v.troco,
            v.status,
            v.nfce_status
        FROM pdv_vendas v
        WHERE v.data BETWEEN ? AND ?
          AND v.status = ?
          {filtro_operador}
        ORDER BY v.data DESC, v.hora DESC, v.id DESC
    """, c, params=[*params, PDV_STATUS_VENDA_FINALIZADA])

    if df_vendas.empty:
        c.close()
        return {
            "vendas": df_vendas,
            "pagamentos": pd.DataFrame(),
            "totais_forma": {},
            "qtd_vendas": 0,
            "total_geral": 0.0,
            "total_descontos": 0.0,
            "ticket_medio": 0.0,
        }

    venda_ids = df_vendas["venda_id"].tolist()
    placeholders = ",".join(["?"] * len(venda_ids))
    df_pag = pd.read_sql_query(f"""
        SELECT p.venda_id, p.forma, p.valor, p.troco
        FROM pdv_venda_pagamentos p
        WHERE p.venda_id IN ({placeholders})
    """, c, params=venda_ids)
    c.close()

    if not df_pag.empty:
        df_pag["forma_norm"] = df_pag["forma"].apply(normalizar_forma_pagamento)
        if forma_filtro:
            venda_ids_forma = df_pag.loc[df_pag["forma_norm"] == forma_filtro, "venda_id"].unique().tolist()
            df_vendas = df_vendas[df_vendas["venda_id"].isin(venda_ids_forma)]
            df_pag = df_pag[df_pag["venda_id"].isin(venda_ids_forma)]

    totais_forma = {}
    if not df_pag.empty:
        for forma_nome, grp in df_pag.groupby("forma_norm"):
            totais_forma[forma_nome] = float(grp["valor"].sum())

    qtd = len(df_vendas)
    total_geral = float(df_vendas["total"].sum()) if qtd else 0.0
    total_descontos = float(df_vendas["desconto"].sum()) if qtd else 0.0

    return {
        "vendas": df_vendas,
        "pagamentos": df_pag,
        "totais_forma": totais_forma,
        "qtd_vendas": qtd,
        "total_geral": total_geral,
        "total_descontos": total_descontos,
        "ticket_medio": (total_geral / qtd) if qtd else 0.0,
    }


def pdv_inicializar_estado():
    if "pdv_carrinho" not in st.session_state:
        st.session_state["pdv_carrinho"] = []
    if "pdv_pagamentos" not in st.session_state:
        st.session_state["pdv_pagamentos"] = []
    if "pdv_desconto" not in st.session_state:
        st.session_state["pdv_desconto"] = 0.0
    if "pdv_qtd_rapida" not in st.session_state:
        st.session_state["pdv_qtd_rapida"] = 1.0
    if "pdv_busca" not in st.session_state:
        st.session_state["pdv_busca"] = ""
    if "pdv_forma_sel" not in st.session_state:
        st.session_state["pdv_forma_sel"] = "PIX"
    if "pdv_valor_pg" not in st.session_state:
        st.session_state["pdv_valor_pg"] = 0.0


def pdv_preparar_estado_widgets():
    """
    Aplica resets/sync antes de instanciar widgets com key.
    Nunca alterar pdv_desconto, pdv_busca ou pdv_valor_pg depois dos inputs.
    """
    if st.session_state.pop("_pdv_reset_venda", False):
        st.session_state["pdv_carrinho"] = []
        st.session_state["pdv_pagamentos"] = []
        st.session_state["pdv_desconto"] = 0.0
        st.session_state["pdv_busca"] = ""
        st.session_state["pdv_valor_pg"] = 0.0
        st.session_state.pop("_pdv_falta_ref", None)
    elif st.session_state.pop("_pdv_clear_busca", False):
        st.session_state["pdv_busca"] = ""

    if st.session_state.pop("_pdv_sync_pagamento", False):
        resumo = pdv_resumo(
            carrinho=st.session_state.get("pdv_carrinho", []),
            desconto=float(st.session_state.get("pdv_desconto", 0) or 0),
            pagamentos=st.session_state.get("pdv_pagamentos", []),
        )
        referencia = resumo["falta"] if resumo["falta"] > 0.009 else resumo["total"]
        st.session_state["pdv_valor_pg"] = float(referencia or 0)
        st.session_state["_pdv_falta_ref"] = referencia


def pdv_marcar_sync_pagamento():
    st.session_state["_pdv_sync_pagamento"] = True


def pdv_on_desconto_change():
    pdv_marcar_sync_pagamento()


def pdv_item_subtotal(item):
    return float(item.get("quantidade", 0) or 0) * float(item.get("preco_unitario", 0) or 0)


def pdv_sincronizar_carrinho(carrinho=None):
    carrinho = carrinho if carrinho is not None else st.session_state.get("pdv_carrinho", [])
    for item in carrinho:
        item["subtotal"] = pdv_item_subtotal(item)
    return carrinho


def pdv_validar_precos_carrinho(carrinho):
    erros = []
    for item in carrinho:
        if float(item.get("preco_unitario", 0) or 0) <= 0.001:
            nome = item.get("nome") or item.get("codigo") or "Produto"
            erros.append(f"{nome}: preço não cadastrado")
    return erros


def pdv_on_remover_item(uid):
    pdv_remover_item(uid)
    pdv_marcar_sync_pagamento()


def pdv_on_finalizar_venda(operador_nome):
    if not caixa_aberto():
        st.session_state["_pdv_error"] = "Abra o caixa antes de finalizar a venda."
        return

    try:
        venda_id, resumo_final = pdv_finalizar_venda(
            list(st.session_state["pdv_carrinho"]),
            list(st.session_state["pdv_pagamentos"]),
            float(st.session_state.get("pdv_desconto", 0) or 0),
            operador_nome,
        )
        st.session_state["_pdv_reset_venda"] = True
        st.session_state["_pdv_sync_pagamento"] = True
        st.session_state["_pdv_success"] = (
            f"Venda #{venda_id} • Total {moeda(resumo_final['total'])} • "
            f"Troco {moeda(resumo_final['troco'])}"
        )
    except Exception as e:
        st.session_state["_pdv_error"] = str(e)


def pdv_produto_para_item(prod_row, quantidade=1.0):
    qtd = float(quantidade)
    preco = float(prod_row.get("Preço", 0) or 0)
    return {
        "uid": uuid.uuid4().hex[:10],
        "produto_id": int(prod_row["id"]),
        "codigo": prod_row.get("Código") or "",
        "nome": prod_row.get("Nome") or "",
        "unidade": prod_row.get("Unidade") or "UN",
        "quantidade": qtd,
        "preco_unitario": preco,
        "subtotal": qtd * preco,
        "ncm": prod_row.get("NCM") or "",
        "cst": prod_row.get("CST") or "",
        "icms": float(prod_row.get("ICMS", 0) or 0),
        "pis": float(prod_row.get("PIS", 0) or 0),
        "cofins": float(prod_row.get("COFINS", 0) or 0),
    }


def pdv_on_busca_change():
    """Enter/leitor: código exato ou match único adiciona ao pedido."""
    termo = str(st.session_state.get("pdv_busca", "") or "").strip()
    if not termo:
        return

    if not caixa_aberto():
        st.session_state["_pdv_add_warning"] = "Abra o caixa antes de vender."
        return

    exato = buscar_produto_por_codigo_exato(termo)
    alvo = pd.Series(exato) if exato else pdv_resolver_busca(termo)
    if alvo is None:
        return

    qtd = float(st.session_state.get("pdv_qtd_rapida", 1.0) or 1.0)
    pdv_adicionar_ao_carrinho(alvo, qtd)
    st.session_state["_pdv_clear_busca"] = True
    st.session_state["_pdv_toast"] = f"Adicionado: {alvo.get('Nome', 'Produto')}"


def pdv_on_adicionar_click():
    termo = str(st.session_state.get("pdv_busca", "") or "").strip()
    if not termo:
        st.session_state["_pdv_add_warning"] = "Digite um produto para adicionar."
        return

    if not caixa_aberto():
        st.session_state["_pdv_add_warning"] = "Abra o caixa antes de vender."
        return

    alvo = pdv_resolver_busca(termo)
    if alvo is not None:
        qtd = float(st.session_state.get("pdv_qtd_rapida", 1.0) or 1.0)
        pdv_adicionar_ao_carrinho(alvo, qtd)
        st.session_state["_pdv_clear_busca"] = True
        st.session_state["_pdv_toast"] = f"Adicionado: {alvo.get('Nome', 'Produto')}"
    else:
        st.session_state["_pdv_add_warning"] = "Selecione um produto abaixo ou refine a busca."


def pdv_on_pick_produto(produto_id):
    if not caixa_aberto():
        st.session_state["_pdv_add_warning"] = "Abra o caixa antes de vender."
        return

    catalogo = produtos_catalogo_df()
    if catalogo.empty:
        return

    encontrado = catalogo[catalogo["id"] == int(produto_id)]
    if encontrado.empty:
        return

    qtd = float(st.session_state.get("pdv_qtd_rapida", 1.0) or 1.0)
    prod = encontrado.iloc[0]
    pdv_adicionar_ao_carrinho(prod, qtd)
    st.session_state["_pdv_clear_busca"] = True
    st.session_state["_pdv_toast"] = f"Adicionado: {prod.get('Nome', 'Produto')}"


def pdv_on_limpar_busca():
    st.session_state["_pdv_clear_busca"] = True


def pdv_on_cancelar_venda():
    pdv_limpar_venda()


def pdv_resolver_busca(termo):
    """Retorna produto único para adicionar ou None se precisar escolher na lista."""
    termo = str(termo or "").strip()
    if not termo:
        return None

    exato = buscar_produto_por_codigo_exato(termo)
    if exato:
        return pd.Series(exato)

    resultados = buscar_produtos_catalogo(termo, limite=8)
    if len(resultados) == 1:
        return resultados.iloc[0]

    return None


def pdv_adicionar_ao_carrinho(prod_row, quantidade=1.0):
    item = pdv_produto_para_item(prod_row, quantidade)
    carrinho = st.session_state["pdv_carrinho"]

    for existente in carrinho:
        if (
            existente["produto_id"] == item["produto_id"]
            and abs(existente["preco_unitario"] - item["preco_unitario"]) < 0.001
        ):
            existente["quantidade"] += item["quantidade"]
            existente["subtotal"] = existente["quantidade"] * existente["preco_unitario"]
            pdv_marcar_sync_pagamento()
            return existente

    carrinho.append(item)
    pdv_marcar_sync_pagamento()
    return item


def pdv_remover_item(uid):
    st.session_state["pdv_carrinho"] = [
        i for i in st.session_state["pdv_carrinho"] if i["uid"] != uid
    ]
    pdv_marcar_sync_pagamento()


def pdv_limpar_venda():
    st.session_state["_pdv_reset_venda"] = True


def pdv_resumo_atual():
    return pdv_resumo(
        carrinho=st.session_state.get("pdv_carrinho", []),
        desconto=float(st.session_state.get("pdv_desconto", 0) or 0),
        pagamentos=st.session_state.get("pdv_pagamentos", []),
    )


def pdv_resumo(carrinho=None, desconto=None, pagamentos=None):
    carrinho = pdv_sincronizar_carrinho(carrinho if carrinho is not None else None)
    desconto = float(st.session_state.get("pdv_desconto", 0) if desconto is None else desconto)
    pagamentos = pagamentos if pagamentos is not None else st.session_state.get("pdv_pagamentos", [])

    subtotal = sum(pdv_item_subtotal(i) for i in carrinho)
    total = max(subtotal - desconto, 0.0)
    pago = sum(float(p.get("valor", 0) or 0) for p in pagamentos)
    falta = max(total - pago, 0.0)
    troco = max(pago - total, 0.0)

    return {
        "subtotal": subtotal,
        "desconto": desconto,
        "total": total,
        "pago": pago,
        "falta": falta,
        "troco": troco,
        "itens": len(carrinho),
    }


def pdv_validar_estoque_carrinho(carrinho):
    agregado = {}
    nomes = {}

    for item in carrinho:
        pid = int(item["produto_id"])
        agregado[pid] = agregado.get(pid, 0.0) + float(item["quantidade"])
        nomes[pid] = item.get("nome") or str(pid)

    erros = []
    for pid, qtd_necessaria in agregado.items():
        qtd_estoque, _, _ = estoque_produto(pid)
        if qtd_estoque + 0.0001 < qtd_necessaria:
            erros.append(
                f"{nomes[pid]}: estoque {qtd_estoque:.2f}, necessário {qtd_necessaria:.2f}"
            )
    return erros


def pdv_adicionar_pagamento(forma, valor, troco=0.0):
    valor = float(valor or 0)
    if valor <= 0:
        raise ValueError("Informe um valor de pagamento maior que zero.")

    st.session_state["pdv_pagamentos"].append({
        "uid": uuid.uuid4().hex[:8],
        "forma": forma,
        "valor": valor,
        "troco": float(troco or 0),
    })
    pdv_marcar_sync_pagamento()


def pdv_remover_pagamento(uid):
    st.session_state["pdv_pagamentos"] = [
        p for p in st.session_state["pdv_pagamentos"] if p["uid"] != uid
    ]
    pdv_marcar_sync_pagamento()


def pdv_on_adicionar_pagamento():
    try:
        pdv_adicionar_pagamento(
            st.session_state.get("pdv_forma_sel", "PIX"),
            st.session_state.get("pdv_valor_pg", 0),
        )
    except Exception as e:
        st.session_state["_pdv_error"] = str(e)


def pdv_on_quick_pagamento(forma, valor):
    try:
        pdv_adicionar_pagamento(forma, float(valor or 0))
    except Exception as e:
        st.session_state["_pdv_error"] = str(e)


def pdv_on_remover_pagamento(uid):
    pdv_remover_pagamento(uid)


def pdv_finalizar_venda(carrinho, pagamentos, desconto, operador):
    if not carrinho:
        raise ValueError("Adicione itens à venda antes de finalizar.")

    caixa = caixa_aberto()
    if not caixa:
        raise ValueError("Abra o caixa antes de finalizar a venda.")
    caixa_id = int(caixa["id"])

    carrinho = pdv_sincronizar_carrinho(list(carrinho))
    erros_preco = pdv_validar_precos_carrinho(carrinho)
    if erros_preco:
        raise ValueError(" | ".join(erros_preco))

    resumo = pdv_resumo(carrinho, desconto, pagamentos)
    if resumo["falta"] > 0.009:
        raise ValueError(f"Pagamento incompleto. Falta {moeda(resumo['falta'])}.")

    erros = pdv_validar_estoque_carrinho(carrinho)
    if erros:
        raise ValueError(" | ".join(erros))

    agora = pd.Timestamp.now()
    data_mov = str(agora.date())
    hora = agora.strftime("%H:%M:%S")

    movimentos = []
    for item in carrinho:
        resultado = saida_peps(
            int(item["produto_id"]),
            data_mov,
            float(item["quantidade"]),
            float(item["preco_unitario"]),
            "Venda",
            "",
            f"PDV|uid:{item['uid']}",
            pdv_venda_id=None,
        )
        movimentos.append((item, resultado))

    c = conn()
    cur = c.cursor()
    try:
        cur.execute("""
            INSERT INTO pdv_vendas
            (data, hora, operador, subtotal, desconto, total, troco, status, nfce_status, caixa_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDENTE', ?)
        """, (
            data_mov,
            hora,
            operador,
            resumo["subtotal"],
            resumo["desconto"],
            resumo["total"],
            resumo["troco"],
            PDV_STATUS_VENDA_FINALIZADA,
            caixa_id,
        ))
        venda_id = cur.lastrowid

        for item, resultado in movimentos:
            mov_id = resultado.get("movimentacao_id")
            cmv = float(resultado.get("cmv_peps", 0) or 0)

            if mov_id:
                cur.execute(
                    "UPDATE movimentacoes SET pdv_venda_id = ? WHERE id = ?",
                    (venda_id, mov_id),
                )

            cur.execute("""
                INSERT INTO pdv_venda_itens
                (venda_id, produto_id, codigo, nome, unidade, quantidade, preco_unitario,
                 subtotal, ncm, cst, icms, pis, cofins, cmv_peps, movimentacao_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                venda_id,
                int(item["produto_id"]),
                item.get("codigo"),
                item.get("nome"),
                item.get("unidade"),
                float(item["quantidade"]),
                float(item["preco_unitario"]),
                float(item["subtotal"]),
                item.get("ncm"),
                item.get("cst"),
                float(item.get("icms", 0) or 0),
                float(item.get("pis", 0) or 0),
                float(item.get("cofins", 0) or 0),
                cmv,
                mov_id,
            ))

        for pagamento in pagamentos:
            cur.execute("""
                INSERT INTO pdv_venda_pagamentos (venda_id, forma, valor, troco)
                VALUES (?, ?, ?, ?)
            """, (
                venda_id,
                pagamento.get("forma"),
                float(pagamento.get("valor", 0) or 0),
                float(pagamento.get("troco", 0) or 0),
            ))

        c.commit()
        return venda_id, resumo
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def inserir_produto_catalogo(
    nome,
    categoria,
    unidade,
    estoque_minimo,
    preco_venda,
    codigo="",
    codigo_barras="",
    custo_referencia=0.0,
    ncm="",
    cst="",
    icms=0.0,
    pis=0.0,
    cofins=0.0,
):
    c = conn()
    cur = c.cursor()

    cur.execute("""
        INSERT INTO produtos
        (nome, categoria, unidade, estoque_minimo, preco_venda, codigo, codigo_barras,
         custo_referencia, ncm, cst, icms, pis, cofins)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        nome.strip(),
        categoria.strip(),
        unidade,
        float(estoque_minimo),
        float(preco_venda),
        normalizar_codigo_produto(codigo) if str(codigo or "").strip() else None,
        str(codigo_barras).strip() if str(codigo_barras or "").strip() else None,
        float(custo_referencia or 0),
        str(ncm or "").strip(),
        str(cst or "").strip(),
        float(icms or 0),
        float(pis or 0),
        float(cofins or 0),
    ))

    produto_id = cur.lastrowid

    if not str(codigo or "").strip():
        auto_codigo = gerar_proximo_codigo_sku(categoria, nome, cur)
        cur.execute("UPDATE produtos SET codigo = ? WHERE id = ?", (auto_codigo, produto_id))

    c.commit()
    c.close()
    return produto_id


def get_or_create(nome, categoria="Mercadoria", unidade="UN"):
    c = conn()
    cur = c.cursor()

    cur.execute("SELECT id FROM produtos WHERE nome=?", (nome,))
    r = cur.fetchone()

    if r:
        c.close()
        return r["id"]

    cur.execute("""
        INSERT INTO produtos (nome, categoria, unidade)
        VALUES (?, ?, ?)
    """, (nome, categoria, unidade))

    c.commit()
    i = cur.lastrowid
    cur.execute(
        "UPDATE produtos SET codigo = ? WHERE id = ?",
        (gerar_proximo_codigo_sku(categoria, nome, cur), i)
    )
    c.commit()
    c.close()
    return i


def moeda(v):
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_pct(v):
    return f"{float(v):,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def estoque_produto(pid):
    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT 
            COALESCE(SUM(qtd_restante),0) qtd,
            COALESCE(SUM(qtd_restante*valor_unitario),0) valor
        FROM lotes
        WHERE produto_id=? AND qtd_restante>0
    """, (pid,))

    r = cur.fetchone()
    c.close()

    qtd = float(r["qtd"] or 0)
    val = float(r["valor"] or 0)
    return qtd, val, (val / qtd if qtd else 0)


def entrada(pid, data_mov, qtd, vu, fornecedor="", obs="", chave=""):
    c = conn()
    cur = c.cursor()

    total = float(qtd) * float(vu)

    cur.execute("""
        INSERT INTO lotes 
        (produto_id, data_entrada, qtd_inicial, qtd_restante, valor_unitario, fornecedor, chave_nfe, observacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (pid, str(data_mov), qtd, qtd, vu, fornecedor, chave, obs))

    cur.execute("""
        INSERT INTO movimentacoes 
        (data, produto_id, tipo, quantidade, valor_unitario, valor_total, receita_venda, fornecedor, chave_nfe, observacao)
        VALUES (?, ?, 'Entrada', ?, ?, ?, 0, ?, ?, ?)
    """, (str(data_mov), pid, qtd, vu, total, fornecedor, chave, obs))

    c.commit()
    c.close()


def saida_peps(pid, data_mov, qtd, preco_venda=0, tipo_saida="Venda", motivo_saida="", obs="", pdv_venda_id=None):
    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT id, qtd_restante, valor_unitario
        FROM lotes
        WHERE produto_id=? AND qtd_restante>0
        ORDER BY date(data_entrada) ASC, id ASC
    """, (pid,))

    lotes = cur.fetchall()
    rest = float(qtd)
    cmv = 0.0

    for l in lotes:
        if rest <= 0:
            break

        disp = float(l["qtd_restante"])
        cons = min(rest, disp)
        cmv += cons * float(l["valor_unitario"])

        cur.execute("""
            UPDATE lotes
            SET qtd_restante=?
            WHERE id=?
        """, (disp - cons, l["id"]))

        rest -= cons

    if rest > 0:
        c.rollback()
        c.close()
        raise ValueError(f"Estoque insuficiente. Faltam {rest:.2f} unidades.")

    c.commit()
    c.close()

    _, _, cm = estoque_produto(pid)

    receita = float(qtd) * float(preco_venda or 0) if tipo_saida == "Venda" else 0
    valor_total = receita

    c = conn()
    cur = c.cursor()

    cur.execute("""
        INSERT INTO movimentacoes 
        (data, produto_id, tipo, quantidade, valor_unitario, valor_total, receita_venda,
         cmv_peps, custo_medio_atual, tipo_saida, motivo_saida, observacao, pdv_venda_id)
        VALUES (?, ?, 'Saída', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(data_mov), pid, qtd, preco_venda, valor_total, receita,
        cmv, cm, tipo_saida, motivo_saida, obs, pdv_venda_id
    ))

    movimentacao_id = cur.lastrowid
    c.commit()
    c.close()

    return {
        "movimentacao_id": movimentacao_id,
        "cmv_peps": cmv,
        "receita": receita,
    }


# =========================================================
# RELATÓRIOS
# =========================================================
def estoque_df():
    c = conn()

    df = pd.read_sql_query("""
        SELECT 
            p.id,
            p.codigo Código,
            p.nome Produto,
            p.categoria Categoria,
            p.unidade Unidade,
            p.estoque_minimo 'Estoque Mínimo',
            COALESCE(SUM(l.qtd_restante),0) 'Qtd Atual',
            COALESCE(SUM(l.qtd_restante*l.valor_unitario),0) 'Valor Estoque'
        FROM produtos p
        LEFT JOIN lotes l ON l.produto_id=p.id AND l.qtd_restante>0
        WHERE p.ativo=1
        GROUP BY p.id
        ORDER BY p.codigo, p.nome
    """, c)

    c.close()

    df["Custo Médio Atual"] = df.apply(
        lambda r: r["Valor Estoque"] / r["Qtd Atual"] if r["Qtd Atual"] else 0,
        axis=1
    )

    df["Alerta"] = df.apply(
        lambda r: "⚠️ Baixo" if r["Qtd Atual"] <= r["Estoque Mínimo"] else "OK",
        axis=1
    )

    return df


def mov_df():
    c = conn()

    df = pd.read_sql_query("""
        SELECT 
            m.id,
            m.data Data,
            p.nome Produto,
            p.categoria Categoria,
            m.tipo Tipo,
            m.tipo_saida 'Tipo Saída',
            m.motivo_saida 'Motivo Saída',
            m.quantidade Quantidade,
            m.valor_unitario 'Valor Unitário',
            m.valor_total 'Valor Total',
            m.receita_venda 'Receita Venda',
            m.cmv_peps 'CMV PEPS',
            m.custo_medio_atual 'Custo Médio Após Saída',
            m.fornecedor Fornecedor,
            m.chave_nfe 'Chave NF-e',
            m.observacao Observação
        FROM movimentacoes m
        JOIN produtos p ON p.id=m.produto_id
        ORDER BY date(m.data) DESC, m.id DESC
    """, c)

    c.close()
    return df


def lotes_df():
    c = conn()

    df = pd.read_sql_query("""
        SELECT 
            l.id,
            p.nome Produto,
            p.categoria Categoria,
            l.data_entrada 'Data Entrada',
            l.qtd_inicial 'Qtd Inicial',
            l.qtd_restante 'Qtd Restante',
            l.valor_unitario 'Valor Unitário',
            l.qtd_restante*l.valor_unitario 'Valor Restante',
            l.fornecedor Fornecedor,
            l.chave_nfe 'Chave NF-e',
            l.observacao Observação
        FROM lotes l
        JOIN produtos p ON p.id=l.produto_id
        ORDER BY p.codigo, p.nome, date(l.data_entrada), l.id
    """, c)

    c.close()
    return df


def resumo_cmv(ano, mes):
    ini = f"{ano}-{mes:02d}-01"
    fim = f"{ano+1}-01-01" if mes == 12 else f"{ano}-{mes+1:02d}-01"

    c = conn()

    df = pd.read_sql_query("""
        SELECT 
            p.nome Produto,
            p.categoria Categoria,
            COALESCE(NULLIF(m.tipo_saida,''),'Venda') 'Tipo Saída',
            SUM(CASE WHEN m.tipo='Saída' THEN m.quantidade ELSE 0 END) 'Qtd Saída',
            SUM(CASE WHEN m.tipo='Saída' AND COALESCE(NULLIF(m.tipo_saida,''),'Venda')='Venda' THEN m.receita_venda ELSE 0 END) Receita,
            SUM(CASE WHEN m.tipo='Saída' AND COALESCE(NULLIF(m.tipo_saida,''),'Venda')='Venda' THEN m.cmv_peps ELSE 0 END) 'CMV Venda',
            SUM(CASE WHEN m.tipo='Saída' AND COALESCE(NULLIF(m.tipo_saida,''),'Venda')<>'Venda' THEN m.cmv_peps ELSE 0 END) 'CMV Perdas/Outras Saídas',
            SUM(CASE WHEN m.tipo='Saída' THEN m.cmv_peps ELSE 0 END) 'CMV Total'
        FROM movimentacoes m
        JOIN produtos p ON p.id=m.produto_id
        WHERE date(m.data)>=date(?) AND date(m.data)<date(?)
        GROUP BY p.id, COALESCE(NULLIF(m.tipo_saida,''),'Venda')
        HAVING Receita>0 OR "CMV Venda">0 OR "CMV Perdas/Outras Saídas">0
        ORDER BY "CMV Total" DESC
    """, c, params=(ini, fim))

    c.close()

    if df.empty:
        return df

    df["CMV Venda %"] = df.apply(
        lambda r: (r["CMV Venda"] / r["Receita"] * 100) if r["Receita"] else 0,
        axis=1
    )

    df["CMV Total %"] = df.apply(
        lambda r: (r["CMV Total"] / r["Receita"] * 100) if r["Receita"] else 0,
        axis=1
    )

    df["Lucro Bruto"] = df["Receita"] - df["CMV Total"]

    df["Margem Bruta %"] = df.apply(
        lambda r: (r["Lucro Bruto"] / r["Receita"] * 100) if r["Receita"] else 0,
        axis=1
    )

    df["Status"] = df["CMV Total %"].apply(
        lambda x: "✅ OK" if x <= META_CMV else "⚠️ Acima da meta"
    )

    return df


# =========================================================
# XML NF-e / NFC-e
# =========================================================
def lname(tag):
    return tag.split("}")[-1]


def txt(root, name):
    for e in root.iter():
        if lname(e.tag) == name:
            return e.text or ""
    return ""


def fnum(x):
    return float(str(x or "0").replace(",", "."))


def ler_xml(b):
    root = ET.fromstring(b)
    chave = ""
    fornecedor = ""
    data_em = str(date.today())

    for e in root.iter():
        if lname(e.tag) == "infNFe":
            chave = e.attrib.get("Id", "").replace("NFe", "")

        if lname(e.tag) == "emit":
            for ch in e.iter():
                if lname(ch.tag) == "xNome":
                    fornecedor = ch.text or ""
                    break

    dh = txt(root, "dhEmi") or txt(root, "dEmi")

    if dh:
        data_em = dh[:10]

    itens = []

    for det in root.iter():
        if lname(det.tag) != "det":
            continue

        prod = None

        for ch in det:
            if lname(ch.tag) == "prod":
                prod = ch
                break

        if prod is None:
            continue

        it = {
            "Produto": "",
            "Código": "",
            "NCM": "",
            "CFOP": "",
            "Unidade": "UN",
            "Quantidade": 0.0,
            "Valor Unitário": 0.0,
            "Valor Total": 0.0
        }

        for ch in prod:
            n = lname(ch.tag)
            t = ch.text or ""

            if n == "xProd":
                it["Produto"] = t.strip()
            elif n == "cProd":
                it["Código"] = t.strip()
            elif n == "NCM":
                it["NCM"] = t.strip()
            elif n == "CFOP":
                it["CFOP"] = t.strip()
            elif n == "uCom":
                it["Unidade"] = t.strip()
            elif n == "qCom":
                it["Quantidade"] = fnum(t)
            elif n == "vUnCom":
                it["Valor Unitário"] = fnum(t)
            elif n == "vProd":
                it["Valor Total"] = fnum(t)

        itens.append(it)

    return {
        "fornecedor": fornecedor,
        "data_emissao": data_em,
        "chave": chave,
        "itens": pd.DataFrame(itens)
    }


# =========================================================
# OCR CUPOM
# =========================================================
def ler_texto_imagem(uploaded_file):
    try:
        import pytesseract
        img = Image.open(uploaded_file)
        texto = pytesseract.image_to_string(img, lang="por")
        return texto
    except Exception as e:
        return f"ERRO_OCR: {e}"


def produto_mais_proximo(nome_detectado, produtos):
    nome_up = str(nome_detectado).upper()
    melhor = ""
    melhor_score = 0

    for p in produtos:
        p_up = str(p).upper()
        palavras = [w for w in re.split(r"\W+", p_up) if len(w) >= 3]
        score = sum(1 for w in palavras if w in nome_up)

        if score > melhor_score:
            melhor_score = score
            melhor = p

    return melhor if melhor_score > 0 else ""


def parse_cupom_texto(texto, produtos_lista):
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    itens = []

    for i, linha in enumerate(linhas):
        linha_up = linha.upper()

        ignorar = [
            "CNPJ", "CPF", "DOCUMENTO", "AUXILIAR", "NOTA FISCAL",
            "CONSUMIDOR", "TOTAL", "VALOR", "TRIBUT", "CONSULTE",
            "HTTP", "CHAVE", "SENHA", "CAIXA", "OPERADOR",
            "CARTAO", "CARTÃO", "CREDITO", "CRÉDITO", "BENEFICIO",
            "INCIDENTES", "PROTOCOLO", "IBPT", "FONTE", "EMITIDA",
            "CONTINGENCIA", "CONTINGÊNCIA", "DESCONTO", "PAGAR",
            "DESCRIÇÃO", "DESCRICAO", "QTD", "UND", "UN "
        ]

        if any(p in linha_up for p in ignorar):
            continue

        produto_sistema = produto_mais_proximo(linha, produtos_lista)

        if not produto_sistema:
            continue

        qtd = 1.0
        preco = None

        bloco = " ".join(linhas[i:i+4])

        nums = re.findall(r"\d+[,.]\d{2}", bloco)

        if nums:
            try:
                preco = float(nums[-1].replace(",", "."))
            except:
                preco = None

        qtd_match = re.search(r"(\d+[,.]\d{3}|\d+[,.]\d{2}|\d+)\s*(UND|UN|KG|G|ML|L)?", bloco.upper())

        if qtd_match:
            try:
                q = float(qtd_match.group(1).replace(",", "."))
                if 0 < q <= 100:
                    qtd = q
            except:
                qtd = 1.0

        if preco is not None and preco > 0:
            itens.append({
                "Produto Detectado": linha,
                "Produto Sistema": produto_sistema,
                "Quantidade": qtd,
                "Valor Unitário Venda": preco
            })

    df = pd.DataFrame(itens)

    if df.empty:
        return df

    df = df.drop_duplicates(subset=["Produto Sistema", "Valor Unitário Venda"])
    return df




# =========================================================
# CONFIGURAÇÕES
# =========================================================
def get_config(chave, padrao=""):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,))
    r = cur.fetchone()
    c.close()
    return r["valor"] if r else padrao


def set_config(chave, valor):
    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO configuracoes (chave, valor)
        VALUES (?, ?)
        ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor
    """, (chave, str(valor)))
    c.commit()
    c.close()


def get_float_config(chave, padrao):
    try:
        return float(str(get_config(chave, str(padrao))).replace(",", "."))
    except:
        return float(padrao)


def datas_periodo(periodo, data_ini=None, data_fim=None):
    hoje = pd.Timestamp(date.today())

    if periodo == "Hoje":
        inicio = hoje
        fim = hoje + pd.Timedelta(days=1)
    elif periodo == "Ontem":
        inicio = hoje - pd.Timedelta(days=1)
        fim = hoje
    elif periodo == "Últimos 7 dias":
        inicio = hoje - pd.Timedelta(days=6)
        fim = hoje + pd.Timedelta(days=1)
    elif periodo == "Últimos 30 dias":
        inicio = hoje - pd.Timedelta(days=29)
        fim = hoje + pd.Timedelta(days=1)
    elif periodo == "Este mês":
        inicio = pd.Timestamp(hoje.year, hoje.month, 1)
        fim = pd.Timestamp(hoje.year + 1, 1, 1) if hoje.month == 12 else pd.Timestamp(hoje.year, hoje.month + 1, 1)
    elif periodo == "Mês passado":
        primeiro = pd.Timestamp(hoje.year, hoje.month, 1)
        ultimo_passado = primeiro - pd.Timedelta(days=1)
        inicio = pd.Timestamp(ultimo_passado.year, ultimo_passado.month, 1)
        fim = primeiro
    else:
        inicio = pd.Timestamp(data_ini)
        fim = pd.Timestamp(data_fim) + pd.Timedelta(days=1)

    return str(inicio.date()), str(fim.date())


def periodo_label(inicio, fim):
    fim_visivel = (pd.Timestamp(fim) - pd.Timedelta(days=1)).date()
    return f"{pd.Timestamp(inicio).date().strftime('%d/%m/%Y')} até {fim_visivel.strftime('%d/%m/%Y')}"


def resumo_periodo(inicio, fim):
    c = conn()
    df = pd.read_sql_query("""
        SELECT
            m.data Data,
            p.nome Produto,
            p.categoria Categoria,
            COALESCE(NULLIF(m.tipo_saida,''),'Venda') TipoSaida,
            m.quantidade Quantidade,
            m.receita_venda Receita,
            m.cmv_peps CMV
        FROM movimentacoes m
        JOIN produtos p ON p.id=m.produto_id
        WHERE m.tipo='Saída'
          AND date(m.data)>=date(?)
          AND date(m.data)<date(?)
    """, c, params=(inicio, fim))
    c.close()

    if df.empty:
        return df

    df["Data"] = pd.to_datetime(df["Data"])
    return df



# =========================================================
# MOTOR DE ALERTAS INTELIGENTES ERP
# =========================================================
def gerar_alertas_inteligentes_erp(inicio=None, fim=None):
    """Gera alertas executivos, ações recomendadas e mensagem pronta para WhatsApp."""
    if inicio is None or fim is None:
        inicio, fim = datas_periodo("Este mês")

    nome_empresa = get_config("nome_empresa", "Restaurante")
    meta_cmv = get_float_config("meta_cmv_ideal", META_CMV)
    alerta_cmv = get_float_config("meta_cmv_alerta", meta_cmv + 4)
    critica_cmv = get_float_config("meta_cmv_critica", meta_cmv + 8)

    dre = dre_periodo(inicio, fim)
    df = resumo_periodo(inicio, fim)
    est = estoque_df()
    estoque_baixo = est[est["Qtd Atual"] <= est["Estoque Mínimo"]].copy() if not est.empty else pd.DataFrame()

    receita = float(dre.get("receita", 0) or 0)
    cmv_pct = float(dre.get("cmv_pct", 0) or 0)
    perdas = float(dre.get("perdas", 0) or 0)
    lucro_operacional = float(dre.get("lucro_operacional", 0) or 0)

    alertas = []
    acoes = []

    def add_alerta(nivel, titulo, texto):
        alertas.append({"nivel": nivel, "titulo": titulo, "texto": texto})

    def add_acao(titulo, texto):
        acoes.append({"titulo": titulo, "texto": texto})

    # CMV atual e projeção simples do mês/ritmo atual
    if receita <= 0:
        add_alerta("atenção", "Sem vendas no período", "Ainda não existe base suficiente para analisar CMV, margem e produtos.")
        add_acao("Registrar vendas", "Lance as vendas do dia para liberar a leitura real do painel executivo.")
    elif cmv_pct >= critica_cmv:
        add_alerta("crítico", "CMV crítico", f"CMV em {format_pct(cmv_pct)}, acima da faixa crítica de {format_pct(critica_cmv)}.")
        add_acao("Revisar CMV hoje", "Verifique compras recentes, perdas, ficha técnica e produtos vendidos com preço defasado.")
    elif cmv_pct >= alerta_cmv:
        add_alerta("atenção", "CMV em atenção", f"CMV em {format_pct(cmv_pct)}, acima da meta de {format_pct(meta_cmv)}.")
        add_acao("Atacar produtos vilões", "Abra produtos com CMV alto e priorize reprecificação ou negociação com fornecedor.")
    elif cmv_pct > meta_cmv:
        add_alerta("atenção", "CMV acima da meta", f"CMV em {format_pct(cmv_pct)}, um pouco acima da meta de {format_pct(meta_cmv)}.")
    else:
        add_alerta("ok", "CMV saudável", f"CMV em {format_pct(cmv_pct)}, dentro da meta de {format_pct(meta_cmv)}.")

    # Projeção de fechamento usando o ritmo atual do período selecionado
    if receita > 0:
        add_alerta("projeção", "Projeção de CMV", f"Se o ritmo atual continuar, o CMV tende a fechar próximo de {format_pct(cmv_pct)}.")
        if cmv_pct > meta_cmv:
            add_acao("Corrigir antes do fechamento", "Como o CMV projetado está acima da meta, aja agora antes de fechar o mês no vermelho.")

    # Resultado operacional
    if receita > 0 and lucro_operacional < 0:
        add_alerta("crítico", "DRE negativo", f"Lucro operacional está negativo em {moeda(lucro_operacional)}.")
        add_acao("Separar preço, CMV e despesas", "Veja se o lucro bruto some por causa das despesas ou se o problema nasce no custo dos produtos.")
    elif receita > 0 and lucro_operacional > 0:
        margem_op = lucro_operacional / receita * 100
        add_alerta("ok", "Resultado operacional positivo", f"Lucro operacional positivo com margem de {format_pct(margem_op)}.")

    # Perdas e consumo interno
    if receita > 0 and perdas > 0:
        perdas_pct = perdas / receita * 100
        nivel = "crítico" if perdas_pct >= 5 else "atenção"
        add_alerta(nivel, "Perdas/consumo interno", f"Impacto de {format_pct(perdas_pct)} da receita no período.")
        add_acao("Cortar desperdício", "Filtre movimentações por Perda, Consumo Interno e Ajuste para cobrar motivo e responsável.")

    # Estoque crítico
    if not estoque_baixo.empty:
        pior = estoque_baixo.sort_values("Qtd Atual").iloc[0]
        add_alerta("atenção", "Estoque crítico", f"{len(estoque_baixo)} produto(s) abaixo ou no mínimo. Primeiro item: {pior['Produto']}.")
        add_acao("Comprar antes de perder venda", f"Priorize reposição de {pior['Produto']} e dos itens com maior saída.")

    # Produtos: margem ruim e oportunidades
    prod = pd.DataFrame()
    if df is not None and not df.empty:
        vendas = df[df["TipoSaida"] == "Venda"].copy()
        if not vendas.empty:
            prod = vendas.groupby("Produto", as_index=False).agg(
                Receita=("Receita", "sum"),
                CMV=("CMV", "sum"),
                Quantidade=("Quantidade", "sum"),
            )
            prod["Lucro Bruto"] = prod["Receita"] - prod["CMV"]
            prod["CMV %"] = prod.apply(lambda r: (r["CMV"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)
            prod["Margem %"] = prod.apply(lambda r: (r["Lucro Bruto"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)

    if not prod.empty:
        campeoes = prod.sort_values("Quantidade", ascending=False).head(5)
        ruins = campeoes[campeoes["CMV %"] > meta_cmv]
        if not ruins.empty:
            item = ruins.sort_values("CMV %", ascending=False).iloc[0]
            add_alerta("crítico", "Produto campeão com margem ruim", f"{item['Produto']} vende bem, mas está com CMV de {format_pct(item['CMV %'])}.")
            add_acao("Reprecificar campeão", f"Revise preço, ficha técnica ou fornecedor de {item['Produto']}.")

        # Oportunidade: margem boa, mas venda baixa dentro dos produtos vendidos
        margem_boa = prod[(prod["CMV %"] > 0) & (prod["CMV %"] <= meta_cmv) & (prod["Margem %"] >= 55)]
        if not margem_boa.empty:
            med_qtd = prod["Quantidade"].median()
            oportunidade = margem_boa[margem_boa["Quantidade"] <= med_qtd]
            if not oportunidade.empty:
                item = oportunidade.sort_values("Margem %", ascending=False).iloc[0]
                add_alerta("oportunidade", "Produto bom para promoção", f"{item['Produto']} tem margem alta e baixa saída relativa.")
                add_acao("Promover produto saudável", f"Use {item['Produto']} em combo, vitrine ou sugestão ativa para puxar lucro.")

        # Produto que mais contribui com lucro
        top_lucro = prod.sort_values("Lucro Bruto", ascending=False).head(1)
        if not top_lucro.empty and float(top_lucro.iloc[0]["Lucro Bruto"]) > 0:
            add_alerta("ok", "Produto mais lucrativo", f"{top_lucro.iloc[0]['Produto']} é o maior gerador de lucro bruto no período.")

    # Monta mensagem compacta para WhatsApp
    icone = {"crítico": "🔴", "atenção": "🟡", "ok": "🟢", "projeção": "📈", "oportunidade": "💡"}
    linhas_alertas = []
    for a in alertas[:6]:
        linhas_alertas.append(f"{icone.get(a['nivel'], '•')} {a['titulo']}: {a['texto']}")

    linhas_acoes = []
    for a in acoes[:4]:
        linhas_acoes.append(f"➡️ {a['titulo']}: {a['texto']}")

    mensagem = f"""🚨 ALERTA INTELIGENTE ERP RESTAURANTE

{nome_empresa}
Data: {date.today().strftime('%d/%m/%Y')}

Resumo:
• Receita: {moeda(receita)}
• CMV: {format_pct(cmv_pct)} | Meta: {format_pct(meta_cmv)}
• Lucro operacional: {moeda(lucro_operacional)}
• Estoque crítico: {len(estoque_baixo)} produto(s)

Alertas:
{chr(10).join(linhas_alertas) if linhas_alertas else 'Nenhum alerta crítico no momento.'}

O que fazer:
{chr(10).join(linhas_acoes) if linhas_acoes else 'Manter rotina de acompanhamento diário.'}"""

    return {
        "alertas": alertas,
        "acoes": acoes,
        "mensagem_whatsapp": mensagem,
        "dre": dre,
        "produtos": prod,
        "estoque_baixo": estoque_baixo,
    }


# =========================================================
# PROJEÇÃO FINANCEIRA / OPERACIONAL
# =========================================================
def projecao_financeira_mes(inicio=None, fim=None):
    """Calcula projeção simples do mês atual com base no ritmo realizado até hoje."""
    hoje_ts = pd.Timestamp(date.today())
    mes_inicio = pd.Timestamp(hoje_ts.year, hoje_ts.month, 1)
    mes_fim = pd.Timestamp(hoje_ts.year + 1, 1, 1) if hoje_ts.month == 12 else pd.Timestamp(hoje_ts.year, hoje_ts.month + 1, 1)

    inicio_mes = str(mes_inicio.date())
    fim_mes = str(mes_fim.date())
    fim_realizado = str((hoje_ts + pd.Timedelta(days=1)).date())

    dre_realizado = dre_periodo(inicio_mes, fim_realizado)
    df_realizado = resumo_periodo(inicio_mes, fim_realizado)

    dias_no_mes = int((mes_fim - mes_inicio).days)
    dia_atual = min(int(hoje_ts.day), dias_no_mes)
    fator = dias_no_mes / dia_atual if dia_atual > 0 else 1

    receita_realizada = float(dre_realizado.get("receita", 0) or 0)
    cmv_realizado = float(dre_realizado.get("cmv_total", 0) or 0)
    perdas_realizadas = float(dre_realizado.get("perdas", 0) or 0)
    despesas_realizadas = float(dre_realizado.get("despesas", 0) or 0)
    lucro_realizado = float(dre_realizado.get("lucro_operacional", 0) or 0)

    receita_proj = receita_realizada * fator
    cmv_proj = cmv_realizado * fator
    perdas_proj = perdas_realizadas * fator
    despesas_proj = despesas_realizadas * fator
    lucro_bruto_proj = receita_proj - cmv_proj
    lucro_operacional_proj = lucro_bruto_proj - despesas_proj

    cmv_pct_proj = (cmv_proj / receita_proj * 100) if receita_proj else 0
    margem_op_proj = (lucro_operacional_proj / receita_proj * 100) if receita_proj else 0

    meta_cmv = get_float_config("meta_cmv_ideal", META_CMV)
    critica_cmv = get_float_config("meta_cmv_critica", meta_cmv + 8)

    if receita_realizada <= 0:
        tendencia = "Sem dados"
        nivel = "atenção"
        resumo = "Ainda não há vendas suficientes no mês para projetar o fechamento."
    elif lucro_operacional_proj < 0 or cmv_pct_proj >= critica_cmv:
        tendencia = "Crítica"
        nivel = "crítico"
        resumo = "O mês tende a fechar com risco alto: CMV elevado ou resultado operacional negativo."
    elif cmv_pct_proj > meta_cmv or margem_op_proj < 10:
        tendencia = "Atenção"
        nivel = "atenção"
        resumo = "O mês tende a fechar com pontos de atenção. Corrigir agora melhora o fechamento."
    else:
        tendencia = "Saudável"
        nivel = "ok"
        resumo = "O ritmo atual indica fechamento saudável dentro dos principais parâmetros."

    recomendacoes = []
    if receita_realizada <= 0:
        recomendacoes.append("Lançar vendas do dia para liberar a projeção real do mês.")
    if cmv_pct_proj > meta_cmv:
        recomendacoes.append("Revisar produtos com CMV alto e fornecedores antes do fechamento mensal.")
    if lucro_operacional_proj < 0:
        recomendacoes.append("Separar o problema entre preço, CMV e despesas para evitar fechar o mês no prejuízo.")
    if perdas_proj > 0 and receita_proj > 0 and (perdas_proj / receita_proj * 100) >= 3:
        recomendacoes.append("Controlar perdas e consumo interno, pois estão pressionando o resultado projetado.")
    if not recomendacoes:
        recomendacoes.append("Manter acompanhamento diário de CMV, estoque crítico e margem por produto.")

    return {
        "dias_no_mes": dias_no_mes,
        "dia_atual": dia_atual,
        "fator": fator,
        "receita_realizada": receita_realizada,
        "receita_proj": receita_proj,
        "cmv_proj": cmv_proj,
        "cmv_pct_proj": cmv_pct_proj,
        "perdas_proj": perdas_proj,
        "despesas_proj": despesas_proj,
        "lucro_bruto_proj": lucro_bruto_proj,
        "lucro_operacional_proj": lucro_operacional_proj,
        "margem_op_proj": margem_op_proj,
        "tendencia": tendencia,
        "nivel": nivel,
        "resumo": resumo,
        "recomendacoes": recomendacoes,
    }

# =========================================================
# WHATSAPP / Z-API
# =========================================================
ZAPI_INSTANCE = "3F3825B4243AF30BEB028E55E4F73592"
ZAPI_TOKEN = "A90F201DAC1257487E0191F8"

# Em algumas contas da Z-API existe também o Client-Token.
# Se sua conta exigir, coloque esse token em Configurações depois.
ZAPI_CLIENT_TOKEN_PADRAO = ""


def limpar_numero_whatsapp(numero):
    numero = str(numero or "").strip()
    numero = numero.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    numero = re.sub(r"\D", "", numero)
    return numero


def enviar_whatsapp_zapi(numero, mensagem):
    numero = limpar_numero_whatsapp(numero)

    if not numero:
        return False, "Número de WhatsApp não informado."

    if len(numero) < 12:
        return False, "Número inválido. Use o formato com DDI e DDD. Exemplo: 5521999999999."

    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE}/token/{ZAPI_TOKEN}/send-text"

    client_token = get_config("zapi_client_token", ZAPI_CLIENT_TOKEN_PADRAO).strip()

    headers = {"Content-Type": "application/json"}
    if client_token:
        headers["Client-Token"] = client_token

    payload = {
        "phone": numero,
        "message": mensagem
    }

    try:
        resposta = requests.post(url, json=payload, headers=headers, timeout=20)
        if resposta.status_code in (200, 201):
            return True, "Mensagem enviada com sucesso."

        detalhe = resposta.text[:500] if resposta.text else ""
        return False, f"Erro Z-API {resposta.status_code}: {detalhe}"

    except Exception as e:
        return False, f"Erro ao conectar na Z-API: {e}"

# =========================================================
# DASHBOARD PREMIUM
# =========================================================
def metric_card(label, value, help_text="", tone="default", icon="📊"):
    colors = {
        "default": "#0f172a",
        "good": "#166534",
        "warn": "#92400e",
        "bad": "#991b1b",
        "blue": "#1d4ed8",
        "purple": "#6d28d9",
    }

    bg_colors = {
        "default": "#f8fafc",
        "good": "#f0fdf4",
        "warn": "#fffbeb",
        "bad": "#fef2f2",
        "blue": "#eff6ff",
        "purple": "#faf5ff",
    }

    color = colors.get(tone, colors["default"])
    bg = bg_colors.get(tone, bg_colors["default"])

    html = f"""
<div style="background:linear-gradient(180deg,#ffffff 0%,{bg} 100%);border:1px solid #e5e7eb;border-left:5px solid {color};border-radius:18px;padding:22px 24px;box-shadow:0 8px 22px rgba(15,23,42,0.06);min-height:155px;">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
<div style="font-size:13px;color:#64748b;font-weight:700;letter-spacing:0.03em;text-transform:uppercase;">{label}</div>
<div style="width:34px;height:34px;border-radius:12px;background:{bg};color:{color};display:flex;align-items:center;justify-content:center;font-size:18px;">{icon}</div>
</div>
<div style="font-size:34px;color:#0f172a;font-weight:850;line-height:1.1;margin-top:6px;">{value}</div>
<div style="font-size:12px;color:#64748b;margin-top:10px;font-weight:500;">{help_text}</div>
</div>
"""

    st.markdown(html, unsafe_allow_html=True)

def alerta_box(texto, tone="default"):
    colors = {
        "default": "#334155",
        "good": "#166534",
        "warn": "#92400e",
        "bad": "#991b1b",
    }

    bg_colors = {
        "default": "#f8fafc",
        "good": "#f0fdf4",
        "warn": "#fffbeb",
        "bad": "#fef2f2",
    }

    color = colors.get(tone, colors["default"])
    bg = bg_colors.get(tone, bg_colors["default"])

    st.markdown(
        f"""
<div style="
background:{bg};
border-left:5px solid {color};
padding:14px 18px;
border-radius:12px;
margin-bottom:10px;
font-weight:600;
color:{color};
box-shadow:0 4px 12px rgba(0,0,0,0.04);
">
{texto}
</div>
""",
        unsafe_allow_html=True
    )
# =========================================================
# PRECIFICAÇÃO
# =========================================================
def precificacao_df(meta_cmv):
    est = estoque_df()
    produtos = produtos_df()

    if est.empty:
        return pd.DataFrame()

    df = est.merge(
        produtos[["id", "preco_venda"]],
        on="id",
        how="left"
    )

    df["Preço Venda Atual"] = pd.to_numeric(df["preco_venda"], errors="coerce").fillna(0)
    df["Custo Atual PEPS/Médio"] = pd.to_numeric(df["Custo Médio Atual"], errors="coerce").fillna(0)

    df["CMV Atual %"] = df.apply(
        lambda r: (r["Custo Atual PEPS/Médio"] / r["Preço Venda Atual"] * 100)
        if r["Preço Venda Atual"] > 0 else 0,
        axis=1
    )

    df["Preço Mínimo pela Meta"] = df.apply(
        lambda r: (r["Custo Atual PEPS/Médio"] / (meta_cmv / 100))
        if meta_cmv > 0 and r["Custo Atual PEPS/Médio"] > 0 else 0,
        axis=1
    )

    df["Lucro Bruto Unitário"] = df["Preço Venda Atual"] - df["Custo Atual PEPS/Médio"]

    df["Margem Bruta %"] = df.apply(
        lambda r: (r["Lucro Bruto Unitário"] / r["Preço Venda Atual"] * 100)
        if r["Preço Venda Atual"] > 0 else 0,
        axis=1
    )

    def status(r):
        if r["Preço Venda Atual"] <= 0:
            return "⚠️ Sem preço de venda"
        if r["Custo Atual PEPS/Médio"] <= 0:
            return "⚠️ Sem custo/estoque"
        if r["CMV Atual %"] <= meta_cmv:
            return "✅ OK"
        return "🔴 Reprecificar"

    df["Status"] = df.apply(status, axis=1)

    df["Diferença para Preço Ideal"] = df["Preço Mínimo pela Meta"] - df["Preço Venda Atual"]

    cols = [
        "Produto", "Categoria", "Qtd Atual", "Custo Atual PEPS/Médio",
        "Preço Venda Atual", "CMV Atual %", "Preço Mínimo pela Meta",
        "Diferença para Preço Ideal", "Lucro Bruto Unitário",
        "Margem Bruta %", "Status"
    ]

    return df[cols].sort_values(["Status", "CMV Atual %"], ascending=[False, False])


# =========================================================
# DRE GERENCIAL / CONTAS A PAGAR
# =========================================================
CATEGORIAS_DESPESA = [
    "Aluguel", "Funcionários", "Energia", "Água", "Internet", "Contador",
    "Taxas/Cartões", "iFood/Delivery", "Marketing", "Manutenção", "Embalagens", "Outros"
]


def despesas_df(inicio=None, fim=None):
    c = conn()

    if inicio and fim:
        df = pd.read_sql_query("""
            SELECT 
                id,
                data Data,
                categoria Categoria,
                descricao Descrição,
                valor Valor,
                observacao Observação,
                COALESCE(status, 'Em aberto') Status
            FROM despesas
            WHERE date(data)>=date(?) AND date(data)<date(?)
            ORDER BY date(data) DESC, id DESC
        """, c, params=(inicio, fim))
    else:
        df = pd.read_sql_query("""
            SELECT 
                id,
                data Data,
                categoria Categoria,
                descricao Descrição,
                valor Valor,
                observacao Observação,
                COALESCE(status, 'Em aberto') Status
            FROM despesas
            ORDER BY date(data) DESC, id DESC
        """, c)

    c.close()
    return df


def despesas_com_status_df(inicio=None, fim=None):
    c = conn()

    if inicio and fim:
        df = pd.read_sql_query("""
            SELECT
                id,
                data,
                categoria,
                descricao,
                valor,
                observacao,
                COALESCE(status, 'Em aberto') AS status
            FROM despesas
            WHERE date(data)>=date(?) AND date(data)<date(?)
            ORDER BY date(data) ASC, id ASC
        """, c, params=(inicio, fim))
    else:
        df = pd.read_sql_query("""
            SELECT
                id,
                data,
                categoria,
                descricao,
                valor,
                observacao,
                COALESCE(status, 'Em aberto') AS status
            FROM despesas
            ORDER BY date(data) ASC, id ASC
        """, c)

    c.close()
    return df


def situacao_despesa(status, data_ref, hoje=None):
    hoje = hoje or date.today()
    status = str(status or "Em aberto").strip()

    if status == "Pago":
        return "Pago", "🟢 Pago"

    try:
        venc = pd.Timestamp(data_ref).date()
    except Exception:
        venc = hoje

    if venc < hoje:
        return "Vencida", "🔴 Vencida"

    return "Em aberto", "🟡 Em aberto"


def resumo_contas_pagar(df, hoje=None):
    hoje = hoje or date.today()

    if df is None or df.empty:
        return {
            "total_aberto": 0.0,
            "total_vencidas": 0.0,
            "total_pagas": 0.0,
            "total_periodo": 0.0,
            "qtd_aberto": 0,
            "qtd_vencidas": 0,
            "qtd_pagas": 0,
            "qtd_total": 0,
        }

    work = df.copy()
    work["status"] = work["status"].fillna("Em aberto")
    work["valor"] = work["valor"].astype(float)

    abertas = work[work["status"] != "Pago"]
    pagas = work[work["status"] == "Pago"]

    vencidas = abertas[
        abertas["data"].apply(lambda d: pd.Timestamp(d).date() < hoje)
    ]

    return {
        "total_aberto": float(abertas["valor"].sum()),
        "total_vencidas": float(vencidas["valor"].sum()),
        "total_pagas": float(pagas["valor"].sum()),
        "total_periodo": float(work["valor"].sum()),
        "qtd_aberto": len(abertas),
        "qtd_vencidas": len(vencidas),
        "qtd_pagas": len(pagas),
        "qtd_total": len(work),
    }


def filtrar_despesas_contas(df, status_filtro="Todos", categoria="Todas", busca="", hoje=None):
    hoje = hoje or date.today()

    if df is None or df.empty:
        return df

    out = df.copy()

    if categoria and categoria != "Todas":
        out = out[out["categoria"] == categoria]

    if busca and str(busca).strip():
        termo = str(busca).strip().lower()
        out = out[
            out["descricao"].fillna("").str.lower().str.contains(termo, na=False)
            | out["categoria"].fillna("").str.lower().str.contains(termo, na=False)
            | out["observacao"].fillna("").str.lower().str.contains(termo, na=False)
        ]

    if status_filtro == "Em aberto":
        out = out[out["status"] != "Pago"]
    elif status_filtro == "Pago":
        out = out[out["status"] == "Pago"]
    elif status_filtro == "Vencidas":
        out = out[
            (out["status"] != "Pago")
            & out["data"].apply(lambda d: pd.Timestamp(d).date() < hoje)
        ]

    if out.empty:
        return out

    out = out.copy()
    out["_situacao_ordem"] = out.apply(
        lambda r: 0 if situacao_despesa(r["status"], r["data"], hoje)[0] == "Vencida"
        else (1 if situacao_despesa(r["status"], r["data"], hoje)[0] == "Em aberto" else 2),
        axis=1,
    )
    out = out.sort_values(["_situacao_ordem", "data", "id"]).drop(columns=["_situacao_ordem"])
    return out


def inserir_despesa(data_mov, categoria, descricao, valor, observacao="", status="Em aberto"):
    c = conn()
    cur = c.cursor()

    cur.execute("""
        INSERT INTO despesas (data, categoria, descricao, valor, observacao, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (str(data_mov), categoria, descricao, float(valor), observacao, status))

    c.commit()
    c.close()


def atualizar_status_despesa(id_despesa, status):
    c = conn()
    cur = c.cursor()

    cur.execute(
        "UPDATE despesas SET status = ? WHERE id = ?",
        (str(status), int(id_despesa))
    )

    c.commit()
    c.close()


def excluir_despesa(id_despesa):
    c = conn()
    cur = c.cursor()

    cur.execute(
        "DELETE FROM despesas WHERE id = ?",
        (int(id_despesa),)
    )

    c.commit()
    c.close()


def dre_periodo(inicio, fim):
    df = resumo_periodo(inicio, fim)
    despesas = despesas_df(inicio, fim)

    receita = df.loc[df["TipoSaida"] == "Venda", "Receita"].sum() if not df.empty else 0
    cmv_venda = df.loc[df["TipoSaida"] == "Venda", "CMV"].sum() if not df.empty else 0
    perdas = df.loc[df["TipoSaida"] != "Venda", "CMV"].sum() if not df.empty else 0
    cmv_total = cmv_venda + perdas

    lucro_bruto = receita - cmv_total
    desp_total = despesas["Valor"].sum() if not despesas.empty else 0
    lucro_operacional = lucro_bruto - desp_total

    cmv_pct = (cmv_total / receita * 100) if receita else 0
    perdas_pct = (perdas / receita * 100) if receita else 0
    margem_bruta_pct = (lucro_bruto / receita * 100) if receita else 0
    margem_operacional_pct = (lucro_operacional / receita * 100) if receita else 0

    return {
        "receita": receita,
        "cmv_venda": cmv_venda,
        "perdas": perdas,
        "cmv_total": cmv_total,
        "lucro_bruto": lucro_bruto,
        "despesas": desp_total,
        "lucro_operacional": lucro_operacional,
        "cmv_pct": cmv_pct,
        "perdas_pct": perdas_pct,
        "margem_bruta_pct": margem_bruta_pct,
        "margem_operacional_pct": margem_operacional_pct,
        "df_mov": df,
        "df_despesas": despesas,
    }


# =========================================================
# LOGIN SIMPLES + USUÁRIOS
# =========================================================
USERS_PATH = Path("usuarios.json")
AUTH_QUERY_PARAM = "auth"
AUTH_DIAS_VALIDADE = 7


def garantir_usuarios_json():
    if not USERS_PATH.exists():
        usuarios = [
            {"usuario": "admin", "senha": "1234", "tipo": "admin", "nome": "Administrador", "ativo": True}
        ]
        USERS_PATH.write_text(json.dumps(usuarios, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_usuarios():
    garantir_usuarios_json()
    try:
        usuarios = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        if not isinstance(usuarios, list):
            return []
        return usuarios
    except Exception:
        return []


def salvar_usuarios(usuarios):
    USERS_PATH.write_text(json.dumps(usuarios, ensure_ascii=False, indent=2), encoding="utf-8")


def autenticar_json(usuario, senha):
    for u in carregar_usuarios():
        if str(u.get("usuario", "")).strip() == str(usuario).strip() and str(u.get("senha", "")) == str(senha):
            if u.get("ativo", True) is False:
                return None
            return {
                "usuario": u.get("usuario", ""),
                "nome": u.get("nome", u.get("usuario", "")),
                "tipo": u.get("tipo", "operador")
            }
    return None


def usuario_dict_por_login(login):
    login = str(login or "").strip()
    for u in carregar_usuarios():
        if str(u.get("usuario", "")).strip() == login:
            if u.get("ativo", True) is False:
                return None
            return {
                "usuario": u.get("usuario", ""),
                "nome": u.get("nome", u.get("usuario", "")),
                "tipo": u.get("tipo", "operador"),
            }
    return None


def criar_token_sessao(login_usuario):
    token = secrets.token_urlsafe(32)
    agora = pd.Timestamp.now()
    expira = agora + pd.Timedelta(days=AUTH_DIAS_VALIDADE)

    c = conn()
    cur = c.cursor()
    cur.execute("""
        INSERT INTO sessoes_auth (token, usuario, criado_em, expira_em)
        VALUES (?, ?, ?, ?)
    """, (token, str(login_usuario), str(agora), str(expira)))
    c.commit()
    c.close()
    return token


def revogar_token_sessao(token):
    if not token:
        return

    c = conn()
    cur = c.cursor()
    cur.execute("DELETE FROM sessoes_auth WHERE token = ?", (str(token),))
    c.commit()
    c.close()


def buscar_usuario_por_token(token):
    if not token:
        return None

    c = conn()
    cur = c.cursor()
    cur.execute("""
        SELECT usuario
        FROM sessoes_auth
        WHERE token = ?
          AND datetime(expira_em) > datetime('now')
    """, (str(token),))
    row = cur.fetchone()
    c.close()

    if not row:
        return None

    user = usuario_dict_por_login(row["usuario"])
    if not user:
        revogar_token_sessao(token)
    return user


def limpar_auth_url():
    if AUTH_QUERY_PARAM in st.query_params:
        del st.query_params[AUTH_QUERY_PARAM]


def persistir_login(user):
    token = criar_token_sessao(user["usuario"])
    st.session_state["usuario_logado"] = user
    st.session_state["auth_token"] = token
    st.query_params[AUTH_QUERY_PARAM] = token


def sincronizar_auth_url():
    if not usuario_logado():
        return

    token = st.session_state.get("auth_token")
    if not token:
        token = criar_token_sessao(st.session_state["usuario_logado"]["usuario"])
        st.session_state["auth_token"] = token

    if st.query_params.get(AUTH_QUERY_PARAM) != token:
        st.query_params[AUTH_QUERY_PARAM] = token


def restaurar_login_persistente():
    if st.session_state.get("usuario_logado"):
        return True

    token = st.query_params.get(AUTH_QUERY_PARAM)
    if not token:
        return False

    user = buscar_usuario_por_token(token)
    if user:
        st.session_state["usuario_logado"] = user
        st.session_state["auth_token"] = token
        return True

    limpar_auth_url()
    return False


def fazer_logout():
    token = st.session_state.get("auth_token") or st.query_params.get(AUTH_QUERY_PARAM)
    revogar_token_sessao(token)
    st.session_state.pop("usuario_logado", None)
    st.session_state.pop("auth_token", None)
    limpar_auth_url()
    st.rerun()


def usuario_logado():
    return st.session_state.get("usuario_logado")


def exigir_login():
    restaurar_login_persistente()

    if usuario_logado():
        sincronizar_auth_url()
        return

    st.markdown("""
        <div style="max-width:520px; margin: 45px auto 15px auto; padding: 30px; border:1px solid #e5e7eb; border-radius:20px; box-shadow:0 8px 24px rgba(15,23,42,.08); background:white;">
            <h2 style="margin-bottom:4px;">🔐 Acesso ao Sistema</h2>
            <p style="color:#64748b; margin-top:0;">Entre para acessar o ERP.</p>
        </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar")

        if entrar:
            user = autenticar_json(usuario, senha)
            if user:
                persistir_login(user)
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")

    st.info("Acesso inicial: **admin** / **1234**")
    st.stop()


def menus_por_perfil():
    user = usuario_logado()
    tipo = str(user.get("tipo", "")).lower() if user else ""

    todos = [
        "Painel CMV",
        "📱 Executivo Mobile",
        "Precificação",
        "DRE Gerencial",
        "Contas a Pagar",
        "Curva ABC",
        "Relatório Vendas PDV",
        "Produtos",
        "Configurações",
        "Usuários",
        "Importar Nota",
        "Importar Cupom Foto",
        "Entrada Manual",
        "Lançar Saída",
        "⚡ Operacional",
        "Estoque Atual",
        "Lotes",
        "Movimentações",
        "Exportar"
    ]

    if tipo == "admin":
        return todos

    if tipo == "gerente":
        return [m for m in todos if m != "Usuários"]

    if tipo == "financeiro":
        return [
            "Painel CMV",
            "📱 Executivo Mobile",
            "Precificação",
            "DRE Gerencial",
            "Contas a Pagar",
            "Curva ABC",
            "Relatório Vendas PDV",
            "Estoque Atual",
            "Movimentações",
            "Exportar"
        ]

    # operador
    return [
        "⚡ Operacional",
        "Importar Nota",
        "Importar Cupom Foto",
        "Entrada Manual",
        "Lançar Saída",
        "Estoque Atual",
        "Lotes",
        "Movimentações"
    ]


def logout_sidebar():
    user = usuario_logado()
    if not user:
        return

    st.sidebar.markdown("---")
    st.sidebar.write(f"👤 **{user.get('nome', user.get('usuario'))}**")
    st.sidebar.caption(f"Perfil: {user.get('tipo', '-')}")
    if st.sidebar.button("Sair"):
        fazer_logout()


# =========================================================
# APP
# =========================================================
init_db()
seed()
garantir_usuarios_json()
exigir_login()
user = st.session_state.get("usuario_logado", {})

menus_permitidos = menus_por_perfil()
menu = st.radio(
    "Navegação",
    menus_permitidos,
    horizontal=True
)
# logout_sidebar()

if menu != "⚡ Operacional":
    st.markdown("""
<div style="
    background: linear-gradient(135deg, #111827 0%, #1e3a8a 55%, #2563eb 100%);
    padding: 28px 32px;
    border-radius: 24px;
    color: white;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.12);
">
    <div style="font-size: 14px; opacity: 0.8;">ERP Inteligente para Restaurantes</div>
    <div style="font-size: 34px; font-weight: 800; margin-top: 6px;">
        📦 Estoque, CMV e Gestão Operacional
    </div>
    <div style="font-size: 15px; opacity: 0.85; margin-top: 8px;">
        Controle PEPS • CMV em tempo real • Alertas inteligentes • Apoio à decisão
    </div>
</div>
""", unsafe_allow_html=True)

col_user, col_sair = st.columns([8, 1])

with col_user:
    st.caption(f"👤 {user.get('nome', user.get('usuario'))} | Perfil: {user.get('tipo', '-')}")
with col_sair:
    if st.button("Sair"):
        fazer_logout()

pdf = produtos_df()


# =========================================================
# PAINEL CMV
# =========================================================
if menu == "Painel CMV":
    st.markdown("""
        <style>
            .block-container {padding-top: 1.4rem;}
            [data-testid="stMetricValue"] {
    font-size: 34px;
    font-weight: 800;
    color: #111827;
    letter-spacing: -1px;
}

[data-testid="stMetricLabel"] {
    font-size: 13px;
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
}
            div[data-testid="stDataFrame"] {border-radius: 14px; overflow: hidden;}
        </style>
    """, unsafe_allow_html=True)

    hoje = date.today()
    nome_empresa = get_config("nome_empresa", "Restaurante")
    meta_padrao = get_float_config("meta_cmv_ideal", META_CMV)
    alerta_cmv = get_float_config("meta_cmv_alerta", meta_padrao + 4)
    critica_cmv = get_float_config("meta_cmv_critica", meta_padrao + 8)

    st.markdown(f"""
        <div style="margin-bottom: 8px;">
            <h1 style="margin-bottom: 0; color:#0f172a;">Painel Executivo</h1>
            <p style="color:#64748b; font-size:15px; margin-top:4px;">
                {nome_empresa} • visão rápida para dono/CFO: faturamento, CMV, margem, perdas, estoque crítico e produtos que mais impactam o resultado.
            </p>
        </div>
    """, unsafe_allow_html=True)

    f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1])
    periodo = f1.selectbox(
        "Período",
        ["Hoje", "Ontem", "Últimos 7 dias", "Últimos 30 dias", "Este mês", "Mês passado", "Personalizado"],
        index=4
    )

    data_ini = hoje.replace(day=1)
    data_fim = hoje

    if periodo == "Personalizado":
        data_ini = f2.date_input("Data inicial", value=data_ini)
        data_fim = f3.date_input("Data final", value=data_fim)
    else:
        f2.write("")
        f3.write("")

    meta_cmv_input = f4.number_input(
        "Meta CMV (%)",
        min_value=1.0,
        max_value=90.0,
        value=float(meta_padrao),
        step=0.5,
        help="Você pode analisar com outra meta aqui. Para salvar como padrão, use Configurações."
    )

    inicio_periodo, fim_periodo = datas_periodo(periodo, data_ini, data_fim)
    label_periodo = periodo_label(inicio_periodo, fim_periodo)

    df_periodo = resumo_periodo(inicio_periodo, fim_periodo)

    inicio_hoje = str(hoje)
    fim_amanha = str(pd.Timestamp(hoje) + pd.Timedelta(days=1))[:10]
    df_hoje = resumo_periodo(inicio_hoje, fim_amanha)
    est = estoque_df()

    receita_periodo = df_periodo.loc[df_periodo["TipoSaida"] == "Venda", "Receita"].sum() if not df_periodo.empty else 0
    cmv_periodo = df_periodo["CMV"].sum() if not df_periodo.empty else 0
    perdas_periodo = df_periodo.loc[df_periodo["TipoSaida"] != "Venda", "CMV"].sum() if not df_periodo.empty else 0
    lucro_periodo = receita_periodo - cmv_periodo
    cmv_pct_periodo = (cmv_periodo / receita_periodo * 100) if receita_periodo else 0
    margem_periodo = (lucro_periodo / receita_periodo * 100) if receita_periodo else 0

    receita_hoje = df_hoje.loc[df_hoje["TipoSaida"] == "Venda", "Receita"].sum() if not df_hoje.empty else 0
    cmv_hoje = df_hoje["CMV"].sum() if not df_hoje.empty else 0
    perdas_hoje = df_hoje.loc[df_hoje["TipoSaida"] != "Venda", "CMV"].sum() if not df_hoje.empty else 0
    lucro_hoje = receita_hoje - cmv_hoje
    cmv_pct_hoje = (cmv_hoje / receita_hoje * 100) if receita_hoje else 0

    qtd_vendas = df_periodo.loc[df_periodo["TipoSaida"] == "Venda", "Quantidade"].sum() if not df_periodo.empty else 0
    ticket_medio = receita_periodo / qtd_vendas if qtd_vendas else 0

    estoque_valor = est["Valor Estoque"].sum() if not est.empty else 0
    estoque_baixo_qtd = len(est[est["Alerta"] == "⚠️ Baixo"]) if not est.empty else 0

    st.markdown(f"### Resumo do período • {label_periodo}")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    if cmv_pct_periodo <= meta_cmv_input:
        cmv_tone = "good"
    elif cmv_pct_periodo <= alerta_cmv:
        cmv_tone = "warn"
    else:
        cmv_tone = "bad"

    with c1:
        metric_card("Faturamento", moeda(receita_periodo), "Receita de vendas lançadas", "blue")
    with c2:
        metric_card("CMV Total", format_pct(cmv_pct_periodo), f"Meta: {format_pct(meta_cmv_input)}", cmv_tone)
    with c3:
        metric_card("Lucro Bruto", moeda(lucro_periodo), f"Margem: {format_pct(margem_periodo)}", "good" if lucro_periodo >= 0 else "bad")
    with c4:
        metric_card("Perdas / Interno", moeda(perdas_periodo), "Sem receita, mas com custo", "warn" if perdas_periodo > 0 else "good")
    with c5:
        metric_card("Ticket Médio", moeda(ticket_medio), "Receita ÷ quantidade vendida", "purple")
    with c6:
        metric_card("Valor em Estoque", moeda(estoque_valor), f"{estoque_baixo_qtd} item(ns) em alerta", "warn" if estoque_baixo_qtd else "good")

    st.markdown("### Hoje")
    h1, h2, h3, h4 = st.columns(4)
    with h1:
        metric_card("Faturamento Hoje", moeda(receita_hoje), "Vendas do dia", "blue")
    with h2:
        metric_card("CMV Hoje", format_pct(cmv_pct_hoje), moeda(cmv_hoje), "good" if cmv_pct_hoje <= meta_cmv_input and receita_hoje else "warn")
    with h3:
        metric_card("Lucro Hoje", moeda(lucro_hoje), "Receita - CMV", "good" if lucro_hoje >= 0 else "bad")
    with h4:
        metric_card("Perdas Hoje", moeda(perdas_hoje), "Perda/consumo/ajuste", "warn" if perdas_hoje > 0 else "good")

    st.markdown("---")

    left, right = st.columns([2, 1])

    with left:
        st.markdown("### Evolução diária")

        if df_periodo.empty:
            st.info("Ainda não há movimentações no período selecionado.")
        else:
            diario = df_periodo.copy()
            diario["Dia"] = diario["Data"].dt.date

            diario_resumo = diario.groupby("Dia", as_index=False).agg(
                Receita=("Receita", "sum"),
                CMV=("CMV", "sum")
            )
            diario_resumo["CMV %"] = diario_resumo.apply(lambda r: (r["CMV"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)

            fig = px.area(
                diario_resumo,
                x="Dia",
                y=["Receita", "CMV"],
                template="plotly_white",
                color_discrete_map={
                    "Receita": "#2563eb",
                    "CMV": "#ef4444"
                }
            )

            fig.update_layout(
                height=420,
                hovermode="x unified",
                legend_title="",
                margin=dict(l=10, r=10, t=30, b=10),
                paper_bgcolor="white",
                plot_bgcolor="white",
                font=dict(
                    family="Segoe UI",
                    size=13,
                    color="#0f172a"
                )
            )

            fig.update_traces(
                line=dict(width=4),
            )

            st.plotly_chart(fig, use_container_width=True)

            st.caption("Evolução diária de Receita e CMV.")

            gauge_color = "#16a34a"

            if cmv_pct_periodo > meta_cmv_input:
                gauge_color = "#dc2626"
            elif cmv_pct_periodo > (meta_cmv_input * 0.9):
                gauge_color = "#f59e0b"

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=cmv_pct_periodo,
                number={'suffix': "%"},
                title={'text': "CMV Atual"},
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': gauge_color},
                    'steps': [
                        {'range': [0, meta_cmv_input * 0.9], 'color': "#dcfce7"},
                        {'range': [meta_cmv_input * 0.9, meta_cmv_input], 'color': "#fef3c7"},
                        {'range': [meta_cmv_input, 100], 'color': "#fee2e2"}
                    ],
                    'threshold': {
                        'line': {'color': "#111827", 'width': 4},
                        'thickness': 0.75,
                        'value': meta_cmv_input
                    }
                }
            ))

            fig_gauge.update_layout(
                height=320,
                margin=dict(l=20, r=20, t=60, b=20),
                paper_bgcolor="white",
                font=dict(
                    family="Segoe UI",
                    size=14,
                    color="#0f172a"
                )
            )

            st.plotly_chart(fig_gauge, use_container_width=True)

            st.markdown("### Top produtos por resultado")

            vendas = df_periodo[df_periodo["TipoSaida"] == "Venda"].copy()

            if vendas.empty:
                st.info("Ainda não há vendas no período.")
            else:
                prod = vendas.groupby("Produto", as_index=False).agg(
                    Receita=("Receita", "sum"),
                    CMV=("CMV", "sum"),
                    Quantidade=("Quantidade", "sum")
                )

                prod["Lucro Bruto"] = prod["Receita"] - prod["CMV"]
                prod["CMV %"] = prod.apply(
                    lambda r: (r["CMV"] / r["Receita"] * 100)
                    if r["Receita"] else 0,
                    axis=1
                )

                col_a, col_b = st.columns(2)

                with col_a:

                    st.markdown("#### 🏆 Mais vendidos")

                    top_vendidos = prod.sort_values(
                        "Quantidade",
                        ascending=False
                    ).head(10)
                    top_vendidos["Quantidade Label"] = top_vendidos["Quantidade"].apply(lambda x: f"{float(x):,.0f}".replace(",", "."))

                    fig_vendidos = px.bar(
                        top_vendidos,
                        x="Quantidade",
                        y="Produto",
                        orientation="h",
                        text="Quantidade Label",
                        color="Quantidade",
                        color_continuous_scale=["#dbeafe", "#60a5fa", "#2563eb", "#1e3a8a"]
                    )

                    fig_vendidos.update_layout(
                        height=420,
                        yaxis={'categoryorder':'total ascending'},
                        paper_bgcolor="white",
                        plot_bgcolor="white",
                        margin=dict(l=10, r=10, t=30, b=10),
                        coloraxis_showscale=False
                    )

                    st.plotly_chart(
                        fig_vendidos,
                        use_container_width=True
                    )

                with col_b:

                    st.markdown("#### 💎 Mais lucrativos")

                    top_lucro = prod.sort_values(
                        "Lucro Bruto",
                        ascending=False
                    ).head(10)
                    top_lucro["Lucro Label"] = top_lucro["Lucro Bruto"].apply(moeda)

                    fig_lucro = px.bar(
                        top_lucro,
                        x="Lucro Bruto",
                        y="Produto",
                        orientation="h",
                        text="Lucro Label",
                        color="Lucro Bruto",
                        color_continuous_scale=["#dcfce7", "#4ade80", "#16a34a", "#14532d"]
                    )

                    fig_lucro.update_layout(
                        height=420,
                        yaxis={'categoryorder':'total ascending'},
                        paper_bgcolor="white",
                        plot_bgcolor="white",
                        margin=dict(l=10, r=10, t=30, b=10),
                        coloraxis_showscale=False
                    )

                    st.plotly_chart(
                        fig_lucro,
                        use_container_width=True
                    )

    with right:
        st.markdown("### Alertas inteligentes")

        if receita_periodo == 0:
            alerta_box("Sem vendas lançadas no período. O CMV ainda não pode ser analisado.", "info")
        elif cmv_pct_periodo <= meta_cmv_input:
            alerta_box(f"CMV dentro da meta: {format_pct(cmv_pct_periodo)}.", "good")
        elif cmv_pct_periodo <= alerta_cmv:
            alerta_box(f"CMV em atenção: {format_pct(cmv_pct_periodo)}. Meta: {format_pct(meta_cmv_input)}.", "warn")
        else:
            alerta_box(f"CMV crítico: {format_pct(cmv_pct_periodo)}. Meta: {format_pct(meta_cmv_input)}.", "bad")

        if perdas_periodo > 0 and receita_periodo > 0:
            perda_pct = perdas_periodo / receita_periodo * 100
            tipo = "bad" if perda_pct > 5 else "warn"
            alerta_box(f"Perdas/saídas internas equivalem a {format_pct(perda_pct)} da receita.", tipo)

        if estoque_baixo_qtd:
            alerta_box(f"{estoque_baixo_qtd} produto(s) abaixo ou no estoque mínimo.", "warn")
        else:
            alerta_box("Nenhum produto abaixo do estoque mínimo.", "good")

        if not df_periodo.empty:
            perdas_df = df_periodo[df_periodo["TipoSaida"] != "Venda"]
            if not perdas_df.empty:
                pior_perda = perdas_df.groupby("Produto", as_index=False)["CMV"].sum().sort_values("CMV", ascending=False).head(1)
                if not pior_perda.empty:
                    alerta_box(f"Maior perda/custo interno: {pior_perda.iloc[0]['Produto']} ({moeda(pior_perda.iloc[0]['CMV'])}).", "warn")

        st.markdown("### Estoque crítico")
        critico = est[est["Alerta"] == "⚠️ Baixo"].copy()
        if critico.empty:
            st.success("Estoque crítico vazio.")
        else:
            st.dataframe(critico[["Produto", "Qtd Atual", "Estoque Mínimo", "Valor Estoque"]], use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### Base gerencial do período")

    if df_periodo.empty:
        st.info("Sem base gerencial para o período.")
    else:
        base = df_periodo.groupby(["Produto", "Categoria", "TipoSaida"], as_index=False).agg(
            Quantidade=("Quantidade", "sum"),
            Receita=("Receita", "sum"),
            CMV=("CMV", "sum")
        )
        base["CMV %"] = base.apply(lambda r: (r["CMV"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)
        base["Lucro Bruto"] = base["Receita"] - base["CMV"]
        base["Margem %"] = base.apply(lambda r: (r["Lucro Bruto"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)
        st.dataframe(
    base.style
    .format({
        "Receita": "R$ {:,.2f}",
        "CMV": "R$ {:,.2f}",
        "Lucro Bruto": "R$ {:,.2f}",
        "CMV %": "{:.2f}%",
        "Margem %": "{:.2f}%"
    })
    .background_gradient(subset=["Lucro Bruto"], cmap="Greens")
    .background_gradient(subset=["CMV %"], cmap="Reds")
    .background_gradient(subset=["Margem %"], cmap="Greens"),
    use_container_width=True,
    hide_index=True
)



# =========================================================
# EXECUTIVO MOBILE V2
# =========================================================
elif menu == "📱 Executivo Mobile":
    st.markdown("""
        <style>
            .block-container {
    padding-top: 0.8rem;
    padding-bottom: 1rem;
    padding-left: 2rem;
    padding-right: 2rem;
    max-width: 100%;
}
            [data-testid="stSidebar"] {min-width: 250px;}
            .exec-hero {
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 52%, #334155 100%);
                color: white;
                padding: 22px 20px;
                border-radius: 26px;
                margin-bottom: 15px;
                box-shadow: 0 14px 34px rgba(15,23,42,.20);
            }
            .exec-title {font-size: 28px; line-height:1.05; font-weight: 950; margin-bottom:6px;}
            .exec-sub {font-size: 13px; color:#cbd5e1; font-weight:600;}
            .exec-pill {display:inline-block; background:rgba(255,255,255,.13); color:white; border:1px solid rgba(255,255,255,.18); border-radius:99px; padding:6px 10px; margin-top:13px; font-size:12px; font-weight:800;}
            .kpi-card {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 22px;
                padding: 17px 16px;
                margin-bottom: 10px;
                box-shadow: 0 8px 26px rgba(15, 23, 42, 0.075);
                min-height: 112px;
            }
            .kpi-label {font-size: 12px; color:#64748b; font-weight:800; margin-bottom:7px; text-transform:uppercase; letter-spacing:.02em;}
            .kpi-value {font-size: 26px; color:#0f172a; font-weight:950; line-height:1.05;}
            .kpi-help {font-size: 12px; color:#64748b; margin-top:7px; font-weight:600;}
            .tone-blue {border-left: 6px solid #2563eb;}
            .tone-red {border-left: 6px solid #ef4444;}
            .tone-green {border-left: 6px solid #22c55e;}
            .tone-orange {border-left: 6px solid #f97316;}
            .tone-purple {border-left: 6px solid #7c3aed;}
            .section-title {font-size:19px; font-weight:950; color:#0f172a; margin:24px 0 10px 0;}
            .alert-card {border-radius:18px; padding:14px 15px; margin-bottom:10px; font-size:14px; font-weight:800; box-shadow: 0 6px 16px rgba(15,23,42,.05);}
            .alert-good {background:#f0fdf4; border-left:6px solid #22c55e; color:#166534;}
            .alert-warn {background:#fffbeb; border-left:6px solid #f59e0b; color:#92400e;}
            .alert-bad {background:#fef2f2; border-left:6px solid #ef4444; color:#991b1b;}
            .insight-card {background:#ffffff; border:1px solid #e5e7eb; border-radius:20px; padding:15px; margin-bottom:10px; box-shadow: 0 6px 18px rgba(15,23,42,.06);}
            .insight-title {font-size:14px; font-weight:900; color:#0f172a; margin-bottom:4px;}
            .insight-text {font-size:13px; color:#475569; font-weight:600;}
            .score-card {
                background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
                border: 1px solid #e5e7eb;
                border-radius: 26px;
                padding: 20px 18px;
                margin: 14px 0 16px 0;
                box-shadow: 0 12px 32px rgba(15,23,42,.10);
            }
            .score-number {font-size:44px; font-weight:950; line-height:1; color:#0f172a;}
            .score-label {font-size:15px; font-weight:950; color:#0f172a; margin-top:6px;}
            .score-sub {font-size:12px; color:#64748b; font-weight:700; margin-top:5px;}
            .score-bar-bg {height:12px; background:#e5e7eb; border-radius:99px; overflow:hidden; margin-top:14px;}
            .score-bar-fill {height:12px; border-radius:99px;}
            .score-reason {font-size:12px; color:#475569; font-weight:700; margin-top:8px;}
            .forecast-card {background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%); color:white; border-radius:26px; padding:18px; margin:14px 0 16px 0; box-shadow:0 12px 32px rgba(15,23,42,.16);}
            .forecast-title {font-size:18px; font-weight:950; margin-bottom:6px;}
            .forecast-sub {font-size:12px; color:#cbd5e1; font-weight:700; margin-bottom:14px;}
            .forecast-grid {display:grid; grid-template-columns:1fr 1fr; gap:10px;}
            .forecast-kpi {background:rgba(255,255,255,.09); border:1px solid rgba(255,255,255,.15); border-radius:18px; padding:12px;}
            .forecast-label {font-size:11px; color:#cbd5e1; font-weight:800; text-transform:uppercase;}
            .forecast-value {font-size:22px; font-weight:950; margin-top:4px;}
            .forecast-action {background:#fff7ed; border-left:5px solid #f97316; color:#9a3412; padding:10px 12px; border-radius:14px; margin-top:10px; font-size:13px; font-weight:800;}
            @media (max-width: 720px) {
                .block-container {padding-left: .55rem; padding-right: .55rem;}
                .exec-title {font-size:24px;}
                .kpi-value {font-size:24px;}
            }
        </style>
    """, unsafe_allow_html=True)

    hoje = date.today()
    nome_empresa = get_config("nome_empresa", "Restaurante")
    meta_cmv = get_float_config("meta_cmv_ideal", META_CMV)
    alerta_cmv = get_float_config("meta_cmv_alerta", meta_cmv + 4)
    critica_cmv = get_float_config("meta_cmv_critica", meta_cmv + 8)

    periodo_mobile = st.selectbox(
        "Período para análise",
        ["Hoje", "Últimos 7 dias", "Últimos 30 dias", "Este mês", "Personalizado"],
        index=3,
        key="mobile_periodo_v2"
    )

    data_ini_mob = hoje.replace(day=1)
    data_fim_mob = hoje
    if periodo_mobile == "Personalizado":
        c_ini, c_fim = st.columns(2)
        data_ini_mob = c_ini.date_input("Data inicial", value=data_ini_mob, key="mob_ini_v2")
        data_fim_mob = c_fim.date_input("Data final", value=data_fim_mob, key="mob_fim_v2")

    inicio_periodo, fim_periodo = datas_periodo(periodo_mobile, data_ini_mob, data_fim_mob)
    label_periodo = periodo_label(inicio_periodo, fim_periodo)

    inicio_hoje = str(hoje)
    fim_amanha = str(pd.Timestamp(hoje) + pd.Timedelta(days=1))[:10]

    df_periodo = resumo_periodo(inicio_periodo, fim_periodo)
    df_hoje = resumo_periodo(inicio_hoje, fim_amanha)
    est = estoque_df()
    dre = dre_periodo(inicio_periodo, fim_periodo)
    lucro_liquido = dre["lucro_operacional"]

    margem_operacional = (
    (lucro_liquido / dre["receita"]) * 100
    if dre["receita"] else 0
    )
    despesas_operacionais = dre["perdas"] + dre["despesas"]

    lucro_liquido = dre["lucro_bruto"] - despesas_operacionais

    margem_operacional = (
    (lucro_liquido / dre["receita"]) * 100
    if dre["receita"] else 0
    )

    receita_periodo = df_periodo.loc[df_periodo["TipoSaida"] == "Venda", "Receita"].sum() if not df_periodo.empty else 0
    cmv_periodo = df_periodo["CMV"].sum() if not df_periodo.empty else 0
    perdas_periodo = df_periodo.loc[df_periodo["TipoSaida"] != "Venda", "CMV"].sum() if not df_periodo.empty else 0
    lucro_periodo = receita_periodo - cmv_periodo
    cmv_pct_periodo = (cmv_periodo / receita_periodo * 100) if receita_periodo else 0
    margem_periodo = (lucro_periodo / receita_periodo * 100) if receita_periodo else 0

    receita_hoje = df_hoje.loc[df_hoje["TipoSaida"] == "Venda", "Receita"].sum() if not df_hoje.empty else 0
    cmv_hoje = df_hoje["CMV"].sum() if not df_hoje.empty else 0
    perdas_hoje = df_hoje.loc[df_hoje["TipoSaida"] != "Venda", "CMV"].sum() if not df_hoje.empty else 0
    lucro_hoje = receita_hoje - cmv_hoje
    cmv_pct_hoje = (cmv_hoje / receita_hoje * 100) if receita_hoje else 0

    vendas_periodo = df_periodo[df_periodo["TipoSaida"] == "Venda"].copy() if not df_periodo.empty else pd.DataFrame()
    qtd_vendas = vendas_periodo["Quantidade"].sum() if not vendas_periodo.empty else 0
    ticket_medio = receita_periodo / qtd_vendas if qtd_vendas else 0

    estoque_valor = est["Valor Estoque"].sum() if not est.empty else 0
    estoque_baixo = est[est["Alerta"] == "⚠️ Baixo"].copy() if not est.empty else pd.DataFrame()

    status_texto = "Saudável"
    status_tom = "🟢"
    if receita_periodo <= 0:
        status_texto = "Sem vendas"
        status_tom = "🟡"
    elif cmv_pct_periodo >= critica_cmv or dre["lucro_operacional"] < 0:
        status_texto = "Crítico"
        status_tom = "🔴"
    elif cmv_pct_periodo > meta_cmv or len(estoque_baixo) > 0 or perdas_periodo > 0:
        status_texto = "Atenção"
        status_tom = "🟡"

    # Score executivo da loja: transforma a operação em uma nota simples para o dono.
    score_loja = 100
    motivos_score = []

    if receita_periodo <= 0:
        score_loja -= 25
        motivos_score.append("sem vendas registradas no período")
    else:
        excesso_cmv = max(0, cmv_pct_periodo - meta_cmv)
        if excesso_cmv > 0:
            perda_score_cmv = min(30, int(excesso_cmv * 2))
            score_loja -= perda_score_cmv
            motivos_score.append(f"CMV {format_pct(cmv_pct_periodo)} acima da meta")

    if dre["lucro_operacional"] < 0:
        score_loja -= 20
        motivos_score.append("DRE operacional negativo")

    if receita_periodo > 0 and perdas_periodo > 0:
        perda_pct_score = perdas_periodo / receita_periodo * 100
        penalidade_perda = min(15, int(perda_pct_score * 2))
        score_loja -= penalidade_perda
        motivos_score.append(f"perdas representam {format_pct(perda_pct_score)} da receita")

    if len(estoque_baixo) > 0:
        penalidade_estoque = min(15, len(estoque_baixo) * 3)
        score_loja -= penalidade_estoque
        motivos_score.append(f"{len(estoque_baixo)} produto(s) em estoque crítico")

    if ticket_medio <= 0 and receita_periodo > 0:
        score_loja -= 5
        motivos_score.append("ticket médio sem leitura adequada")

    score_loja = max(0, min(100, int(score_loja)))

    if score_loja >= 90:
        score_status = "Excelente"
        score_emoji = "🟢"
        score_cor = "#22c55e"
    elif score_loja >= 75:
        score_status = "Saudável"
        score_emoji = "🟢"
        score_cor = "#16a34a"
    elif score_loja >= 55:
        score_status = "Atenção"
        score_emoji = "🟡"
        score_cor = "#f59e0b"
    else:
        score_status = "Crítica"
        score_emoji = "🔴"
        score_cor = "#ef4444"

    motivos_score_txt = " • ".join(motivos_score[:3]) if motivos_score else "operação dentro dos principais parâmetros acompanhados"

    st.markdown(f"""
        <div class="exec-hero">
            <div class="exec-title">{status_tom} Painel do Dono</div>
            <div class="exec-sub">{nome_empresa} • mapa da operação para decidir rápido, sem depender de relatório do gerente.</div>
            <div class="exec-pill">Status: {status_texto} • {label_periodo}</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
        <div class="score-card">
            <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
                <div>
                    <div class="score-number">{score_loja}<span style="font-size:18px; color:#64748b;">/100</span></div>
                    <div class="score-label">{score_emoji} Saúde da loja: {score_status}</div>
                    <div class="score-sub">Nota automática baseada em CMV, margem, perdas, estoque crítico e resultado.</div>
                </div>
                <div style="font-size:12px; font-weight:900; color:{score_cor}; background:rgba(15,23,42,.04); padding:7px 10px; border-radius:999px; white-space:nowrap;">{score_status}</div>
            </div>
            <div class="score-bar-bg"><div class="score-bar-fill" style="width:{score_loja}%; background:{score_cor};"></div></div>
            <div class="score-reason">Principais leituras: {motivos_score_txt}.</div>
        </div>
    """, unsafe_allow_html=True)

    def kpi(label, value, help_text="", tone="blue"):
        st.markdown(f"""
            <div class="kpi-card tone-{tone}">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-help">{help_text}</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div class='section-title'>📌 Resumo executivo</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        kpi("Faturamento", moeda(receita_periodo), "Receita no período", "blue")
    with c2:
        tom_cmv = "green" if cmv_pct_periodo <= meta_cmv and receita_periodo > 0 else "red"
        kpi("CMV", format_pct(cmv_pct_periodo), f"Meta mensal: {format_pct(meta_cmv)}", tom_cmv)
    c3, c4 = st.columns(2)
    with c3:
        kpi("Lucro bruto", moeda(lucro_periodo), f"Margem: {format_pct(margem_periodo)}", "green" if lucro_periodo >= 0 else "red")
    with c4:
        kpi("Perdas", moeda(perdas_periodo), "Perda, consumo e ajuste", "orange" if perdas_periodo > 0 else "green")
    c5, c6 = st.columns(2)
    with c5:
        kpi("Ticket médio", moeda(ticket_medio), "Receita ÷ quantidade vendida", "purple")
    with c6:
       metric_card(
        "Lucro Líquido",
        moeda(lucro_liquido),
        format_pct(margem_operacional),
        "good" if lucro_liquido > 0 else "bad"
    )
    st.markdown("<div class='section-title'>⏱ Hoje</div>", unsafe_allow_html=True)
    h1, h2 = st.columns(2)
    with h1:
        kpi("Venda hoje", moeda(receita_hoje), "Faturamento do dia", "blue")
    with h2:
        kpi("CMV hoje", format_pct(cmv_pct_hoje), moeda(cmv_hoje), "green" if cmv_pct_hoje <= meta_cmv and receita_hoje > 0 else "red")
    h3, h4 = st.columns(2)
    with h3:
        kpi("Lucro hoje", moeda(lucro_hoje), "Receita - CMV", "green" if lucro_hoje >= 0 else "red")
    with h4:
        kpi("Perdas hoje", moeda(perdas_hoje), "Impacto operacional", "orange" if perdas_hoje > 0 else "green")

    st.markdown("<div class='section-title'>🚨 Central inteligente de alertas</div>", unsafe_allow_html=True)

    # Motor simples de alertas executivos: transforma número em decisão.
    alertas_exec = []
    acoes_exec = []

    def add_alerta(nivel, titulo, texto):
        # nivel: bad, warn, good
        icone = {"bad": "🔴", "warn": "🟡", "good": "🟢"}.get(nivel, "🟡")
        classe = {"bad": "alert-bad", "warn": "alert-warn", "good": "alert-good"}.get(nivel, "alert-warn")
        alertas_exec.append((classe, f"{icone} {titulo}: {texto}"))

    def add_acao(titulo, texto):
        acoes_exec.append((titulo, texto))

    # Ranking de produtos para inteligência
    prod_mobile = pd.DataFrame()
    if not vendas_periodo.empty:
        prod_mobile = vendas_periodo.groupby("Produto", as_index=False).agg(
            Receita=("Receita", "sum"),
            CMV=("CMV", "sum"),
            Quantidade=("Quantidade", "sum")
        )
        prod_mobile["Lucro Bruto"] = prod_mobile["Receita"] - prod_mobile["CMV"]
        prod_mobile["CMV %"] = prod_mobile.apply(lambda r: (r["CMV"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)
        prod_mobile["Margem %"] = prod_mobile.apply(lambda r: (r["Lucro Bruto"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)

    # 0) Score geral
    if score_loja < 55:
        add_alerta("bad", "Saúde da loja crítica", f"score {score_loja}/100. Prioridade: corrigir CMV, perdas e resultado antes de pensar em crescimento.")
        add_acao("Plano de choque da loja", "Comece pelo maior vilão: CMV, perdas ou DRE negativo. O score mostra que a operação precisa de ação imediata.")
    elif score_loja < 75:
        add_alerta("warn", "Saúde da loja em atenção", f"score {score_loja}/100. A loja ainda opera, mas existem pontos que podem virar prejuízo.")
    else:
        add_alerta("good", "Saúde da loja positiva", f"score {score_loja}/100. Mantenha a rotina de acompanhamento e ataque pequenas oportunidades.")

    # 1) CMV
    if receita_periodo <= 0:
        add_alerta("warn", "Sem leitura de vendas", "lance vendas para liberar análise real de CMV, margem e produtos.")
        add_acao("Começar pela base", "Registre as vendas do dia para o painel conseguir apontar margem, CMV e produtos críticos.")
    elif cmv_pct_periodo >= critica_cmv:
        diferenca = cmv_pct_periodo - meta_cmv
        add_alerta("bad", "CMV crítico", f"{format_pct(cmv_pct_periodo)} está {format_pct(diferenca)} acima da meta mensal de {format_pct(meta_cmv)}.")
        add_acao("Reunião rápida com gerente", "Pergunte hoje: quais produtos tiveram perda, quais compras encareceram e quais vendas estão com preço defasado.")
    elif cmv_pct_periodo > meta_cmv:
        diferenca = cmv_pct_periodo - meta_cmv
        add_alerta("warn", "CMV acima da meta", f"{format_pct(cmv_pct_periodo)} está {format_pct(diferenca)} acima da meta mensal.")
        add_acao("Atacar os vilões do CMV", "Abra a aba 'CMV alto' e revise os produtos que estão puxando o percentual para cima.")
    else:
        add_alerta("good", "CMV saudável", f"{format_pct(cmv_pct_periodo)} dentro da meta de {format_pct(meta_cmv)}.")

    # 2) Perdas
    if receita_periodo > 0 and perdas_periodo > 0:
        perda_pct = perdas_periodo / receita_periodo * 100
        if perda_pct > 5:
            add_alerta("bad", "Perdas altas", f"perdas/consumo/ajustes equivalem a {format_pct(perda_pct)} da receita.")
            add_acao("Cortar desperdício", "Filtre movimentações por perda, consumo interno e ajuste. Cobre motivo e responsável por cada lançamento.")
        else:
            add_alerta("warn", "Perdas em atenção", f"impacto de {format_pct(perda_pct)} da receita no período.")
            add_acao("Monitorar perdas", "Acompanhe diariamente se o valor de perdas continua subindo ou foi um evento pontual.")

    # 3) Estoque crítico
    if len(estoque_baixo) > 0:
        top_critico = estoque_baixo.sort_values("Qtd Atual").head(1)
        nome_critico = top_critico.iloc[0]["Produto"] if not top_critico.empty else "produto crítico"
        add_alerta("warn", "Risco de ruptura", f"{len(estoque_baixo)} produto(s) em estoque crítico. Primeiro item: {nome_critico}.")
        add_acao("Comprar antes de perder venda", "Priorize os itens críticos com maior saída e maior margem.")
    else:
        add_alerta("good", "Estoque sem ruptura", "nenhum produto abaixo do estoque mínimo.")

    # 4) DRE
    if dre["receita"] > 0 and dre["lucro_operacional"] < 0:
        add_alerta("bad", "Prejuízo operacional", "o DRE do período está negativo depois de CMV e despesas.")
        add_acao("Revisar resultado", "Separe o problema entre preço, CMV e despesas. Se o lucro bruto existe mas some no final, olhe despesas.")
    elif dre["receita"] > 0 and dre["lucro_operacional"] > 0:
        margem_op = dre["lucro_operacional"] / dre["receita"] * 100
        add_alerta("good", "Resultado operacional", f"lucro operacional positivo com margem de {format_pct(margem_op)}.")

    # 5) Produto campeão com margem ruim
    if not prod_mobile.empty:
        vendidos = prod_mobile.sort_values("Quantidade", ascending=False).head(5)
        ruins = vendidos[vendidos["CMV %"] > meta_cmv]
        if not ruins.empty:
            p_ruim = ruins.sort_values("CMV %", ascending=False).iloc[0]
            add_alerta("bad", "Produto campeão com margem ruim", f"{p_ruim['Produto']} vende bem, mas está com CMV de {format_pct(p_ruim['CMV %'])}.")
            add_acao("Reprecificar campeão", f"Revise preço, ficha técnica ou fornecedor de {p_ruim['Produto']}. Produto que vende muito com margem ruim destrói lucro.")

        bons = prod_mobile[(prod_mobile["CMV %"] <= meta_cmv) & (prod_mobile["Lucro Bruto"] > 0)]
        if not bons.empty:
            p_bom = bons.sort_values("Lucro Bruto", ascending=False).iloc[0]
            add_acao("Promover produto saudável", f"{p_bom['Produto']} tem boa margem e lucro. Pode entrar em combo, destaque de vitrine ou sugestão ativa.")

    for classe, texto in alertas_exec[:7]:
        st.markdown(f"<div class='alert-card {classe}'>{texto}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🧠 O que fazer hoje</div>", unsafe_allow_html=True)
    if not acoes_exec:
        acoes_exec.append(("Manter rotina", "Acompanhe CMV, perdas e estoque crítico diariamente. A operação está sem alerta grave no período."))

    for titulo, texto in acoes_exec[:5]:
        st.markdown(f"""
            <div class="insight-card">
                <div class="insight-title">{titulo}</div>
                <div class="insight-text">{texto}</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🤖 Motor automático de inteligência</div>", unsafe_allow_html=True)
    inteligencia_mobile = gerar_alertas_inteligentes_erp(inicio_periodo, fim_periodo)
    for alerta in inteligencia_mobile["alertas"][:6]:
        nivel = alerta.get("nivel", "atenção")
        if nivel == "crítico":
            classe = "alert-bad"
            ic = "🔴"
        elif nivel == "ok":
            classe = "alert-good"
            ic = "🟢"
        elif nivel == "oportunidade":
            classe = "alert-warn"
            ic = "💡"
        elif nivel == "projeção":
            classe = "alert-warn"
            ic = "📈"
        else:
            classe = "alert-warn"
            ic = "🟡"
        st.markdown(
            f"<div class='alert-card {classe}'>{ic} <b>{alerta.get('titulo','Alerta')}</b>: {alerta.get('texto','')}</div>",
            unsafe_allow_html=True
        )

    st.markdown("<div class='section-title'>🔮 Projeção inteligente do mês</div>", unsafe_allow_html=True)
    proj = projecao_financeira_mes()
    cor_tendencia = "#22c55e" if proj["nivel"] == "ok" else ("#ef4444" if proj["nivel"] == "crítico" else "#f59e0b")
    st.markdown(f"""
        <div class="forecast-card">
            <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
                <div>
                    <div class="forecast-title">🔮 Como o mês deve fechar</div>
                    <div class="forecast-sub">Projeção baseada no ritmo realizado até o dia {proj['dia_atual']} de {proj['dias_no_mes']}.</div>
                </div>
                <div style="background:{cor_tendencia}; color:white; font-size:12px; font-weight:950; border-radius:999px; padding:7px 10px; white-space:nowrap;">{proj['tendencia']}</div>
            </div>
            <div class="forecast-grid">
                <div class="forecast-kpi"><div class="forecast-label">Receita projetada</div><div class="forecast-value">{moeda(proj['receita_proj'])}</div></div>
                <div class="forecast-kpi"><div class="forecast-label">Lucro previsto</div><div class="forecast-value">{moeda(proj['lucro_operacional_proj'])}</div></div>
                <div class="forecast-kpi"><div class="forecast-label">CMV projetado</div><div class="forecast-value">{format_pct(proj['cmv_pct_proj'])}</div></div>
                <div class="forecast-kpi"><div class="forecast-label">Margem operacional</div><div class="forecast-value">{format_pct(proj['margem_op_proj'])}</div></div>
            </div>
            <div style="font-size:13px; color:#e2e8f0; font-weight:800; margin-top:12px;">{proj['resumo']}</div>
        </div>
    """, unsafe_allow_html=True)

    for rec in proj["recomendacoes"][:3]:
        st.markdown(f"<div class='forecast-action'>➡️ {rec}</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🤖 Consultor IA do Restaurante</div>", unsafe_allow_html=True)
    st.caption("Pergunte qualquer coisa sobre CMV, DRE, PEPS, margem, estoque, perdas, produtos, lucro, projeção ou indicadores do sistema.")

    # =====================================================
    # IA CONSULTORA ROBUSTA — pergunta livre + base do ERP
    # =====================================================
    perguntas_rapidas = [
        "O que devo fazer hoje?",
        "O que é CMV?",
        "Como calcula o CMV?",
        "O que é DRE?",
        "Por que meu lucro caiu?",
        "Qual produto é mais lucrativo?",
        "Qual produto vende mais?",
        "Qual produto devo promover?",
        "Quais produtos estão com margem ruim?",
        "Como o mês deve fechar?",
        "Onde estou perdendo dinheiro?",
        "O que é PEPS?",
        "O que é Curva ABC?",
    ]

    def montar_contexto_consultor_ia():
        produtos_contexto = []
        if not prod_mobile.empty:
            base_prod = prod_mobile.copy().sort_values(["Lucro Bruto", "Receita"], ascending=[False, False]).head(15)
            for _, r in base_prod.iterrows():
                produtos_contexto.append({
                    "produto": str(r.get("Produto", "")),
                    "receita": round(float(r.get("Receita", 0) or 0), 2),
                    "cmv": round(float(r.get("CMV", 0) or 0), 2),
                    "cmv_pct": round(float(r.get("CMV %", 0) or 0), 2),
                    "lucro_bruto": round(float(r.get("Lucro Bruto", 0) or 0), 2),
                    "margem_pct": round(float(r.get("Margem %", 0) or 0), 2),
                    "quantidade": round(float(r.get("Quantidade", 0) or 0), 2),
                })

        estoque_contexto = []
        if not estoque_baixo.empty:
            for _, r in estoque_baixo.head(12).iterrows():
                estoque_contexto.append({
                    "produto": str(r.get("Produto", "")),
                    "qtd_atual": round(float(r.get("Qtd Atual", 0) or 0), 2),
                    "estoque_minimo": round(float(r.get("Estoque Mínimo", 0) or 0), 2),
                })

        contexto = {
            "empresa": nome_empresa,
            "periodo": label_periodo,
            "meta_cmv_pct": round(float(meta_cmv), 2),
            "receita_periodo": round(float(receita_periodo), 2),
            "cmv_periodo": round(float(cmv_periodo), 2),
            "cmv_pct_periodo": round(float(cmv_pct_periodo), 2),
            "lucro_bruto": round(float(lucro_periodo), 2),
            "perdas": round(float(perdas_periodo), 2),
            "ticket_medio": round(float(ticket_medio), 2),
            "estoque_valor": round(float(estoque_valor), 2),
            "estoque_critico_qtd": int(len(estoque_baixo)),
            "dre": {
                "receita": round(float(dre.get("receita", 0) or 0), 2),
                "cmv_total": round(float(dre.get("cmv_total", 0) or 0), 2),
                "lucro_bruto": round(float(dre.get("lucro_bruto", 0) or 0), 2),
                "despesas": round(float(dre.get("despesas", 0) or 0), 2),
                "lucro_operacional": round(float(dre.get("lucro_operacional", 0) or 0), 2),
                "margem_operacional_pct": round(float(dre.get("margem_operacional_pct", 0) or 0), 2),
            },
            "projecao_mes": {
                "receita_projetada": round(float(proj.get("receita_proj", 0) or 0), 2),
                "lucro_operacional_projetado": round(float(proj.get("lucro_operacional_proj", 0) or 0), 2),
                "cmv_pct_projetado": round(float(proj.get("cmv_pct_proj", 0) or 0), 2),
                "margem_operacional_projetada": round(float(proj.get("margem_op_proj", 0) or 0), 2),
                "tendencia": str(proj.get("tendencia", "")),
            },
            "produtos": produtos_contexto,
            "estoque_critico": estoque_contexto,
        }
        return json.dumps(contexto, ensure_ascii=False, indent=2)

    def resposta_base_conhecimento(pergunta):
        p = str(pergunta or "").lower()

        if "dre" in p:
            return (
                "**O que é DRE?**\n\n"
                "DRE é a Demonstração do Resultado Gerencial. No seu ERP, ela mostra se o restaurante está dando lucro ou prejuízo no período.\n\n"
                "**Como ler no sistema:**\n"
                f"• Receita: {moeda(dre.get('receita', 0))}\n"
                f"• CMV total: {moeda(dre.get('cmv_total', 0))}\n"
                f"• Lucro bruto: {moeda(dre.get('lucro_bruto', 0))}\n"
                f"• Despesas: {moeda(dre.get('despesas', 0))}\n"
                f"• Lucro operacional: {moeda(dre.get('lucro_operacional', 0))}\n\n"
                "**Fórmula simples:** Receita - CMV - Despesas = Lucro Operacional.\n\n"
                "**Leitura prática:** se o lucro bruto é bom, mas o lucro operacional fica negativo, o problema provavelmente está nas despesas. Se o lucro bruto já é baixo, olhe CMV, preço e custo dos produtos."
            )

        if "cmv" in p:
            return (
                "**O que é CMV?**\n\n"
                "CMV é o Custo da Mercadoria Vendida. Ele mostra quanto o restaurante gastou em produto/insumo para gerar as vendas.\n\n"
                "**Como o sistema calcula:**\n"
                "CMV % = custo das saídas pelo PEPS ÷ receita de venda × 100.\n\n"
                f"**No seu período atual:**\n• CMV: {format_pct(cmv_pct_periodo)}\n• Meta: {format_pct(meta_cmv)}\n• Receita: {moeda(receita_periodo)}\n• CMV em R$: {moeda(cmv_periodo)}\n\n"
                "**Leitura prática:** se o CMV passa da meta, pode indicar compra cara, preço defasado, desperdício, consumo interno, erro de ficha técnica ou perda operacional."
            )

        if "peps" in p:
            return (
                "**O que é PEPS?**\n\n"
                "PEPS significa Primeiro que Entra, Primeiro que Sai. O sistema baixa primeiro os lotes mais antigos do estoque.\n\n"
                "**Por que isso importa?**\n"
                "Ajuda a calcular o custo real da venda e reduz risco de produto parado ou vencendo. Em restaurante, isso é importante para controlar CMV e validade."
            )

        if "curva abc" in p or "abc" in p:
            return (
                "**O que é Curva ABC?**\n\n"
                "A Curva ABC separa os produtos por importância no resultado. Produtos A são os mais relevantes, produtos B têm impacto médio e produtos C têm menor impacto.\n\n"
                "**Leitura prática:** o dono deve acompanhar de perto os produtos A, porque pequenas mudanças em preço, custo, estoque ou perda nesses itens mexem muito no lucro."
            )

        if "margem" in p:
            return (
                "**O que é margem?**\n\n"
                "Margem é o percentual que sobra depois de descontar o custo do produto.\n\n"
                "**Fórmula simples:** Margem Bruta % = Lucro Bruto ÷ Receita × 100.\n\n"
                "**Leitura prática:** produto que vende muito, mas tem margem ruim, pode parecer bom no caixa e ruim no lucro."
            )

        if "ticket" in p:
            return (
                "**O que é ticket médio?**\n\n"
                "Ticket médio é quanto, em média, cada venda ou item vendido gera de receita.\n\n"
                f"No período atual, o ticket médio está em {moeda(ticket_medio)}.\n\n"
                "**Leitura prática:** aumentar ticket médio com combos e produtos de boa margem melhora o resultado sem depender apenas de mais clientes."
            )

        return None

    def resposta_dados_erp(pergunta):
        p = str(pergunta or "").lower()

        if not prod_mobile.empty and any(t in p for t in ["mais lucrativo", "maior lucro", "mais lucro", "produto lucrativo", "alimento lucrativo"]):
            ranking = prod_mobile.sort_values("Lucro Bruto", ascending=False).head(5).copy()
            melhor = ranking.iloc[0]
            lista = "\n".join([f"{i+1}. {r['Produto']} — lucro bruto {moeda(r['Lucro Bruto'])}, margem {format_pct(r['Margem %'])}" for i, r in ranking.reset_index(drop=True).iterrows()])
            return f"**Produto mais lucrativo:** {melhor['Produto']}\n\n{lista}\n\n**Ação:** dê destaque ao produto mais lucrativo, mas acompanhe estoque e capacidade de produção."

        if not prod_mobile.empty and any(t in p for t in ["mais vendido", "vende mais", "campeão de venda", "campeao de venda"]):
            ranking = prod_mobile.sort_values("Quantidade", ascending=False).head(5).copy()
            melhor = ranking.iloc[0]
            lista = "\n".join([f"{i+1}. {r['Produto']} — {r['Quantidade']:.0f} un., receita {moeda(r['Receita'])}, CMV {format_pct(r['CMV %'])}" for i, r in ranking.reset_index(drop=True).iterrows()])
            return f"**Produto mais vendido:** {melhor['Produto']}\n\n{lista}\n\n**Ação:** se o campeão de venda tiver CMV alto, revise preço, custo ou ficha técnica."

        if not prod_mobile.empty and any(t in p for t in ["pior margem", "margem ruim", "baixa margem", "menor margem"]):
            ranking = prod_mobile.sort_values("Margem %", ascending=True).head(5).copy()
            pior = ranking.iloc[0]
            lista = "\n".join([f"{i+1}. {r['Produto']} — margem {format_pct(r['Margem %'])}, CMV {format_pct(r['CMV %'])}" for i, r in ranking.reset_index(drop=True).iterrows()])
            return f"**Produto com pior margem:** {pior['Produto']}\n\n{lista}\n\n**Ação:** revise preço de venda, custo de compra, porção/ficha técnica ou retire de promoção."

        if len(estoque_baixo) > 0 and any(t in p for t in ["estoque", "comprar", "ruptura", "acabando", "repor"]):
            ranking = estoque_baixo.sort_values("Qtd Atual").head(5).copy()
            lista = "\n".join([f"{i+1}. {r['Produto']} — atual {r['Qtd Atual']} / mínimo {r['Estoque Mínimo']}" for i, r in ranking.reset_index(drop=True).iterrows()])
            return f"**Itens com estoque crítico:**\n{lista}\n\n**Ação:** compre primeiro os itens críticos que também vendem bem ou têm boa margem."

        if "preju" in p or "lucro caiu" in p or "resultado" in p or "perdendo dinheiro" in p:
            return (
                "**Leitura do resultado:**\n"
                f"• Receita: {moeda(receita_periodo)}\n"
                f"• CMV: {format_pct(cmv_pct_periodo)} contra meta de {format_pct(meta_cmv)}\n"
                f"• Lucro bruto: {moeda(lucro_periodo)}\n"
                f"• Lucro operacional: {moeda(dre.get('lucro_operacional', 0))}\n"
                f"• Perdas/consumo/ajustes: {moeda(perdas_periodo)}\n\n"
                "**Diagnóstico provável:** quando o lucro cai, normalmente é por CMV alto, despesa alta, preço defasado, perdas ou produto vendendo sem margem.\n\n"
                "**Ação:** ataque primeiro CMV alto, produtos com pior margem, perdas e despesas do período."
            )

        if "mês" in p or "mes" in p or "proje" in p or "fechar" in p:
            return (
                "**Projeção do mês:**\n"
                f"• Receita projetada: {moeda(proj.get('receita_proj', 0))}\n"
                f"• Lucro operacional projetado: {moeda(proj.get('lucro_operacional_proj', 0))}\n"
                f"• CMV projetado: {format_pct(proj.get('cmv_pct_proj', 0))}\n"
                f"• Margem operacional projetada: {format_pct(proj.get('margem_op_proj', 0))}\n"
                f"• Tendência: {proj.get('tendencia', '')}\n\n"
                "**Ação:** se a tendência estiver em atenção ou crítica, revise CMV, despesas e produtos de margem ruim antes do fechamento."
            )

        if "hoje" in p or "fazer" in p or "ação" in p or "acao" in p:
            return (
                "**Prioridades para hoje:**\n"
                "1. Revisar produtos com CMV acima da meta.\n"
                "2. Conferir produtos com estoque crítico.\n"
                "3. Verificar perdas, consumo interno e ajustes.\n"
                "4. Promover produtos com boa margem e baixa saída.\n"
                "5. Separar se o problema está em preço, custo, perda ou despesa."
            )

        return None

    def consultar_ia_real_openai(pergunta):
        api_key = get_config("openai_api_key", "").strip()
        modelo = get_config("openai_model", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        if not api_key:
            return None, "IA real não configurada. Configure a chave em Configurações → OpenAI API Key."

        contexto = montar_contexto_consultor_ia()
        prompt = f"""
Você é o Consultor IA de um ERP de restaurantes.
Responda em português do Brasil, de forma clara, objetiva e prática para o dono da loja.
Use os dados reais do ERP quando a pergunta envolver produtos, CMV, DRE, margem, estoque, perdas, lucro, projeção ou vendas.
Quando a pergunta for conceitual, explique de forma simples e conecte com o sistema.
Não invente números fora do contexto. Se faltar dado, diga o que falta.

DADOS DO ERP:
{contexto}

PERGUNTA DO DONO:
{pergunta}
"""
        try:
            resp = requests.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": modelo, "input": prompt, "temperature": 0.25, "max_output_tokens": 900},
                timeout=40,
            )
            if resp.status_code >= 400:
                return None, f"Erro IA {resp.status_code}: {resp.text[:500]}"
            data = resp.json()
            texto = data.get("output_text")
            if not texto:
                partes = []
                for item in data.get("output", []):
                    for c in item.get("content", []):
                        if c.get("type") in ("output_text", "text"):
                            partes.append(c.get("text", ""))
                texto = "\n".join([x for x in partes if x]).strip()
            return texto, None
        except Exception as e:
            return None, f"Erro ao consultar IA real: {e}"

    def responder_consultor(pergunta):
        pergunta = str(pergunta or "").strip()
        if not pergunta:
            return "Digite uma pergunta ou escolha uma pergunta rápida."

        # 1) Primeiro responde conceitos do próprio sistema imediatamente.
        resp = resposta_base_conhecimento(pergunta)
        if resp:
            return resp

        # 2) Depois responde perguntas objetivas usando os dados do ERP.
        resp = resposta_dados_erp(pergunta)
        if resp:
            return resp

        # 3) Se tiver API Key, usa IA real para qualquer pergunta livre.
        resp_real, erro = consultar_ia_real_openai(pergunta)
        if resp_real:
            return "**IA real:**\n\n" + resp_real

        # 4) Sem API Key, entrega uma resposta local útil e avisa claramente.
        return (
            "**Resposta local do consultor:**\n\n"
            f"Com base no painel atual, sua receita é {moeda(receita_periodo)}, o CMV está em {format_pct(cmv_pct_periodo)} e o lucro operacional está em {moeda(dre.get('lucro_operacional', 0))}.\n\n"
            "Para perguntas totalmente livres, configure a OpenAI API Key em Configurações. Enquanto isso, eu respondo conceitos e análises principais do ERP por inteligência local.\n\n"
            f"Detalhe técnico: {erro}"
        )

    # BLOCO ESTÁVEL DA IA
    # Corrige travamento visual do Streamlit/Edge após várias perguntas seguidas.
    # Em vez de atualizar HTML dinâmico com unsafe_allow_html, usamos componentes nativos
    # e forçamos um rerun limpo depois de cada resposta.
    if "ultima_resposta_ia" not in st.session_state:
        st.session_state["ultima_pergunta_ia"] = "O que devo fazer hoje?"
        st.session_state["ultima_resposta_ia"] = responder_consultor("O que devo fazer hoje?")

    col_pergunta_1, col_pergunta_2 = st.columns([1, 1])

    pergunta_modelo = col_pergunta_1.selectbox(
        "Perguntas rápidas",
        perguntas_rapidas,
        key="ia_pergunta_modelo_estavel_v11"
    )

    pergunta_livre = col_pergunta_2.text_input(
        "Ou escreva sua pergunta",
        placeholder="Ex: o que é DRE?",
        key="ia_pergunta_livre_estavel_v11"
    )

    usar_livre = bool(str(pergunta_livre or "").strip())
    pergunta_ia = str(pergunta_livre if usar_livre else pergunta_modelo).strip()

    if st.button("🤖 Gerar resposta da IA", key="btn_gerar_ia_estavel_v11"):
        with st.spinner("Analisando pergunta e dados do ERP..."):
            st.session_state["ultima_pergunta_ia"] = pergunta_ia
            st.session_state["ultima_resposta_ia"] = responder_consultor(pergunta_ia)
        st.rerun()

    pergunta_exibida = st.session_state.get("ultima_pergunta_ia", pergunta_ia)
    resposta_exibida = st.session_state.get("ultima_resposta_ia", "")

    with st.container(border=True):
        st.markdown(f"**Pergunta:** {pergunta_exibida}")
        st.markdown(resposta_exibida)

    st.markdown("<div class='section-title'>📈 Evolução do período</div>", unsafe_allow_html=True)
    if not df_periodo.empty:
        evol = df_periodo.copy()
        evol["Dia"] = pd.to_datetime(evol["Data"], errors="coerce").dt.date
        evol = evol.groupby("Dia", as_index=False).agg(Receita=("Receita", "sum"), CMV=("CMV", "sum"))
        evol["Lucro Bruto"] = evol["Receita"] - evol["CMV"]
        st.line_chart(evol.set_index("Dia")[["Receita", "CMV", "Lucro Bruto"]])
    else:
        st.info("Sem dados para gráfico no período.")

    st.markdown("<div class='section-title'>🏆 Produtos para decisão</div>", unsafe_allow_html=True)
    if vendas_periodo.empty:
        st.info("Sem vendas para ranquear produtos.")
    else:
        prod = vendas_periodo.groupby("Produto", as_index=False).agg(
            Receita=("Receita", "sum"),
            CMV=("CMV", "sum"),
            Quantidade=("Quantidade", "sum")
        )
        prod["Lucro Bruto"] = prod["Receita"] - prod["CMV"]
        prod["CMV %"] = prod.apply(lambda r: (r["CMV"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)
        prod["Margem %"] = prod.apply(lambda r: (r["Lucro Bruto"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)

        aba1, aba2, aba3, aba4, aba5 = st.tabs(["Mais vendidos", "Mais lucrativos", "Pior margem", "CMV alto", "Promoção"])
        cols_prod = ["Produto", "Quantidade", "Receita", "CMV", "CMV %", "Lucro Bruto", "Margem %"]
        with aba1:
            st.dataframe(prod.sort_values("Quantidade", ascending=False).head(10)[cols_prod], use_container_width=True, hide_index=True)
        with aba2:
            st.dataframe(prod.sort_values("Lucro Bruto", ascending=False).head(10)[cols_prod], use_container_width=True, hide_index=True)
        with aba3:
            st.dataframe(prod.sort_values("Margem %", ascending=True).head(10)[cols_prod], use_container_width=True, hide_index=True)
        with aba4:
            st.dataframe(prod.sort_values("CMV %", ascending=False).head(10)[cols_prod], use_container_width=True, hide_index=True)
        with aba5:
            promo = prod[(prod["CMV %"] <= meta_cmv) & (prod["Lucro Bruto"] > 0)].sort_values("Margem %", ascending=False).head(10)
            st.caption("Produtos com CMV saudável e margem melhor para ação comercial/promoção controlada.")
            st.dataframe(promo[cols_prod], use_container_width=True, hide_index=True)

    st.markdown("<div class='section-title'>📊 DRE na palma da mão</div>", unsafe_allow_html=True)
    dre_mobile = pd.DataFrame([
        {"Linha": "Receita", "Valor": dre["receita"]},
        {"Linha": "CMV Total", "Valor": -dre["cmv_total"]},
        {"Linha": "Lucro Bruto", "Valor": dre["lucro_bruto"]},
        {"Linha": "Despesas", "Valor": -dre["despesas"]},
        {"Linha": "Lucro Operacional", "Valor": dre["lucro_operacional"]},
    ])
    st.dataframe(
        dre_mobile,
        use_container_width=True,
        hide_index=True,
        column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}
    )

    st.markdown("<div class='section-title'>📦 Estoque crítico</div>", unsafe_allow_html=True)
    if estoque_baixo.empty:
        st.success("Nenhum item crítico no estoque.")
    else:
        st.dataframe(estoque_baixo[["Produto", "Qtd Atual", "Estoque Mínimo", "Valor Estoque"]], use_container_width=True, hide_index=True)


# =========================================================
# PRECIFICAÇÃO
# =========================================================
elif menu == "Precificação":
    st.subheader("Precificação Inteligente")
    st.caption("Veja se cada produto está sendo vendido pelo preço certo de acordo com a meta de CMV.")

    meta_padrao = get_float_config("meta_cmv_ideal", META_CMV)

    c1, c2, c3 = st.columns([1, 1, 2])
    meta_usada = c1.number_input(
        "Meta CMV para simulação (%)",
        min_value=1.0,
        max_value=90.0,
        value=float(meta_padrao),
        step=0.5
    )

    filtro_status = c2.selectbox(
        "Filtro",
        ["Todos", "🔴 Reprecificar", "✅ OK", "⚠️ Sem preço de venda", "⚠️ Sem custo/estoque"]
    )

    termo = c3.text_input("Buscar produto")

    dfp = precificacao_df(meta_usada)

    if dfp.empty:
        st.info("Ainda não há produtos/estoque para analisar.")
    else:
        if filtro_status != "Todos":
            dfp = dfp[dfp["Status"] == filtro_status]

        if termo.strip():
            dfp = dfp[dfp["Produto"].str.contains(termo.strip(), case=False, na=False)]

        total_produtos = len(dfp)
        reprecificar = len(dfp[dfp["Status"] == "🔴 Reprecificar"])
        sem_preco = len(dfp[dfp["Status"] == "⚠️ Sem preço de venda"])
        ok = len(dfp[dfp["Status"] == "✅ OK"])

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            metric_card("Produtos analisados", total_produtos, "Itens filtrados", "blue")
        with k2:
            metric_card("Reprecificar", reprecificar, "Acima da meta CMV", "bad" if reprecificar else "good")
        with k3:
            metric_card("Sem preço", sem_preco, "Cadastre preço de venda", "warn" if sem_preco else "good")
        with k4:
            metric_card("Dentro da meta", ok, "Produtos saudáveis", "good")

        st.markdown("### Produtos com preço sugerido")

        st.dataframe(
            dfp,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Custo Atual PEPS/Médio": st.column_config.NumberColumn(format="R$ %.2f"),
                "Preço Venda Atual": st.column_config.NumberColumn(format="R$ %.2f"),
                "CMV Atual %": st.column_config.NumberColumn(format="%.2f%%"),
                "Preço Mínimo pela Meta": st.column_config.NumberColumn(format="R$ %.2f"),
                "Diferença para Preço Ideal": st.column_config.NumberColumn(format="R$ %.2f"),
                "Lucro Bruto Unitário": st.column_config.NumberColumn(format="R$ %.2f"),
                "Margem Bruta %": st.column_config.NumberColumn(format="%.2f%%"),
            }
        )

        st.markdown("### Simulador rápido")

        produtos_lista = list(dfp["Produto"].unique())
        if produtos_lista:
            produto_sim = st.selectbox("Produto para simular", produtos_lista)
            linha = dfp[dfp["Produto"] == produto_sim].iloc[0]

            custo = float(linha["Custo Atual PEPS/Médio"])
            preco_atual = float(linha["Preço Venda Atual"])
            preco_sim = st.number_input(
                "Novo preço de venda simulado",
                min_value=0.0,
                value=float(round(preco_atual, 2)),
                step=0.5
            )

            cmv_sim = (custo / preco_sim * 100) if preco_sim > 0 else 0
            lucro_sim = preco_sim - custo
            margem_sim = (lucro_sim / preco_sim * 100) if preco_sim > 0 else 0

            s1, s2, s3, s4 = st.columns(4)
            with s1:
                metric_card("Custo Atual", moeda(custo), "Custo PEPS/médio atual", "blue")
            with s2:
                metric_card("CMV Simulado", format_pct(cmv_sim), f"Meta: {format_pct(meta_usada)}", "good" if cmv_sim <= meta_usada else "bad")
            with s3:
                metric_card("Lucro Unitário", moeda(lucro_sim), "Preço - custo", "good" if lucro_sim >= 0 else "bad")
            with s4:
                metric_card("Margem Simulada", format_pct(margem_sim), "Margem bruta", "good" if margem_sim > 0 else "bad")

            if cmv_sim > meta_usada:
                preco_ideal = custo / (meta_usada / 100) if meta_usada else 0
                st.error(f"Para bater CMV de {format_pct(meta_usada)}, o preço mínimo sugerido é {moeda(preco_ideal)}.")
            else:
                st.success("Preço simulado dentro da meta de CMV.")


# =========================================================
# CONTAS A PAGAR
# =========================================================
elif menu == "Contas a Pagar":

    st.markdown("""
        <style>
            .cap-hero {
                background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%);
                color: white;
                padding: 24px 28px;
                border-radius: 22px;
                margin-bottom: 18px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
            }
            .cap-title { font-size: 30px; font-weight: 900; margin-bottom: 4px; }
            .cap-sub { font-size: 14px; color: #dbeafe; font-weight: 600; }
            .cap-chip {
                display: inline-block;
                margin-top: 12px;
                background: rgba(255,255,255,.12);
                border: 1px solid rgba(255,255,255,.18);
                border-radius: 999px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 800;
            }
            .cap-resumo-chip {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                padding: 10px 14px;
                font-size: 13px;
                color: #475569;
                font-weight: 700;
                margin-bottom: 12px;
            }
            @media (max-width: 720px) {
                .cap-hero { padding: 18px 16px; }
                .cap-title { font-size: 24px; }
            }
        </style>
    """, unsafe_allow_html=True)

    hoje = date.today()
    nome_empresa = get_config("nome_empresa", "Restaurante")

    st.markdown(f"""
        <div class="cap-hero">
            <div class="cap-title">💰 Contas a Pagar</div>
            <div class="cap-sub">{nome_empresa} • gestão de despesas operacionais</div>
            <div class="cap-chip">Controle em aberto, vencidas e pagas</div>
        </div>
    """, unsafe_allow_html=True)

    with st.expander("➕ Nova despesa", expanded=False):
        with st.form("form_contas_pagar_nova"):
            c_form1, c_form2 = st.columns(2)
            data_desp = c_form1.date_input("Vencimento", value=hoje, key="cap_data_desp")
            categoria = c_form2.selectbox("Categoria", CATEGORIAS_DESPESA, key="cap_categoria")
            descricao = st.text_input("Descrição", key="cap_descricao")
            c_val, c_obs = st.columns([1, 2])
            valor = c_val.number_input("Valor", min_value=0.01, step=10.0, key="cap_valor")
            obs = c_obs.text_input("Observação", key="cap_obs")
            salvar_nova = st.form_submit_button("Lançar despesa", use_container_width=True)

            if salvar_nova:
                if not str(descricao).strip():
                    st.error("Informe uma descrição para a despesa.")
                else:
                    inserir_despesa(data_desp, categoria, descricao.strip(), valor, obs.strip())
                    st.success("Despesa lançada com sucesso.")
                    st.rerun()

    f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1.4])
    periodo = f1.selectbox(
        "Período",
        ["Hoje", "Ontem", "Últimos 7 dias", "Últimos 30 dias", "Este mês", "Mês passado", "Personalizado", "Todos"],
        index=4,
        key="cap_periodo"
    )

    data_ini_cap = hoje.replace(day=1)
    data_fim_cap = hoje

    if periodo == "Personalizado":
        data_ini_cap = f2.date_input("Data inicial", value=data_ini_cap, key="cap_ini")
        data_fim_cap = f3.date_input("Data final", value=data_fim_cap, key="cap_fim")
    else:
        f2.write("")
        f3.write("")

    status_filtro = f4.selectbox(
        "Status",
        ["Todos", "Em aberto", "Vencidas", "Pago"],
        key="cap_status"
    )

    c5, c6, c7 = st.columns([1, 1, 2])
    categoria_filtro = c5.selectbox(
        "Categoria",
        ["Todas"] + CATEGORIAS_DESPESA,
        key="cap_categoria_filtro"
    )
    busca = c6.text_input("Buscar", placeholder="Descrição, categoria...", key="cap_busca")
    if c7.button("Limpar filtros", use_container_width=True):
        st.session_state["cap_periodo"] = "Este mês"
        st.session_state["cap_status"] = "Todos"
        st.session_state["cap_categoria_filtro"] = "Todas"
        st.session_state["cap_busca"] = ""
        st.rerun()

    if periodo == "Todos":
        df_base = despesas_com_status_df()
        label_periodo_cap = "Todos os lançamentos"
    else:
        inicio_cap, fim_cap = datas_periodo(periodo, data_ini_cap, data_fim_cap)
        df_base = despesas_com_status_df(inicio_cap, fim_cap)
        label_periodo_cap = periodo_label(inicio_cap, fim_cap)

    df_filtrado = filtrar_despesas_contas(
        df_base,
        status_filtro=status_filtro,
        categoria=categoria_filtro,
        busca=busca,
        hoje=hoje,
    )

    resumo = resumo_contas_pagar(df_filtrado, hoje)

    st.markdown(f"### Resumo • {label_periodo_cap}")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        metric_card(
            "Em aberto",
            moeda(resumo["total_aberto"]),
            f"{resumo['qtd_aberto']} lançamento(s)",
            "warn" if resumo["total_aberto"] > 0 else "good",
            "💳"
        )
    with k2:
        metric_card(
            "Vencidas",
            moeda(resumo["total_vencidas"]),
            f"{resumo['qtd_vencidas']} pendência(s)",
            "bad" if resumo["total_vencidas"] > 0 else "good",
            "🔴"
        )
    with k3:
        metric_card(
            "Pagas",
            moeda(resumo["total_pagas"]),
            f"{resumo['qtd_pagas']} quitada(s)",
            "good",
            "✅"
        )
    with k4:
        metric_card(
            "Total filtrado",
            moeda(resumo["total_periodo"]),
            f"{resumo['qtd_total']} lançamento(s)",
            "blue",
            "📊"
        )

    st.markdown(
        f'<div class="cap-resumo-chip">{resumo["qtd_total"]} lançamento(s) • '
        f'{moeda(resumo["total_aberto"])} em aberto • '
        f'{moeda(resumo["total_vencidas"])} vencidas</div>',
        unsafe_allow_html=True,
    )

    st.markdown("### Lançamentos")

    if df_filtrado.empty:
        st.info("Nenhuma despesa encontrada com os filtros atuais.")
    else:
        tabela = df_filtrado.copy()
        tabela["Situação"] = tabela.apply(
            lambda r: situacao_despesa(r["status"], r["data"], hoje)[1],
            axis=1,
        )
        tabela["Vencimento"] = pd.to_datetime(tabela["data"]).dt.strftime("%d/%m/%Y")
        tabela["Valor"] = tabela["valor"].astype(float)
        tabela["Descrição"] = tabela["descricao"].fillna("")
        tabela["Observação"] = tabela["observacao"].fillna("")

        exibir = tabela[[
            "id", "Vencimento", "categoria", "Descrição", "Valor", "Situação", "Observação"
        ]].rename(columns={
            "id": "ID",
            "categoria": "Categoria",
        })

        st.dataframe(
            exibir,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn(format="%d"),
                "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
            }
        )

        st.markdown("### Ações do lançamento")

        opcoes = {}
        for _, row in df_filtrado.iterrows():
            sit = situacao_despesa(row["status"], row["data"], hoje)[1]
            label = (
                f"#{int(row['id'])} • {pd.Timestamp(row['data']).strftime('%d/%m/%Y')} • "
                f"{row['categoria']} • {row['descricao'] or '-'} • {moeda(row['valor'])} • {sit}"
            )
            opcoes[label] = int(row["id"])

        selecionado_label = st.selectbox(
            "Selecione um lançamento",
            list(opcoes.keys()),
            key="cap_selecionado"
        )
        id_sel = opcoes[selecionado_label]
        linha_sel = df_filtrado[df_filtrado["id"] == id_sel].iloc[0]
        status_sel = str(linha_sel["status"])

        a1, a2, a3 = st.columns([1, 1, 1])

        if status_sel != "Pago":
            if a1.button("✅ Marcar como pago", use_container_width=True, key="cap_btn_pagar"):
                atualizar_status_despesa(id_sel, "Pago")
                st.toast("Despesa marcada como paga.")
                st.rerun()
        else:
            if a1.button("↩ Reabrir conta", use_container_width=True, key="cap_btn_reabrir"):
                atualizar_status_despesa(id_sel, "Em aberto")
                st.toast("Despesa reaberta.")
                st.rerun()

        confirmar_exclusao = a2.checkbox("Confirmar exclusão", key="cap_confirm_del")
        if a3.button(
            "🗑 Excluir",
            use_container_width=True,
            disabled=not confirmar_exclusao,
            key="cap_btn_excluir"
        ):
            excluir_despesa(id_sel)
            st.success("Despesa excluída com sucesso.")
            st.rerun()


# =========================================================
# DRE GERENCIAL
# =========================================================
elif menu == "DRE Gerencial":

    st.subheader("DRE Gerencial")
    st.caption("Visão financeira simplificada: receita, CMV, perdas, despesas e lucro operacional.")

    hoje = date.today()

    f1, f2, f3 = st.columns([1.2, 1, 1])
    periodo = f1.selectbox(
        "Período",
        ["Hoje", "Ontem", "Últimos 7 dias", "Últimos 30 dias", "Este mês", "Mês passado", "Personalizado"],
        index=4,
        key="dre_periodo"
    )

    data_ini = hoje.replace(day=1)
    data_fim = hoje

    if periodo == "Personalizado":
        data_ini = f2.date_input("Data inicial", value=data_ini, key="dre_ini")
        data_fim = f3.date_input("Data final", value=data_fim, key="dre_fim")
    else:
        f2.write("")
        f3.write("")

    inicio_periodo, fim_periodo = datas_periodo(periodo, data_ini, data_fim)
    label = periodo_label(inicio_periodo, fim_periodo)

    dre = dre_periodo(inicio_periodo, fim_periodo)
    lucro_liquido = dre["lucro_operacional"]

    margem_operacional = (
    (lucro_liquido / dre["receita"]) * 100
    if dre["receita"] else 0
    )

    st.markdown(f"### Resultado do período • {label}")

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        metric_card("Receita", moeda(dre["receita"]), "Vendas lançadas", "blue")
    with c2:
        metric_card("CMV Total", moeda(dre["cmv_total"]), format_pct(dre["cmv_pct"]), "warn" if dre["cmv_pct"] > get_float_config("meta_cmv_ideal", META_CMV) else "good")
    with c3:
        metric_card("Lucro Bruto", moeda(dre["lucro_bruto"]), format_pct(dre["margem_bruta_pct"]), "good" if dre["lucro_bruto"] >= 0 else "bad")
    with c4:
        metric_card("Despesas", moeda(dre["despesas"]), "Despesas lançadas", "warn" if dre["despesas"] > 0 else "good")
    with c5:
        metric_card("Lucro Operacional", moeda(dre["lucro_operacional"]), format_pct(dre["margem_operacional_pct"]), "good" if dre["lucro_operacional"] >= 0 else "bad")
    with c6:
       metric_card(
        "Lucro Líquido",
        moeda(lucro_liquido),
        format_pct(margem_operacional),
        "good" if lucro_liquido > 0 else "bad"
    )
    st.markdown("### Estrutura da DRE")

    dre_linhas = pd.DataFrame([
        {"Linha": "Receita Bruta", "Valor": dre["receita"], "% Receita": 100 if dre["receita"] else 0},
        {"Linha": "(-) CMV das Vendas", "Valor": -dre["cmv_venda"], "% Receita": -(dre["cmv_venda"] / dre["receita"] * 100) if dre["receita"] else 0},
        {"Linha": "(-) Perdas / Consumo Interno / Ajustes", "Valor": -dre["perdas"], "% Receita": -dre["perdas_pct"]},
        {"Linha": "(=) Lucro Bruto", "Valor": dre["lucro_bruto"], "% Receita": dre["margem_bruta_pct"]},
        {"Linha": "(-) Despesas Operacionais", "Valor": -dre["despesas"], "% Receita": -(dre["despesas"] / dre["receita"] * 100) if dre["receita"] else 0},
        {"Linha": "(=) Lucro Operacional", "Valor": dre["lucro_operacional"], "% Receita": dre["margem_operacional_pct"]},
    ])

    st.dataframe(
        dre_linhas,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
            "% Receita": st.column_config.NumberColumn(format="%.2f%%"),
        }
    )

    st.markdown("---")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("### Lançar despesa operacional")

        with st.form("form_despesa"):
            data_desp = st.date_input("Data da despesa", value=hoje)
            categoria = st.selectbox(
                "Categoria",
                CATEGORIAS_DESPESA
            )
            descricao = st.text_input("Descrição")
            valor = st.number_input("Valor da despesa", min_value=0.01, step=10.0)
            obs = st.text_area("Observação")
            salvar = st.form_submit_button("Lançar despesa")

            if salvar:
                inserir_despesa(data_desp, categoria, descricao, valor, obs)
                st.success("Despesa lançada com sucesso. Atualize a página ou troque o filtro para recalcular.")

    with right:
        st.markdown("### Despesas por categoria")

        despesas_periodo = dre["df_despesas"]

        if despesas_periodo.empty:
            st.info("Nenhuma despesa lançada no período.")
        else:
            desp_cat = despesas_periodo.groupby("Categoria", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)

            fig_desp = px.bar(
                desp_cat,
                x="Categoria",
                y="Valor",
                text="Valor",
                color="Valor",
                color_continuous_scale=["#dbeafe", "#60a5fa", "#2563eb", "#1e3a8a"]
            )

            fig_desp.update_layout(
                height=420,
                paper_bgcolor="white",
                plot_bgcolor="white",
                margin=dict(l=10, r=10, t=30, b=10),
                coloraxis_showscale=False
            )

            fig_desp.update_traces(
                texttemplate="R$ %{y:,.2f}",
                textposition="outside",
                marker_line_width=0
            )

            st.plotly_chart(fig_desp, use_container_width=True)

            st.dataframe(
                desp_cat,
                use_container_width=True,
                hide_index=True,
                column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}
            )

    st.markdown("---")

    st.markdown("### Detalhamento de despesas")
    despesas_periodo = dre["df_despesas"]

    if despesas_periodo.empty:
        st.info("Sem despesas no período.")
    else:
        st.dataframe(
            despesas_periodo,
            use_container_width=True,
            hide_index=True,
            column_config={"Valor": st.column_config.NumberColumn(format="R$ %.2f")}
        )

    st.markdown("### Diagnóstico CFO")

    if dre["receita"] <= 0:
        alerta_box("Sem receita no período. Lance vendas para analisar a DRE.", "info")
    else:
        meta = get_float_config("meta_cmv_ideal", META_CMV)

        if dre["cmv_pct"] > meta:
            alerta_box(f"CMV acima da meta: {format_pct(dre['cmv_pct'])} vs meta {format_pct(meta)}.", "bad")
        else:
            alerta_box(f"CMV dentro da meta: {format_pct(dre['cmv_pct'])}.", "good")

        if dre["margem_operacional_pct"] < 0:
            alerta_box("Lucro operacional negativo. O restaurante está operando no prejuízo no período.", "bad")
        elif dre["margem_operacional_pct"] < 10:
            alerta_box("Margem operacional baixa. Vale revisar preços, perdas e despesas fixas.", "warn")
        else:
            alerta_box("Margem operacional saudável para o período analisado.", "good")

        if dre["perdas_pct"] > 5:
            alerta_box(f"Perdas altas: {format_pct(dre['perdas_pct'])} da receita. Investigar desperdício, vencimento ou consumo interno.", "warn")


# =========================================================
# CURVA ABC + COMPRAS INTELIGENTES
# =========================================================
elif menu == "Curva ABC":

    st.subheader("Curva ABC + Compras Inteligentes")
    st.caption("Descubra os produtos mais importantes do restaurante e receba sugestões inteligentes de compra.")

    hoje = date.today()

    periodo = st.selectbox(
        "Período de análise",
        ["Últimos 7 dias", "Últimos 30 dias", "Este mês", "Personalizado"],
        index=1
    )

    data_ini = hoje.replace(day=1)
    data_fim = hoje

    c1, c2 = st.columns(2)

    if periodo == "Personalizado":
        data_ini = c1.date_input("Data inicial", value=data_ini)
        data_fim = c2.date_input("Data final", value=data_fim)

    inicio_periodo, fim_periodo = datas_periodo(periodo, data_ini, data_fim)

    df = resumo_periodo(inicio_periodo, fim_periodo)

    vendas = df[df["TipoSaida"] == "Venda"].copy()

    if vendas.empty:
        st.warning("Sem vendas no período selecionado.")
    else:

        resumo = vendas.groupby("Produto", as_index=False).agg(
            Receita=("Receita", "sum"),
            CMV=("CMV", "sum"),
            Quantidade=("Quantidade", "sum")
        )

        resumo["Lucro Bruto"] = resumo["Receita"] - resumo["CMV"]

        resumo = resumo.sort_values("Receita", ascending=False)

        resumo["% Receita"] = (
            resumo["Receita"] /
            resumo["Receita"].sum()
        ) * 100

        resumo["% Acumulado"] = resumo["% Receita"].cumsum()

        def classificar_abc(valor):
            if valor <= 80:
                return "A"
            elif valor <= 95:
                return "B"
            return "C"

        resumo["Classe ABC"] = resumo["% Acumulado"].apply(classificar_abc)

        resumo["Margem %"] = resumo.apply(
            lambda r: (r["Lucro Bruto"] / r["Receita"] * 100)
            if r["Receita"] > 0 else 0,
            axis=1
        )

        st.markdown("### Curva ABC de Receita")

        st.dataframe(
            resumo,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Receita": st.column_config.NumberColumn(format="R$ %.2f"),
                "CMV": st.column_config.NumberColumn(format="R$ %.2f"),
                "Lucro Bruto": st.column_config.NumberColumn(format="R$ %.2f"),
                "% Receita": st.column_config.NumberColumn(format="%.2f%%"),
                "% Acumulado": st.column_config.NumberColumn(format="%.2f%%"),
                "Margem %": st.column_config.NumberColumn(format="%.2f%%"),
            }
        )

        st.markdown("### Resumo Executivo")

        a = len(resumo[resumo["Classe ABC"] == "A"])
        b = len(resumo[resumo["Classe ABC"] == "B"])
        c = len(resumo[resumo["Classe ABC"] == "C"])

        ca, cb, cc = st.columns(3)

        with ca:
            metric_card("Classe A", a, "Produtos mais importantes", "good")

        with cb:
            metric_card("Classe B", b, "Produtos intermediários", "warn")

        with cc:
            metric_card("Classe C", c, "Baixa representatividade", "blue")

        st.markdown("---")

        st.markdown("### Compras Inteligentes")

        estoque = estoque_df()

        compras = estoque.merge(
            resumo,
            on="Produto",
            how="left"
        )

        compras["Quantidade"] = compras["Quantidade"].fillna(0)

        compras["Venda Média Dia"] = compras["Quantidade"] / 30

        compras["Dias Cobertura"] = compras.apply(
            lambda r: (
                r["Qtd Atual"] / r["Venda Média Dia"]
            ) if r["Venda Média Dia"] > 0 else 999,
            axis=1
        )

        compras["Sugestão Compra"] = compras.apply(
            lambda r: max(
                0,
                round((r["Venda Média Dia"] * 15) - r["Qtd Atual"], 0)
            ),
            axis=1
        )

        compras["Status"] = compras["Dias Cobertura"].apply(
            lambda x:
                "🔴 Comprar Urgente" if x <= 3 else
                "🟡 Atenção" if x <= 7 else
                "✅ OK"
        )

        compras_view = compras[[
            "Produto",
            "Qtd Atual",
            "Quantidade",
            "Dias Cobertura",
            "Sugestão Compra",
            "Status"
        ]]

        compras_view.columns = [
            "Produto",
            "Estoque Atual",
            "Qtd Vendida",
            "Dias Cobertura",
            "Sugestão Compra",
            "Status"
        ]

        st.dataframe(
            compras_view,
            use_container_width=True,
            hide_index=True
        )

        st.markdown("### Produtos Parados")

        parados = compras_view[
            (compras_view["Qtd Vendida"] <= 0) &
            (compras_view["Estoque Atual"] > 0)
        ]

        if parados.empty:
            st.success("Nenhum produto parado encontrado.")
        else:
            st.dataframe(
                parados,
                use_container_width=True,
                hide_index=True
            )



# =========================================================
# USUÁRIOS
# =========================================================
elif menu == "Usuários":
    st.subheader("Usuários e Permissões")
    st.caption("Cadastre usuários e defina o perfil de acesso.")

    if str(usuario_logado().get("tipo", "")).lower() != "admin":
        st.error("Somente administrador pode acessar esta tela.")
        st.stop()

    st.info("""
    **Perfis disponíveis**
    - admin: acesso total
    - gerente: acesso geral, exceto usuários
    - financeiro: painéis, DRE, precificação, curva ABC e relatórios
    - operador: entradas, saídas, estoque e movimentações
    """)

    usuarios = carregar_usuarios()

    with st.form("novo_usuario_form"):
        st.markdown("### Criar usuário")
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome")
        novo_usuario = c2.text_input("Usuário")

        c3, c4 = st.columns(2)
        nova_senha = c3.text_input("Senha", type="password")
        tipo = c4.selectbox("Perfil", ["admin", "gerente", "financeiro", "operador"])

        criar = st.form_submit_button("Criar usuário")

        if criar:
            if not nome or not novo_usuario or not nova_senha:
                st.error("Preencha nome, usuário e senha.")
            elif any(u.get("usuario") == novo_usuario for u in usuarios):
                st.error("Esse usuário já existe.")
            else:
                usuarios.append({
                    "usuario": novo_usuario.strip(),
                    "senha": nova_senha,
                    "tipo": tipo,
                    "nome": nome.strip(),
                    "ativo": True
                })
                salvar_usuarios(usuarios)
                st.success("Usuário criado com sucesso.")
                st.rerun()

    st.markdown("### Usuários cadastrados")
    dfu = pd.DataFrame(usuarios)
    if dfu.empty:
        st.warning("Nenhum usuário cadastrado.")
    else:
        cols = [c for c in ["nome", "usuario", "tipo", "ativo"] if c in dfu.columns]
        st.dataframe(dfu[cols], use_container_width=True, hide_index=True)

        st.markdown("### Alterar senha ou status")
        opcoes = [u.get("usuario", "") for u in usuarios]
        escolhido = st.selectbox("Usuário", opcoes)

        nova_senha2 = st.text_input("Nova senha", type="password")
        col1, col2, col3 = st.columns(3)

        if col1.button("Alterar senha"):
            if not nova_senha2:
                st.error("Informe a nova senha.")
            else:
                for u in usuarios:
                    if u.get("usuario") == escolhido:
                        u["senha"] = nova_senha2
                salvar_usuarios(usuarios)
                st.success("Senha alterada.")

        if col2.button("Ativar"):
            for u in usuarios:
                if u.get("usuario") == escolhido:
                    u["ativo"] = True
            salvar_usuarios(usuarios)
            st.success("Usuário ativado.")
            st.rerun()

        if col3.button("Desativar"):
            if escolhido == usuario_logado().get("usuario"):
                st.error("Você não pode desativar seu próprio usuário.")
            else:
                for u in usuarios:
                    if u.get("usuario") == escolhido:
                        u["ativo"] = False
                salvar_usuarios(usuarios)
                st.success("Usuário desativado.")
                st.rerun()



# =========================================================
# PRODUTOS
# =========================================================
elif menu == "Produtos":
    st.subheader("Cadastro Profissional de Produtos")
    st.caption("Catálogo com SKU, código de barras, custo de referência, preço e estoque integrado ao PEPS.")

    with st.form("prod"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código interno (SKU)", placeholder="Ex: CRO-001 ou deixe vazio para gerar")
        codigo_barras = c2.text_input("Código de barras (EAN)", placeholder="Opcional — leitor futuro")

        c3, c4 = st.columns(2)
        nome = c3.text_input("Nome")
        cat = c4.text_input("Categoria")

        c5, c6, c7 = st.columns(3)
        un = c5.selectbox("Unidade", ["UN", "KG", "G", "L", "ML", "CX"])
        minimo = c6.number_input("Estoque mínimo", min_value=0.0, step=1.0)
        custo_ref = c7.number_input("Custo referência (R$)", min_value=0.0, step=0.5, help="Usado quando ainda não há entrada PEPS.")

        preco = st.number_input("Preço de venda (R$)", min_value=0.0, step=0.5)

        with st.expander("Dados fiscais (NFC-e futura)"):
            f1, f2 = st.columns(2)
            ncm = f1.text_input("NCM", placeholder="Ex: 19059090")
            cst = f2.text_input("CST", placeholder="Ex: 102")
            f3, f4, f5 = st.columns(3)
            icms = f3.number_input("ICMS (%)", min_value=0.0, step=0.5)
            pis = f4.number_input("PIS (%)", min_value=0.0, step=0.5)
            cofins = f5.number_input("COFINS (%)", min_value=0.0, step=0.5)

        ok = st.form_submit_button("Salvar produto", use_container_width=True)

        if ok:
            if not str(nome).strip():
                st.error("Informe o nome do produto.")
            else:
                try:
                    inserir_produto_catalogo(
                        nome=nome,
                        categoria=cat or "Mercadoria",
                        unidade=un,
                        estoque_minimo=minimo,
                        preco_venda=preco,
                        codigo=codigo,
                        codigo_barras=codigo_barras,
                        custo_referencia=custo_ref,
                        ncm=ncm,
                        cst=cst,
                        icms=icms,
                        pis=pis,
                        cofins=cofins,
                    )
                    st.success("Produto cadastrado com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.warning(f"Não salvei: {e}")

    st.markdown("### Catálogo atual")
    catalogo = produtos_catalogo_df()

    if catalogo.empty:
        st.info("Nenhum produto cadastrado.")
    else:
        exibir_cat = catalogo[[
            "Código", "Nome", "Categoria", "Unidade",
            "Custo", "Preço", "Estoque", "Código de Barras"
        ]]
        st.dataframe(
            exibir_cat,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Custo": st.column_config.NumberColumn(format="R$ %.2f"),
                "Preço": st.column_config.NumberColumn(format="R$ %.2f"),
                "Estoque": st.column_config.NumberColumn(format="%.2f"),
            }
        )



# =========================================================
# CONFIGURAÇÕES
# =========================================================
elif menu == "Configurações":
    st.subheader("Configurações do Sistema")
    st.caption("Aqui você define as metas e dados principais da empresa. As metas ficam salvas no banco do sistema.")

    with st.form("config_form"):
        nome_empresa = st.text_input("Nome da empresa", value=get_config("nome_empresa", "Restaurante"))
        categoria_negocio = st.selectbox(
            "Categoria do negócio",
            ["Restaurante", "Lanchonete", "Cafeteria", "Hamburgueria", "Padaria", "Açaiteria", "Dark Kitchen", "Bar", "Outro"],
            index=0
        )

        c1, c2, c3 = st.columns(3)
        meta_ideal = c1.number_input("Meta CMV ideal (%)", min_value=1.0, max_value=90.0, value=get_float_config("meta_cmv_ideal", META_CMV), step=0.5)
        meta_alerta = c2.number_input("Faixa de atenção (%)", min_value=1.0, max_value=90.0, value=get_float_config("meta_cmv_alerta", META_CMV + 4), step=0.5)
        meta_critica = c3.number_input("Faixa crítica (%)", min_value=1.0, max_value=90.0, value=get_float_config("meta_cmv_critica", META_CMV + 8), step=0.5)

        st.markdown("---")
        st.markdown("### 🔔 Alertas automáticos no WhatsApp")
        st.caption("Deixe opcional: o dono ativa se quiser receber alertas. Se desmarcar, os alertas continuam apenas no painel.")

        whatsapp_ativo = st.checkbox(
            "Ativar envio automático de alertas no WhatsApp",
            value=get_config("whatsapp_ativo", "0") == "1"
        )

        w1, w2 = st.columns(2)
        whatsapp_numero = w1.text_input(
            "Número do responsável",
            value=get_config("whatsapp_numero", ""),
            placeholder="Ex: 5521999999999"
        )
        whatsapp_horario = w2.text_input(
            "Horário do resumo diário",
            value=get_config("whatsapp_horario", "08:00"),
            placeholder="Ex: 08:00"
        )

        wa1, wa2, wa3 = st.columns(3)
        whatsapp_alerta_cmv = wa1.checkbox("Avisar CMV acima da meta", value=get_config("whatsapp_alerta_cmv", "1") == "1")
        whatsapp_alerta_estoque = wa2.checkbox("Avisar estoque crítico", value=get_config("whatsapp_alerta_estoque", "1") == "1")
        whatsapp_alerta_dre = wa3.checkbox("Avisar DRE negativo", value=get_config("whatsapp_alerta_dre", "1") == "1")

        salvar = st.form_submit_button("Salvar configurações")

        if salvar:
            set_config("nome_empresa", nome_empresa)
            set_config("categoria_negocio", categoria_negocio)
            set_config("meta_cmv_ideal", meta_ideal)
            set_config("meta_cmv_alerta", meta_alerta)
            set_config("meta_cmv_critica", meta_critica)
            set_config("whatsapp_ativo", "1" if whatsapp_ativo else "0")
            set_config("whatsapp_numero", whatsapp_numero)
            set_config("whatsapp_horario", whatsapp_horario)
            set_config("whatsapp_alerta_cmv", "1" if whatsapp_alerta_cmv else "0")
            set_config("whatsapp_alerta_estoque", "1" if whatsapp_alerta_estoque else "0")
            set_config("whatsapp_alerta_dre", "1" if whatsapp_alerta_dre else "0")
            st.success("Configurações salvas com sucesso.")

    st.info("Exemplo: se sua cafeteria trabalha com CMV ideal de 30%, coloque 30%. O dashboard passa a usar essa meta automaticamente.")
    st.markdown("### Parâmetros atuais")
    st.write(f"**Empresa:** {get_config('nome_empresa', 'Restaurante')}")
    st.write(f"**Meta CMV ideal:** {format_pct(get_float_config('meta_cmv_ideal', META_CMV))}")
    st.write(f"**Atenção:** {format_pct(get_float_config('meta_cmv_alerta', META_CMV + 4))}")
    st.write(f"**Crítico:** {format_pct(get_float_config('meta_cmv_critica', META_CMV + 8))}")

    st.markdown("### 🔔 WhatsApp automático")
    whatsapp_ativo_atual = get_config("whatsapp_ativo", "0") == "1"
    numero_atual = get_config("whatsapp_numero", "")
    horario_atual = get_config("whatsapp_horario", "08:00")

    if whatsapp_ativo_atual:
        st.success(f"WhatsApp automático ATIVADO para {numero_atual or 'número não informado'} às {horario_atual}.")
    else:
        st.warning("WhatsApp automático DESATIVADO. Os alertas aparecem somente no painel.")

    hoje_cfg = date.today()
    inicio_cfg, fim_cfg = datas_periodo("Este mês")
    dre_cfg = dre_periodo(inicio_cfg, fim_cfg)
    estoque_baixo_cfg = estoque_df()
    estoque_baixo_cfg = estoque_baixo_cfg[estoque_baixo_cfg["Qtd Atual"] <= estoque_baixo_cfg["Estoque Mínimo"]]
    cmv_cfg = dre_cfg["cmv_pct"]
    meta_cfg = get_float_config("meta_cmv_ideal", META_CMV)

    inteligencia_cfg = gerar_alertas_inteligentes_erp(inicio_cfg, fim_cfg)
    previa_whatsapp = inteligencia_cfg["mensagem_whatsapp"]

    st.text_area("Prévia da mensagem inteligente de WhatsApp", value=previa_whatsapp, height=360)

    st.markdown("#### Integração Z-API")
    zapi_client_token_atual = get_config("zapi_client_token", "")
    with st.expander("Configuração avançada da Z-API", expanded=False):
        novo_client_token = st.text_input(
            "Client-Token da Z-API (se sua conta exigir)",
            value=zapi_client_token_atual,
            type="password",
            help="Algumas contas da Z-API exigem Client-Token no cabeçalho. Se não tiver, deixe em branco."
        )
        if st.button("Salvar Client-Token"):
            set_config("zapi_client_token", novo_client_token.strip())
            st.success("Client-Token salvo.")

    st.markdown("#### 🤖 IA Consultora Real")
    with st.expander("Configuração da OpenAI", expanded=False):
        openai_key_atual = get_config("openai_api_key", "")
        openai_model_atual = get_config("openai_model", "gpt-4.1-mini")
        nova_openai_key = st.text_input(
            "OpenAI API Key",
            value=openai_key_atual,
            type="password",
            help="Chave usada para a IA responder perguntas livres com base nos dados do ERP."
        )
        novo_openai_model = st.text_input(
            "Modelo da IA",
            value=openai_model_atual,
            help="Exemplo: gpt-4.1-mini. Se sua conta tiver outro modelo liberado, você pode alterar aqui."
        )
        if st.button("Salvar configuração da IA"):
            set_config("openai_api_key", nova_openai_key.strip())
            set_config("openai_model", novo_openai_model.strip())
            st.success("Configuração da IA salva.")

    if get_config("openai_api_key", "").strip():
        st.success("IA real ATIVADA. O Consultor IA responderá perguntas livres usando os dados do ERP.")
    else:
        st.warning("IA real ainda não configurada. O Consultor IA continuará usando o motor local por regras.")

    if st.button("Enviar teste real no WhatsApp"):
        if not whatsapp_ativo_atual:
            st.warning("Ative o WhatsApp automático antes de enviar teste.")
        elif not numero_atual:
            st.warning("Informe o número do responsável nas configurações.")
        else:
            ok, msg = enviar_whatsapp_zapi(numero_atual, previa_whatsapp)
            if ok:
                st.success("WhatsApp enviado com sucesso.")
            else:
                st.error(msg)


# =========================================================
# IMPORTAR NOTA XML
# =========================================================
elif menu == "Importar Nota":
    st.subheader("Importar XML de NF-e/NFC-e")

    arq = st.file_uploader("Envie o XML da nota", type=["xml"])

    if arq:
        try:
            d = ler_xml(arq.getvalue())

            st.write(
                f"Fornecedor: **{d['fornecedor'] or '-'}** | "
                f"Data: **{d['data_emissao']}** | "
                f"Chave: **{d['chave'] or '-'}**"
            )

            st.dataframe(d["itens"], use_container_width=True)

            cat = st.text_input("Categoria padrão para produtos novos", "Mercadoria")

            if st.button("Confirmar entrada no estoque"):
                for _, it in d["itens"].iterrows():
                    pid = get_or_create(
                        str(it["Produto"]).strip(),
                        cat,
                        str(it["Unidade"]).strip() or "UN"
                    )

                    entrada(
                        pid,
                        d["data_emissao"],
                        float(it["Quantidade"]),
                        float(it["Valor Unitário"]),
                        d["fornecedor"],
                        f"XML Código {it['Código']} NCM {it['NCM']} CFOP {it['CFOP']}",
                        d["chave"]
                    )

                st.success("Nota lançada no estoque.")

        except Exception as e:
            st.error(f"Erro ao ler XML: {e}")


# =========================================================
# IMPORTAR CUPOM FOTO OCR
# =========================================================
elif menu == "Importar Cupom Foto":
    st.subheader("Importar Cupom por Foto / OCR")
    st.caption("Envie uma foto do cupom. O sistema lê, filtra somente produtos cadastrados e baixa pelo PEPS.")

    st.warning("A leitura por foto depende da qualidade da imagem. Sempre confira antes de confirmar.")

    arq_img = st.file_uploader("Envie a foto do cupom", type=["jpg", "jpeg", "png"])

    texto_extraido = ""

    if arq_img:
        st.image(arq_img, caption="Cupom enviado", width=350)
        texto_extraido = ler_texto_imagem(arq_img)

        if texto_extraido.startswith("ERRO_OCR"):
            st.error("OCR ainda não está configurado corretamente neste computador.")
            st.code(texto_extraido)
            texto_extraido = ""
        else:
            st.success("Texto extraído da imagem.")

    texto_manual = st.text_area(
        "Texto do cupom lido pelo OCR ou colado manualmente",
        value=texto_extraido,
        height=250
    )

    if st.button("Analisar cupom"):
        if not texto_manual.strip():
            st.error("Nenhum texto para analisar.")
        else:
            produtos_lista = list(pdf["nome"])
            df_itens = parse_cupom_texto(texto_manual, produtos_lista)

            if df_itens.empty:
                st.warning("Nenhum produto cadastrado foi reconhecido no cupom.")
            else:
                st.session_state["cupom_itens"] = df_itens
                st.success("Itens detectados para baixa no estoque. Confira antes de confirmar.")

    if "cupom_itens" in st.session_state:
        st.subheader("Itens detectados para baixa no estoque")

        editado = st.data_editor(
            st.session_state["cupom_itens"],
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Produto Sistema": st.column_config.SelectboxColumn(
                    "Produto Sistema",
                    options=list(pdf["nome"]) if not pdf.empty else []
                ),
                "Quantidade": st.column_config.NumberColumn(
                    "Quantidade",
                    min_value=0.01,
                    step=1.0
                ),
                "Valor Unitário Venda": st.column_config.NumberColumn(
                    "Valor Unitário Venda",
                    min_value=0.0,
                    step=0.5,
                    format="R$ %.2f"
                )
            }
        )

        data_venda = st.date_input("Data da venda do cupom", date.today(), key="data_cupom_foto")

        if st.button("Confirmar saída PEPS dos itens do cupom"):
            op = dict(zip(pdf["nome"], pdf["id"]))
            erros = []
            baixados = 0

            for _, it in editado.iterrows():
                produto_nome = str(it["Produto Sistema"]).strip()
                qtd = float(it["Quantidade"])
                preco = float(it["Valor Unitário Venda"])

                if produto_nome not in op or not produto_nome:
                    continue

                try:
                    saida_peps(
                        op[produto_nome],
                        data_venda,
                        qtd,
                        preco,
                        "Venda",
                        "",
                        f"Saída automática por foto de cupom. Detectado: {it['Produto Detectado']}"
                    )

                    baixados += 1

                except Exception as e:
                    erros.append(f"{produto_nome}: {e}")

            if baixados:
                st.success(f"{baixados} item(ns) baixado(s) do estoque com sucesso.")

            if erros:
                st.error("Alguns itens cadastrados não foram baixados:")
                for e in erros:
                    st.write("- " + str(e))


# =========================================================
# ENTRADA MANUAL
# =========================================================
elif menu == "Entrada Manual":
    st.subheader("Entrada de Estoque")

    op = dict(zip(pdf["nome"], pdf["id"]))

    with st.form("ent"):
        dt = st.date_input("Data", date.today())
        prod = st.selectbox("Produto", list(op))
        qtd = st.number_input("Quantidade", min_value=0.01, step=1.0)
        vu = st.number_input("Valor unitário de compra", min_value=0.01, step=0.5)
        forn = st.text_input("Fornecedor")
        obs = st.text_area("Observação")
        ok = st.form_submit_button("Lançar entrada")

        if ok:
            entrada(op[prod], dt, qtd, vu, forn, obs)
            st.success("Entrada lançada.")


# =========================================================
# PDV / FRENTE DE CAIXA
# =========================================================
elif menu == "⚡ Operacional":
    pdv_inicializar_estado()
    pdv_preparar_estado_widgets()
    pdv_sincronizar_carrinho()
    operador_nome = user.get("nome", user.get("usuario", "Operador"))
    carrinho = st.session_state["pdv_carrinho"]
    pagamentos = st.session_state["pdv_pagamentos"]
    resumo = pdv_resumo_atual()
    erros_preco_pdv = pdv_validar_precos_carrinho(carrinho)

    sucesso_pdv = st.session_state.pop("_pdv_success", None)
    if sucesso_pdv:
        st.balloons()
        st.success(sucesso_pdv)

    erro_pdv = st.session_state.pop("_pdv_error", None)
    if erro_pdv:
        st.error(erro_pdv)

    st.markdown("""
        <style>
            .stApp { background: #eceff3 !important; }
            .block-container {
                padding-top: 0.45rem !important;
                padding-bottom: 0.45rem !important;
                max-width: 100% !important;
            }
            header[data-testid="stHeader"] {
                background: rgba(255,255,255,.92) !important;
                border-bottom: 1px solid #dde3ea !important;
            }
            div[data-testid="stRadio"] > div {
                background: #ffffff !important;
                border: 1px solid #d7dee8 !important;
                border-radius: 12px !important;
                padding: 6px 10px !important;
                box-shadow: 0 2px 8px rgba(15,23,42,.04) !important;
            }
            .pdv-top {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 14px;
                padding: 10px 16px;
                margin-bottom: 10px;
                box-shadow: 0 4px 14px rgba(15,23,42,.05);
            }
            .pdv-top-title { font-size: 18px; font-weight: 900; color: #111827; line-height: 1.1; }
            .pdv-top-sub { font-size: 12px; color: #64748b; font-weight: 700; margin-top: 2px; }
            .pdv-search-wrap {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 16px;
                padding: 12px 14px 8px 14px;
                margin-bottom: 10px;
                box-shadow: 0 6px 18px rgba(15,23,42,.06);
            }
            .pdv-search-wrap .stTextInput input {
                min-height: 62px !important;
                font-size: 22px !important;
                font-weight: 800 !important;
                border: 2px solid #cbd5e1 !important;
                border-radius: 14px !important;
                background: #f8fafc !important;
                color: #0f172a !important;
            }
            .pdv-search-wrap .stTextInput input:focus {
                border-color: #2563eb !important;
                box-shadow: 0 0 0 3px rgba(37,99,235,.15) !important;
            }
            .pdv-card {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 16px;
                padding: 14px;
                box-shadow: 0 8px 22px rgba(15,23,42,.06);
            }
            .pdv-card-title {
                font-size: 13px; font-weight: 900; color: #475569;
                text-transform: uppercase; letter-spacing: .08em; margin-bottom: 10px;
            }
            .pdv-receipt {
                background: #fcfcfd;
                border: 1px dashed #cbd5e1;
                border-radius: 12px;
                padding: 8px 10px;
                max-height: 420px;
                overflow-y: auto;
            }
            .pdv-receipt table { width: 100%; border-collapse: collapse; font-size: 14px; }
            .pdv-receipt th {
                text-align: left; color: #64748b; font-size: 11px;
                text-transform: uppercase; letter-spacing: .06em;
                border-bottom: 1px solid #e2e8f0; padding: 6px 4px;
            }
            .pdv-receipt td {
                padding: 8px 4px; border-bottom: 1px solid #f1f5f9;
                color: #0f172a; font-weight: 700; vertical-align: top;
            }
            .pdv-receipt .pdv-line-sub { color: #059669; font-weight: 900; text-align: right; white-space: nowrap; }
            .pdv-receipt .pdv-line-qty { color: #334155; white-space: nowrap; }
            .pdv-pay-grid .stButton > button {
                min-height: 58px; font-size: 15px; font-weight: 800;
                border-radius: 12px; border: 1px solid #dbe3ec;
                background: #f8fafc; color: #0f172a;
            }
            .pdv-pay-pix .stButton > button { background: #ecfdf5 !important; border-color: #86efac !important; color: #065f46 !important; }
            .pdv-pay-card .stButton > button { background: #eff6ff !important; border-color: #93c5fd !important; color: #1e40af !important; }
            .pdv-pay-cash .stButton > button { background: #fffbeb !important; border-color: #fcd34d !important; color: #92400e !important; }
            .pdv-btn-main .stButton > button {
                min-height: 56px; font-size: 17px; font-weight: 900;
                border-radius: 14px; border: none;
                background: linear-gradient(135deg, #16a34a, #22c55e) !important;
                color: white !important;
            }
            .pdv-btn-ghost .stButton > button {
                min-height: 44px; font-weight: 800; border-radius: 12px;
                background: #ffffff !important; color: #334155 !important;
                border: 1px solid #d7dee8 !important;
            }
            .pdv-btn-danger .stButton > button {
                min-height: 44px; font-weight: 800; border-radius: 12px;
                background: #fff1f2 !important; color: #be123c !important;
                border: 1px solid #fecdd3 !important;
            }
            .pdv-chip {
                display: inline-block; background: #f1f5f9; border: 1px solid #e2e8f0;
                border-radius: 999px; padding: 6px 10px; margin: 0 6px 6px 0;
                font-size: 12px; font-weight: 800; color: #334155;
            }
            .pdv-prod-card {
                background: #ffffff;
                border: 1px solid #dbe3ec;
                border-radius: 14px;
                padding: 12px 14px;
                margin-bottom: 8px;
                box-shadow: 0 4px 14px rgba(15,23,42,.04);
            }
            .pdv-prod-code {
                display: inline-block;
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 12px;
                font-weight: 900;
                margin-right: 8px;
            }
            .pdv-prod-name { font-size: 16px; font-weight: 900; color: #0f172a; line-height: 1.2; }
            .pdv-prod-meta { font-size: 13px; color: #64748b; font-weight: 700; margin-top: 4px; }
            .pdv-prod-price { font-size: 15px; font-weight: 900; color: #059669; }
            .pdv-prod-stock { font-size: 13px; font-weight: 800; color: #475569; }
            .pdv-results-title {
                font-size: 13px; font-weight: 900; color: #475569;
                text-transform: uppercase; letter-spacing: .08em;
                margin: 4px 0 8px 0;
            }
            .pdv-footer-bar {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 14px;
                padding: 12px 16px;
                margin-top: 10px;
                box-shadow: 0 8px 22px rgba(15,23,42,.06);
            }
            .pdv-footer-grid {
                display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
            }
            .pdv-foot-label { font-size: 11px; color: #64748b; font-weight: 800; text-transform: uppercase; }
            .pdv-foot-value { font-size: 22px; color: #0f172a; font-weight: 900; margin-top: 2px; }
            .pdv-foot-value.total { color: #059669; font-size: 28px; }
            .pdv-foot-value.troco { color: #d97706; }
            .pdv-empty {
                text-align: center; color: #64748b; font-weight: 700;
                padding: 28px 12px; font-size: 14px;
            }
            .pdv-caixa-badge {
                display: inline-flex; align-items: center; gap: 8px;
                background: #ecfdf5; border: 1px solid #86efac; color: #065f46;
                border-radius: 999px; padding: 8px 14px; font-size: 13px; font-weight: 800;
            }
            .pdv-caixa-badge.fechado {
                background: #fff7ed; border-color: #fdba74; color: #9a3412;
            }
            .pdv-caixa-panel {
                background: #ffffff; border: 1px solid #d7dee8; border-radius: 16px;
                padding: 16px; box-shadow: 0 8px 22px rgba(15,23,42,.06); margin-bottom: 12px;
            }
            .pdv-caixa-kpi {
                background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
                padding: 12px 14px;
            }
            .pdv-caixa-kpi-label { font-size: 11px; color: #64748b; font-weight: 800; text-transform: uppercase; }
            .pdv-caixa-kpi-value { font-size: 20px; color: #0f172a; font-weight: 900; margin-top: 4px; }
            @media (max-width: 980px) {
                .pdv-footer-grid { grid-template-columns: repeat(2, 1fr); }
            }
        </style>
    """, unsafe_allow_html=True)

    caixa_ativo = caixa_aberto()
    resumo_caixa_ativo = resumo_caixa(caixa_ativo["id"]) if caixa_ativo else None

    pdv_aba = st.segmented_control(
        "Área do PDV",
        options=["🛒 Venda", "💰 Caixa"],
        default="🛒 Venda",
        key="pdv_aba",
    )

    if pdv_aba == "💰 Caixa":
        if caixa_ativo:
            rc = resumo_caixa_ativo
            st.markdown(
                f'<span class="pdv-caixa-badge">● Caixa #{caixa_ativo["id"]} ABERTO • '
                f'{caixa_ativo["data_abertura"]} {caixa_ativo["hora_abertura"]} • '
                f'{caixa_ativo["operador_abertura"]}</span>',
                unsafe_allow_html=True,
            )
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Vendas", rc["qtd_vendas"])
            k2.metric("Total vendido", moeda(rc["total_vendido"]))
            k3.metric("Ticket médio", moeda(rc["ticket_medio"]))
            k4.metric("Descontos", moeda(rc["total_descontos"]))

            st.markdown("#### Totais por forma de pagamento")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Dinheiro", moeda(rc["total_dinheiro"]))
            p2.metric("PIX", moeda(rc["total_pix"]))
            p3.metric("Crédito", moeda(rc["total_credito"]))
            p4.metric("Débito", moeda(rc["total_debito"]))

            st.markdown("#### Conferência de gaveta")
            g1, g2, g3 = st.columns(3)
            g1.metric("Valor inicial", moeda(rc["valor_inicial"]))
            g2.metric("Esperado em dinheiro", moeda(rc["valor_esperado_dinheiro"]))
            g3.metric("Troco concedido", moeda(rc["total_troco"]))

            if rc["qtd_cancelamentos"]:
                st.warning(f"Cancelamentos no turno: {rc['qtd_cancelamentos']}")
            if rc["nfce_pendencias"]:
                st.caption(f"NFC-e pendente em {rc['nfce_pendencias']} venda(s) — preparado para emissão futura.")

            with st.form("form_fechar_caixa", clear_on_submit=False):
                st.markdown("**Fechar caixa**")
                valor_contado = st.number_input(
                    "Valor contado em dinheiro (gaveta)",
                    min_value=0.0,
                    step=1.0,
                    value=float(rc["valor_esperado_dinheiro"]),
                )
                obs_fech = st.text_input("Observação de fechamento", placeholder="Opcional")
                fechar_ok = st.form_submit_button("Fechar caixa", type="primary", use_container_width=True)
                if fechar_ok:
                    try:
                        resumo_fech = fechar_caixa(
                            caixa_ativo["id"],
                            operador_nome,
                            valor_contado,
                            obs_fech,
                        )
                        diff = float(resumo_fech.get("diferenca_dinheiro") or 0)
                        if abs(diff) <= 0.009:
                            st.success(
                                f"Caixa #{caixa_ativo['id']} fechado • Conferência OK • "
                                f"Total vendido {moeda(resumo_fech['total_vendido'])}"
                            )
                        elif diff > 0:
                            st.success(
                                f"Caixa fechado • Sobra de {moeda(diff)} em dinheiro • "
                                f"Total vendido {moeda(resumo_fech['total_vendido'])}"
                            )
                        else:
                            st.warning(
                                f"Caixa fechado • Falta de {moeda(abs(diff))} em dinheiro • "
                                f"Total vendido {moeda(resumo_fech['total_vendido'])}"
                            )
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        else:
            st.markdown(
                '<span class="pdv-caixa-badge fechado">● Nenhum caixa aberto</span>',
                unsafe_allow_html=True,
            )
            st.markdown("#### Abrir caixa")
            st.caption("Informe o fundo de troco em dinheiro para iniciar o turno.")

            with st.form("form_abrir_caixa", clear_on_submit=False):
                valor_inicial = st.number_input(
                    "Valor inicial em dinheiro",
                    min_value=0.0,
                    step=10.0,
                    value=0.0,
                )
                obs_abertura = st.text_input("Observação", placeholder="Opcional")
                abrir_ok = st.form_submit_button("Abrir caixa", type="primary", use_container_width=True)
                if abrir_ok:
                    try:
                        novo_id = abrir_caixa(operador_nome, valor_inicial, obs_abertura)
                        st.success(f"Caixa #{novo_id} aberto com {moeda(valor_inicial)} em dinheiro.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    elif not caixa_ativo:
        if pdv_aba == "🛒 Venda":
            st.info("Abra o caixa em **💰 Caixa** para liberar vendas.")
            st.caption("Use o seletor acima para ir à abertura de caixa.")

    elif pdv_aba == "🛒 Venda" and resumo_caixa_ativo:
        st.caption(
            f"Caixa #{caixa_ativo['id']} • Vendas: {resumo_caixa_ativo['qtd_vendas']} • "
            f"Turno: {moeda(resumo_caixa_ativo['total_vendido'])} • Enter adiciona produto"
        )

    if pdv_aba == "🛒 Venda" and caixa_ativo:
        t1, t2, t3, t4 = st.columns([3.2, 1.2, 1, 1])
        with t1:
            st.markdown(f"""
                <div class="pdv-top">
                    <div class="pdv-top-title">Caixa • PDV Restaurante</div>
                    <div class="pdv-top-sub">Operador: {operador_nome} • PEPS + CMV automático</div>
                </div>
            """, unsafe_allow_html=True)
        with t2:
            st.button(
                "Cancelar venda",
                use_container_width=True,
                key="pdv_cancelar",
                on_click=pdv_on_cancelar_venda,
            )
        with t3:
            st.button(
                "Limpar busca",
                use_container_width=True,
                key="pdv_limpar_busca",
                on_click=pdv_on_limpar_busca,
            )
        with t4:
            if st.button("Sair", use_container_width=True, key="pdv_sair"):
                fazer_logout()

        with st.container(border=True):
            st.markdown("**Buscar produto** — nome, SKU ou código de barras • **Enter** confirma")
            st.text_input(
                "Buscar produto",
                placeholder="Digite ou escaneie...",
                key="pdv_busca",
                label_visibility="collapsed",
                on_change=pdv_on_busca_change,
            )
            b1, b2, b3 = st.columns([1, 1.2, 2.8])
            b1.number_input("Qtd", min_value=0.01, step=1.0, key="pdv_qtd_rapida")
            with b2:
                st.button(
                    "Adicionar",
                    use_container_width=True,
                    key="pdv_add_btn",
                    type="primary",
                    on_click=pdv_on_adicionar_click,
                )

        toast_msg = st.session_state.pop("_pdv_toast", None)
        if toast_msg:
            st.toast(toast_msg)

        aviso_add = st.session_state.pop("_pdv_add_warning", None)
        if aviso_add:
            st.warning(aviso_add)

        termo_busca = str(st.session_state.get("pdv_busca", "") or "").strip()
        resultados_pdv = buscar_produtos_catalogo(termo_busca, limite=12) if termo_busca else pd.DataFrame()

        if termo_busca:
            if resultados_pdv.empty:
                st.info("Nenhum produto encontrado.")
            else:
                st.markdown(
                    f'<div class="pdv-results-title">{len(resultados_pdv)} produto(s) encontrado(s)</div>',
                    unsafe_allow_html=True,
                )
                for idx, (_, prod) in enumerate(resultados_pdv.iterrows()):
                    codigo = prod.get("Código") or "-"
                    nome = prod.get("Nome") or ""
                    categoria = prod.get("Categoria") or "-"
                    preco = moeda(prod.get("Preço", 0))
                    estoque = float(prod.get("Estoque", 0) or 0)
                    unidade = prod.get("Unidade") or "UN"

                    with st.container(border=True):
                        c_info, c_meta, c_btn = st.columns([3.4, 2.2, 1], gap="small", vertical_alignment="center")
                        with c_info:
                            st.markdown(f"**[{codigo}]** {nome}")
                            st.caption(categoria)
                        with c_meta:
                            st.markdown(f"**Preço:** {preco}")
                            st.markdown(f"**Estoque:** {estoque:.2f} {unidade}")
                        with c_btn:
                            st.button(
                                "Adicionar",
                                key=f"pdv_pick_{prod['id']}_{idx}",
                                use_container_width=True,
                                type="primary",
                                on_click=pdv_on_pick_produto,
                                args=(int(prod["id"]),),
                            )

        col_cupom, col_pag = st.columns([1.45, 1], gap="medium")

        with col_cupom:
            st.markdown("### Pedido atual")

            if not carrinho:
                st.info("Nenhum item no pedido")
            else:
                if erros_preco_pdv:
                    st.error(
                        "Há produto(s) com preço não cadastrado. "
                        "Cadastre o preço em Produtos antes de finalizar a venda."
                    )

                for item in carrinho:
                    subtotal_item = pdv_item_subtotal(item)
                    sem_preco = float(item.get("preco_unitario", 0) or 0) <= 0.001

                    with st.container(border=True):
                        c_qtd, c_info, c_sub, c_del = st.columns(
                            [0.8, 3.6, 1.2, 0.5],
                            gap="small",
                            vertical_alignment="center",
                        )
                        with c_qtd:
                            st.markdown(f"**{item['quantidade']:.2f}**")
                            st.caption(item.get("unidade") or "UN")
                        with c_info:
                            codigo = item.get("codigo") or "-"
                            st.markdown(f"**[{codigo}]** {item.get('nome') or 'Produto'}")
                            if sem_preco:
                                st.warning("Preço não cadastrado")
                            else:
                                st.caption(f"Unitário: {moeda(item['preco_unitario'])}")
                        with c_sub:
                            st.markdown("**Subtotal**")
                            st.markdown(f"**{moeda(subtotal_item)}**")
                        with c_del:
                            st.button(
                                "✕",
                                key=f"pdv_del_{item['uid']}",
                                use_container_width=True,
                                on_click=pdv_on_remover_item,
                                args=(item["uid"],),
                            )

        with col_pag:
            st.markdown("### Pagamento")

            st.number_input(
                "Desconto (R$)",
                min_value=0.0,
                step=1.0,
                key="pdv_desconto",
                on_change=pdv_on_desconto_change,
            )
            resumo = pdv_resumo_atual()

            st.caption(f"Restante: **{moeda(resumo['falta'])}** • Pago: **{moeda(resumo['pago'])}**")

            st.markdown("**Forma de pagamento**")
            forma_sel = st.radio(
                "Forma",
                PDV_FORMAS_PAGAMENTO,
                horizontal=True,
                key="pdv_forma_sel",
                label_visibility="collapsed",
            )

            st.number_input("Valor do pagamento", min_value=0.0, step=1.0, key="pdv_valor_pg")

            valor_restante = resumo["falta"] if resumo["falta"] > 0.009 else resumo["total"]
            p1, p2 = st.columns(2)
            with p1:
                st.button(
                    "PIX",
                    use_container_width=True,
                    key="pdv_quick_pix",
                    on_click=pdv_on_quick_pagamento,
                    args=("PIX", valor_restante),
                )
                st.button(
                    "Débito",
                    use_container_width=True,
                    key="pdv_quick_deb",
                    on_click=pdv_on_quick_pagamento,
                    args=("Débito", valor_restante),
                )
            with p2:
                st.button(
                    "Crédito",
                    use_container_width=True,
                    key="pdv_quick_cred",
                    on_click=pdv_on_quick_pagamento,
                    args=("Crédito", valor_restante),
                )
                st.button(
                    "Dinheiro",
                    use_container_width=True,
                    key="pdv_quick_cash",
                    on_click=pdv_on_quick_pagamento,
                    args=("Dinheiro", valor_restante),
                )

            st.button(
                "Adicionar pagamento",
                use_container_width=True,
                key="pdv_add_pg",
                on_click=pdv_on_adicionar_pagamento,
            )

            if pagamentos:
                for pg in pagamentos:
                    c_pg, c_pg_del = st.columns([5, 1])
                    with c_pg:
                        st.markdown(
                            f"<span class='pdv-chip'>{pg['forma']} • {moeda(pg['valor'])}</span>",
                            unsafe_allow_html=True,
                        )
                    with c_pg_del:
                        st.button(
                            "✕",
                            key=f"pdv_pg_del_{pg['uid']}",
                            on_click=pdv_on_remover_pagamento,
                            args=(pg["uid"],),
                        )

            if resumo["troco"] > 0.009:
                st.success(f"Troco: {moeda(resumo['troco'])}")

            if erros_preco_pdv:
                st.button(
                    "Finalizar venda",
                    use_container_width=True,
                    key="pdv_finalizar",
                    disabled=True,
                    help="Cadastre o preço de todos os produtos antes de finalizar.",
                )
            else:
                st.button(
                    "Finalizar venda",
                    use_container_width=True,
                    key="pdv_finalizar",
                    type="primary",
                    on_click=pdv_on_finalizar_venda,
                    args=(operador_nome,),
                )

        resumo = pdv_resumo_atual()
        foot1, foot2, foot3, foot4 = st.columns(4)
        with foot1:
            st.metric("Subtotal", moeda(resumo["subtotal"]))
        with foot2:
            st.metric("Desconto", moeda(resumo["desconto"]))
        with foot3:
            st.metric("Total", moeda(resumo["total"]))
        with foot4:
            st.metric("Troco", moeda(resumo["troco"]))


    # =========================================================
# SAÍDA / VENDA / PERDA
# =========================================================
elif menu == "Lançar Saída":
    st.subheader("Saída / Venda / Perda — PEPS")
    st.caption("Venda gera receita. Perda, consumo interno, produção e ajuste baixam estoque e entram no CMV operacional, mas sem receita.")

    op = dict(zip(pdf["nome"], pdf["id"]))
    prec = dict(zip(pdf["nome"], pdf["preco_venda"]))

    with st.form("sai"):
        dt = st.date_input("Data", date.today())
        prod = st.selectbox("Produto", list(op))
        tipo_saida = st.selectbox("Tipo de saída", ["Venda", "Perda", "Consumo Interno", "Produção", "Ajuste Inventário"])
        qtd = st.number_input("Quantidade", min_value=0.01, step=1.0)

        motivo = ""
        preco = 0.0

        if tipo_saida == "Venda":
            preco = st.number_input(
                "Valor unitário de venda",
                min_value=0.0,
                step=0.5,
                value=float(prec.get(prod, 0) or 0)
            )

            st.write(f"Receita desta venda: **{moeda(qtd * preco)}**")

        else:
            motivo = st.selectbox("Motivo", ["Vencimento", "Quebra", "Queimou", "Erro de produção", "Degustação", "Funcionário", "Contagem/Inventário", "Outro"])
            st.info("Essa saída não gera receita, mas entra como custo/perda no CMV operacional.")

        obs = st.text_area("Observação")
        ok = st.form_submit_button("Lançar saída")

        if ok:
            try:
                saida_peps(op[prod], dt, qtd, preco, tipo_saida, motivo, obs)
                st.success("Saída lançada e CMV calculado.")
            except Exception as e:
                st.error(str(e))


# =========================================================
# ESTOQUE / LOTES / MOVIMENTAÇÕES
# =========================================================
elif menu == "Estoque Atual":
    st.dataframe(estoque_df().drop(columns=["id"]), use_container_width=True)

elif menu == "Lotes":
    st.dataframe(lotes_df(), use_container_width=True)

elif menu == "Movimentações":
    st.dataframe(mov_df(), use_container_width=True)


# =========================================================
# RELATÓRIO VENDAS PDV
# =========================================================
elif menu == "Relatório Vendas PDV":
    st.subheader("Relatório de Vendas PDV")
    st.caption("Análise rápida por período, operador e forma de pagamento.")

    hoje = date.today()
    c1, c2, c3, c4 = st.columns(4)
    data_ini = c1.date_input("Data inicial", hoje.replace(day=1), key="rel_pdv_ini")
    data_fim = c2.date_input("Data final", hoje, key="rel_pdv_fim")

    c = conn()
    operadores_df = pd.read_sql_query("""
        SELECT DISTINCT operador
        FROM pdv_vendas
        WHERE operador IS NOT NULL AND TRIM(operador) != ''
        ORDER BY operador
    """, c)
    c.close()
    opcoes_operador = ["Todos"] + operadores_df["operador"].tolist()
    operador_filtro = c3.selectbox("Operador", opcoes_operador, key="rel_pdv_operador")
    forma_filtro = c4.selectbox(
        "Forma de pagamento",
        ["Todas"] + PDV_FORMAS_PAGAMENTO,
        key="rel_pdv_forma",
    )

    rel = relatorio_vendas_pdv(
        data_ini,
        data_fim,
        operador="" if operador_filtro == "Todos" else operador_filtro,
        forma="" if forma_filtro == "Todas" else forma_filtro,
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Vendas", rel["qtd_vendas"])
    m2.metric("Total geral", moeda(rel["total_geral"]))
    m3.metric("Ticket médio", moeda(rel["ticket_medio"]))
    m4.metric("Descontos", moeda(rel["total_descontos"]))
    m5.metric("Período", f"{data_ini.strftime('%d/%m')} → {data_fim.strftime('%d/%m')}")

    st.markdown("#### Totais por forma de pagamento")
    f1, f2, f3, f4 = st.columns(4)
    totais = rel.get("totais_forma", {})
    f1.metric("Dinheiro", moeda(totais.get("Dinheiro", 0)))
    f2.metric("PIX", moeda(totais.get("PIX", 0)))
    f3.metric("Crédito", moeda(totais.get("Crédito", 0)))
    f4.metric("Débito", moeda(totais.get("Débito", 0)))

    vendas_df = rel["vendas"]
    if vendas_df.empty:
        st.info("Nenhuma venda encontrada para os filtros selecionados.")
    else:
        exibir = vendas_df.copy()
        exibir["subtotal"] = exibir["subtotal"].apply(moeda)
        exibir["desconto"] = exibir["desconto"].apply(moeda)
        exibir["total"] = exibir["total"].apply(moeda)
        exibir["troco"] = exibir["troco"].apply(moeda)
        st.dataframe(
            exibir.rename(columns={
                "venda_id": "Venda",
                "data": "Data",
                "hora": "Hora",
                "operador": "Operador",
                "caixa_id": "Caixa",
                "subtotal": "Subtotal",
                "desconto": "Desconto",
                "total": "Total",
                "troco": "Troco",
                "status": "Status",
                "nfce_status": "NFC-e",
            }),
            use_container_width=True,
            hide_index=True,
        )

        if not rel["pagamentos"].empty:
            with st.expander("Detalhe de pagamentos"):
                pag = rel["pagamentos"].copy()
                pag["valor"] = pag["valor"].apply(moeda)
                pag["troco"] = pag["troco"].apply(moeda)
                st.dataframe(pag, use_container_width=True, hide_index=True)


# =========================================================
# EXPORTAR
# =========================================================
elif menu == "Exportar":
    arquivo = "relatorio_estoque_peps_cmv.xlsx"

    estoque = estoque_df()
    movimentacoes = mov_df()
    lotes = lotes_df()
    resumo = resumo_cmv(date.today().year, date.today().month)

    with pd.ExcelWriter(arquivo, engine="openpyxl") as w:
        pd.DataFrame({
            "Sistema": ["Estoque Restaurante PEPS + CMV + Perdas + OCR"],
            "Data": [str(date.today())],
            "Observação": ["Relatório gerado automaticamente"]
        }).to_excel(w, sheet_name="Resumo", index=False)

        estoque.to_excel(w, sheet_name="Estoque Atual", index=False)

        if not movimentacoes.empty:
            movimentacoes.to_excel(w, sheet_name="Movimentações", index=False)

        if not lotes.empty:
            lotes.to_excel(w, sheet_name="Lotes", index=False)

        if not resumo.empty:
            resumo.to_excel(w, sheet_name="CMV Mês Atual", index=False)

        despesas_export = despesas_df()
        if not despesas_export.empty:
            despesas_export.to_excel(w, sheet_name="Despesas", index=False)

    with open(arquivo, "rb") as f:
        st.download_button(
            "Baixar relatório Excel",
            f,
            "relatorio_estoque_peps_cmv.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
