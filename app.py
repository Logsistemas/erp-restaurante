
import sqlite3
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
            observacao TEXT
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

    c.commit()
    c.close()


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


# =========================================================
# FUNÇÕES BASE
# =========================================================
def produtos_df():
    c = conn()
    df = pd.read_sql_query("SELECT * FROM produtos WHERE ativo=1 ORDER BY nome", c)
    c.close()
    return df


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


def saida_peps(pid, data_mov, qtd, preco_venda=0, tipo_saida="Venda", motivo_saida="", obs=""):
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
         cmv_peps, custo_medio_atual, tipo_saida, motivo_saida, observacao)
        VALUES (?, ?, 'Saída', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(data_mov), pid, qtd, preco_venda, valor_total, receita,
        cmv, cm, tipo_saida, motivo_saida, obs
    ))

    c.commit()
    c.close()


# =========================================================
# RELATÓRIOS
# =========================================================
def estoque_df():
    c = conn()

    df = pd.read_sql_query("""
        SELECT 
            p.id,
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
        ORDER BY p.nome
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
        ORDER BY p.nome, date(l.data_entrada), l.id
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
# DRE GERENCIAL
# =========================================================
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
                observacao Observação
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
                observacao Observação
            FROM despesas
            ORDER BY date(data) DESC, id DESC
        """, c)

    c.close()
    return df


def inserir_despesa(data_mov, categoria, descricao, valor, observacao=""):
    c = conn()
    cur = c.cursor()

    cur.execute("""
        INSERT INTO despesas (data, categoria, descricao, valor, observacao)
        VALUES (?, ?, ?, ?, ?)
    """, (str(data_mov), categoria, descricao, float(valor), observacao))

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


def usuario_logado():
    return st.session_state.get("usuario_logado")


def exigir_login():
    if usuario_logado():
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
                st.session_state["usuario_logado"] = user
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
        "Curva ABC",
        "Produtos",
        "Configurações",
        "Usuários",
        "Importar Nota",
        "Importar Cupom Foto",
        "Entrada Manual",
        "Lançar Saída",
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
            "Curva ABC",
            "Estoque Atual",
            "Movimentações",
            "Exportar"
        ]

    # operador
    return [
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
        st.session_state.pop("usuario_logado", None)
        st.rerun()


# =========================================================
# APP
# =========================================================
init_db()
seed()
garantir_usuarios_json()
exigir_login()
user = st.session_state.get("usuario_logado", {})

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

menus_permitidos = menus_por_perfil()
menu = st.radio(
    "Navegação",
    menus_permitidos,
    horizontal=True
)
# logout_sidebar()

col_user, col_sair = st.columns([8, 1])

with col_user:
    st.caption(f"👤 {user.get('nome', user.get('usuario'))} | Perfil: {user.get('tipo', '-')}")
with col_sair:
    if st.button("Sair"):
        st.session_state.pop("usuario_logado", None)
        st.rerun()

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
                ["Aluguel", "Funcionários", "Energia", "Água", "Internet", "Contador", "Taxas/Cartões", "iFood/Delivery", "Marketing", "Manutenção", "Embalagens", "Outros"]
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
            st.bar_chart(desp_cat.set_index("Categoria"))
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
    st.subheader("Cadastrar Produto")

    with st.form("prod"):
        nome = st.text_input("Nome")
        cat = st.text_input("Categoria")
        un = st.selectbox("Unidade", ["UN", "KG", "G", "L", "ML", "CX"])
        minimo = st.number_input("Estoque mínimo", min_value=0.0, step=1.0)
        preco = st.number_input("Preço de venda padrão", min_value=0.0, step=0.5)
        ok = st.form_submit_button("Salvar")

        if ok:
            c = conn()
            cur = c.cursor()

            try:
                cur.execute("""
                    INSERT INTO produtos 
                    (nome, categoria, unidade, estoque_minimo, preco_venda)
                    VALUES (?, ?, ?, ?, ?)
                """, (nome, cat, un, minimo, preco))

                c.commit()
                st.success("Produto cadastrado.")

            except Exception as e:
                st.warning(f"Não salvei: {e}")

            c.close()

    st.dataframe(produtos_df().drop(columns=["ativo"]), use_container_width=True)



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
