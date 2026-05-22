
import sqlite3
from pathlib import Path
from datetime import date
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
from PIL import Image
import re
import json

DB_PATH = Path("estoque_restaurante.db")
META_CMV = 36.0

st.set_page_config(page_title="Estoque Restaurante | PEPS + CMV", layout="wide")


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

# =========================================================
# DASHBOARD PREMIUM
# =========================================================
def metric_card(label, value, help_text="", tone="default"):
    colors = {
        "default": "#0f172a",
        "good": "#166534",
        "warn": "#92400e",
        "bad": "#991b1b",
        "blue": "#1d4ed8",
        "purple": "#6d28d9",
    }
    color = colors.get(tone, colors["default"])
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e5e7eb;
            border-left: 5px solid {color};
            border-radius: 18px;
            padding: 18px 18px;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
            min-height: 122px;">
            <div style="font-size: 13px; color: #64748b; font-weight: 600; margin-bottom: 8px;">
                {label}
            </div>
            <div style="font-size: 27px; color: #0f172a; font-weight: 800; line-height: 1.1;">
                {value}
            </div>
            <div style="font-size: 12px; color: #64748b; margin-top: 8px;">
                {help_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


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

    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Receita"] = pd.to_numeric(df["Receita"], errors="coerce").fillna(0)
    df["CMV"] = pd.to_numeric(df["CMV"], errors="coerce").fillna(0)
    df["Quantidade"] = pd.to_numeric(df["Quantidade"], errors="coerce").fillna(0)
    return df


def format_pct(v):
    return f"{float(v):.2f}%".replace(".", ",")


def alerta_box(texto, tipo="warn"):
    cores = {
        "warn": ("#fffbeb", "#f59e0b", "#92400e"),
        "bad": ("#fef2f2", "#ef4444", "#991b1b"),
        "good": ("#f0fdf4", "#22c55e", "#166534"),
        "info": ("#eff6ff", "#3b82f6", "#1d4ed8"),
    }
    bg, border, color = cores.get(tipo, cores["warn"])
    st.markdown(
        f"""
        <div style="
            background:{bg};
            border-left:5px solid {border};
            color:{color};
            padding:12px 14px;
            border-radius:12px;
            margin-bottom:8px;
            font-size:14px;
            font-weight:600;">
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
        "Precificação",
        "DRE Gerencial",
        "Curva ABC",
        "Produtos",
        "Configurações",
        "Usuários",
        "Importar Nota",
        "Importar Cupom Foto",
        "Entrada Manual",
        "Saída PEPS",
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
        "Saída PEPS",
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

st.title("📦 Sistema de Estoque Restaurante — PEPS + CMV")
st.caption("Controle permitido: PEPS + CMV mensal. Meta ideal configurada: 36%.")

menus_permitidos = menus_por_perfil()
menu = st.sidebar.radio("Menu", menus_permitidos)
logout_sidebar()

pdf = produtos_df()


# =========================================================
# PAINEL CMV
# =========================================================
if menu == "Painel CMV":
    st.markdown("""
        <style>
            .block-container {padding-top: 1.4rem;}
            [data-testid="stMetricValue"] {font-size: 26px;}
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

            st.line_chart(diario_resumo.set_index("Dia")[["Receita", "CMV"]])
            st.caption("Evolução de receita e CMV em R$.")

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
                prod["CMV %"] = prod.apply(lambda r: (r["CMV"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)
                prod["Margem %"] = prod.apply(lambda r: (r["Lucro Bruto"] / r["Receita"] * 100) if r["Receita"] else 0, axis=1)

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**🏆 Mais vendidos**")
                    st.dataframe(prod.sort_values("Quantidade", ascending=False).head(10), use_container_width=True, hide_index=True)
                with col_b:
                    st.markdown("**💎 Mais lucrativos**")
                    st.dataframe(prod.sort_values("Lucro Bruto", ascending=False).head(10), use_container_width=True, hide_index=True)

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
        st.dataframe(base, use_container_width=True, hide_index=True)



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

    st.markdown(f"### Resultado do período • {label}")

    c1, c2, c3, c4, c5 = st.columns(5)

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

        salvar = st.form_submit_button("Salvar configurações")

        if salvar:
            set_config("nome_empresa", nome_empresa)
            set_config("categoria_negocio", categoria_negocio)
            set_config("meta_cmv_ideal", meta_ideal)
            set_config("meta_cmv_alerta", meta_alerta)
            set_config("meta_cmv_critica", meta_critica)
            st.success("Configurações salvas com sucesso.")

    st.info("Exemplo: se sua cafeteria trabalha com CMV ideal de 30%, coloque 30%. O dashboard passa a usar essa meta automaticamente.")
    st.markdown("### Parâmetros atuais")
    st.write(f"**Empresa:** {get_config('nome_empresa', 'Restaurante')}")
    st.write(f"**Meta CMV ideal:** {format_pct(get_float_config('meta_cmv_ideal', META_CMV))}")
    st.write(f"**Atenção:** {format_pct(get_float_config('meta_cmv_alerta', META_CMV + 4))}")
    st.write(f"**Crítico:** {format_pct(get_float_config('meta_cmv_critica', META_CMV + 8))}")


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
