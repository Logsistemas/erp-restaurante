from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import numpy as np

DB_PATH = Path("estoque_restaurante.db")
META_CMV = 36.0

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def num(v):
    try:
        return float(v or 0)
    except:
        return 0.0


def resumo_periodo(inicio, fim):
    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT
            COALESCE(SUM(CASE 
                WHEN COALESCE(NULLIF(tipo_saida,''),'Venda') = 'Venda' 
                THEN receita_venda ELSE 0 END), 0) AS receita,

            COALESCE(SUM(CASE 
                WHEN COALESCE(NULLIF(tipo_saida,''),'Venda') = 'Venda' 
                THEN cmv_peps ELSE 0 END), 0) AS cmv_venda,

            COALESCE(SUM(CASE 
                WHEN COALESCE(NULLIF(tipo_saida,''),'Venda') <> 'Venda' 
                THEN cmv_peps ELSE 0 END), 0) AS perdas,

            COALESCE(SUM(CASE 
                WHEN COALESCE(NULLIF(tipo_saida,''),'Venda') = 'Venda' 
                THEN quantidade ELSE 0 END), 0) AS qtd
        FROM movimentacoes
        WHERE tipo = 'Saída'
          AND date(data) >= date(?)
          AND date(data) < date(?)
    """, (inicio, fim))

    r = cur.fetchone()
    c.close()

    receita = num(r["receita"])
    cmv_venda = num(r["cmv_venda"])
    perdas = num(r["perdas"])
    qtd = num(r["qtd"])

    cmv_total = cmv_venda + perdas
    lucro = receita - cmv_total
    cmv_pct = (cmv_total / receita * 100) if receita else 0
    ticket = (receita / qtd) if qtd else 0

    return {
        "receita": receita,
        "lucro": lucro,
        "cmv_pct": cmv_pct,
        "ticket": ticket,
        "cmv_total": cmv_total,
        "perdas": perdas,
        "qtd": qtd,
    }


def estoque_critico():
    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT
            p.nome AS produto,
            COALESCE(SUM(l.qtd_restante), 0) AS qtd_atual,
            COALESCE(p.estoque_minimo, 0) AS minimo
        FROM produtos p
        LEFT JOIN lotes l 
            ON l.produto_id = p.id 
            AND l.qtd_restante > 0
        WHERE p.ativo = 1
        GROUP BY p.id, p.nome, p.estoque_minimo
        HAVING qtd_atual <= minimo
        ORDER BY qtd_atual ASC
    """)

    itens = [
        {
            "produto": row["produto"],
            "qtd_atual": round(num(row["qtd_atual"]), 2),
            "minimo": round(num(row["minimo"]), 2),
        }
        for row in cur.fetchall()
    ]

    c.close()
    return itens


def valor_estoque():
    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT COALESCE(SUM(qtd_restante * valor_unitario), 0) AS total
        FROM lotes
        WHERE qtd_restante > 0
    """)

    total = num(cur.fetchone()["total"])
    c.close()
    return total


def produtos_destaque(inicio, fim):
    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT
            p.nome AS nome,
            COALESCE(SUM(m.quantidade), 0) AS quantidade,
            COALESCE(SUM(m.receita_venda), 0) AS receita,
            COALESCE(SUM(m.cmv_peps), 0) AS cmv,
            COALESCE(SUM(m.receita_venda - m.cmv_peps), 0) AS lucro
        FROM movimentacoes m
        JOIN produtos p ON p.id = m.produto_id
        WHERE m.tipo = 'Saída'
          AND COALESCE(NULLIF(m.tipo_saida,''),'Venda') = 'Venda'
          AND date(m.data) >= date(?)
          AND date(m.data) < date(?)
        GROUP BY p.id, p.nome
    """, (inicio, fim))

    produtos = []

    for row in cur.fetchall():
        receita = num(row["receita"])
        cmv = num(row["cmv"])
        lucro = num(row["lucro"])
        quantidade = num(row["quantidade"])

        cmv_pct = (cmv / receita * 100) if receita else 0
        margem_pct = (lucro / receita * 100) if receita else 0

        produtos.append({
            "nome": row["nome"],
            "quantidade": round(quantidade, 2),
            "receita": round(receita, 2),
            "cmv_valor": round(cmv, 2),
            "cmv": round(cmv_pct, 2),
            "lucro": round(lucro, 2),
            "margem": round(margem_pct, 2),
        })

    c.close()

    mais_vendidos = sorted(produtos, key=lambda x: x["quantidade"], reverse=True)[:10]
    mais_lucrativos = sorted(produtos, key=lambda x: x["lucro"], reverse=True)[:10]
    pior_margem = sorted(produtos, key=lambda x: x["margem"])[:10]
    cmv_alto = sorted(produtos, key=lambda x: x["cmv"], reverse=True)[:10]

    promocao = [
        p for p in produtos
        if p["margem"] >= 60 and p["quantidade"] > 0
    ]
    promocao = sorted(promocao, key=lambda x: x["margem"], reverse=True)[:10]

    return {
        "mais_vendidos": mais_vendidos,
        "mais_lucrativos": mais_lucrativos,
        "pior_margem": pior_margem,
        "cmv_alto": cmv_alto,
        "promocao": promocao,
    }
    return {
        "mais_vendidos": mais_vendidos,
        "mais_lucrativos": mais_lucrativos,
        "pior_margem": pior_margem,
        "cmv_alto": cmv_alto,
        "promocao": promocao
    }


def grafico_ultimos_7_dias():
    hoje = date.today()
    inicio = hoje - timedelta(days=6)

    c = conn()
    cur = c.cursor()

    cur.execute("""
        SELECT
            date(data) AS dia,
            COALESCE(SUM(receita_venda), 0) AS receita,
            COALESCE(SUM(cmv_peps), 0) AS cmv
        FROM movimentacoes
        WHERE tipo = 'Saída'
          AND COALESCE(NULLIF(tipo_saida,''),'Venda') = 'Venda'
          AND date(data) >= date(?)
          AND date(data) < date(?)
        GROUP BY date(data)
    """, (str(inicio), str(hoje + timedelta(days=1))))

    por_dia = {row["dia"]: row for row in cur.fetchall()}
    c.close()

    labels = []
    receitas = []
    lucros = []

    nomes = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    for i in range(7):
        d = inicio + timedelta(days=i)
        chave = str(d)
        labels.append(nomes[d.weekday()])

        row = por_dia.get(chave)
        receita = num(row["receita"]) if row else 0
        cmv = num(row["cmv"]) if row else 0

        receitas.append(round(receita, 2))
        lucros.append(round(receita - cmv, 2))

    return {
        "labels": labels,
        "receita": receitas,
        "lucro": lucros,
    }


def calcular_score(cmv_mes, lucro_mes, estoque_critico_qtd, perdas_mes):
    score = 100

    if cmv_mes > META_CMV:
        score -= int((cmv_mes - META_CMV) * 2)

    if lucro_mes < 0:
        score -= 30

    score -= estoque_critico_qtd * 5

    if perdas_mes > 0:
        score -= 5

    return max(0, min(100, score))


@app.get("/dashboard")
def dashboard():
    hoje = date.today()

    inicio_hoje = str(hoje)
    fim_hoje = str(hoje + timedelta(days=1))

    inicio_mes = str(date(hoje.year, hoje.month, 1))
    if hoje.month == 12:
        fim_mes = str(date(hoje.year + 1, 1, 1))
        dias_no_mes = 31
    else:
        fim_mes_date = date(hoje.year, hoje.month + 1, 1)
        fim_mes = str(fim_mes_date)
        dias_no_mes = (fim_mes_date - date(hoje.year, hoje.month, 1)).days

    hoje_resumo = resumo_periodo(inicio_hoje, fim_hoje)
    mes_resumo = resumo_periodo(inicio_mes, fim_mes)

    estoque_itens = estoque_critico()
    estoque_qtd = len(estoque_itens)
    estoque_valor = valor_estoque()

    score = calcular_score(
        mes_resumo["cmv_pct"],
        mes_resumo["lucro"],
        estoque_qtd,
        mes_resumo["perdas"],
    )

    dia_atual = max(1, hoje.day)
    fator = dias_no_mes / dia_atual

    receita_proj = mes_resumo["receita"] * fator
    lucro_proj = mes_resumo["lucro"] * fator
    cmv_proj = mes_resumo["cmv_pct"]

    alertas = []

    acoes_hoje = []

    if score >= 80:
        alertas.append({
            "tipo": "sucesso",
            "titulo": "Saúde da loja saudável",
            "mensagem": f"Score operacional em {score}/100. Operação equilibrada.",
        })
    elif score >= 50:
        alertas.append({
            "tipo": "alerta",
            "titulo": "Saúde da loja em atenção",
            "mensagem": f"Score {score}/100. A loja ainda opera, mas existem pontos que podem virar prejuízo.",
        })
    else:
        alertas.append({
            "tipo": "critico",
            "titulo": "Saúde da loja crítica",
            "mensagem": f"Score operacional muito baixo ({score}/100). Revisão urgente necessária.",
        })

    if mes_resumo["cmv_pct"] > META_CMV:
        alertas.append({
            "tipo": "alerta",
            "titulo": "CMV acima da meta",
            "mensagem": f"{mes_resumo['cmv_pct']:.2f}% está {(mes_resumo['cmv_pct'] - META_CMV):.2f}% acima da meta mensal.",
        })

    if mes_resumo["perdas"] > 0:
        alertas.append({
            "tipo": "alerta",
            "titulo": "Perdas em atenção",
            "mensagem": f"Impacto de {((mes_resumo['perdas'] / mes_resumo['receita']) * 100) if mes_resumo['receita'] else 0:.2f}% da receita no período.",
        })

    if estoque_qtd > 0:
        alertas.append({
            "tipo": "alerta",
            "titulo": "Risco de ruptura",
            "mensagem": f"{estoque_qtd} produto(s) em estoque crítico.",
        })

    
        alertas.append({
        "tipo": "critico",
        "titulo": "Prejuízo operacional",
        "mensagem": "O DRE do período está negativo depois de CMV e despesas.",
    })

    if mes_resumo["cmv_pct"] > META_CMV:
        acoes_hoje.append({
            "titulo": "Atacar os vilões do CMV",
            "descricao": "Abra a aba 'CMV alto' e revise os produtos que estão puxando o percentual para cima.",
        })

    if mes_resumo["perdas"] > 0:
        acoes_hoje.append({
            "titulo": "Monitorar perdas",
            "descricao": "Acompanhe diariamente se o valor de perdas continua subindo ou foi um evento pontual.",
        })

    if estoque_qtd > 0:
        acoes_hoje.append({
            "titulo": "Comprar antes de perder venda",
            "descricao": "Priorize os itens críticos com maior saída e maior margem.",
        })

    
        acoes_hoje.append({
        "titulo": "Revisar resultado",
        "descricao": "Separe o problema entre preço, CMV e despesas. Se o lucro bruto existe mas some no final, olhe despesas.",
    })

        acoes_hoje.append({
            "titulo": "Reforçar produtos lucrativos",
            "descricao": "Promova os produtos com maior margem usando combos, vitrine e sugestão ativa.",
        })

    if produtos_destaque(inicio_mes, fim_mes)["promocao"]:
        primeiro_promo = produtos_destaque(inicio_mes, fim_mes)["promocao"][0]["nome"]
        acoes_hoje.append({
            "titulo": "Promover produto saudável",
            "descricao": f"{primeiro_promo} tem boa margem e pode entrar em combo, destaque de vitrine ou sugestão ativa.",
        })

        produtos = produtos_destaque(inicio_mes, fim_mes)
        grafico = grafico_ultimos_7_dias()

        saude_texto = (
            "Saudável" if score >= 80 else
            "Atenção" if score >= 50 else
            "Crítica"
        )

        leituras_score = [
            f"CMV mensal: {mes_resumo['cmv_pct']:.2f}%",
            f"Lucro mensal: R$ {mes_resumo['lucro']:.2f}",
            f"Estoque crítico: {estoque_qtd} item(ns)",
            f"Perdas no mês: R$ {mes_resumo['perdas']:.2f}",
        ]

        motor_inteligencia = [
            {
                "titulo": "Leitura de margem",
                "texto": (
                    "CMV dentro da meta operacional."
                    if mes_resumo["cmv_pct"] <= META_CMV
                    else "CMV acima da meta. Revisar custos e desperdícios."
                ),
            },
            {
                "titulo": "Leitura de estoque",
                "texto": (
                    "Estoque crítico vazio."
                    if estoque_qtd == 0
                    else f"{estoque_qtd} produto(s) precisam de atenção."
                ),
            },
            {
                "titulo": "Leitura de resultado",
                "texto": (
                    "Resultado operacional positivo no mês."
                    if mes_resumo["lucro"] >= 0
                    else "Resultado negativo. Avaliar CMV, perdas e despesas."
                ),
            },
        ]

        ia = (
            f"Hoje sua loja faturou R$ {hoje_resumo['receita']:.2f}, "
            f"com lucro bruto de R$ {hoje_resumo['lucro']:.2f}. "
            + (
                "✅ O CMV está saudável. "
                if mes_resumo["cmv_pct"] <= META_CMV
                else "⚠️ O CMV está acima da meta ideal. "
            )
            + (
                "📈 Ticket médio excelente hoje. "
                if hoje_resumo["ticket"] >= 20
                else "📌 Ticket médio pode melhorar com combos e adicionais. "
            )
            + (
                f"🚨 Existem {estoque_qtd} produto(s) em estoque crítico. "
                if estoque_qtd > 0
                else "✅ Estoque sob controle. "
            )
            + f"Previsão de faturamento mensal: R$ {receita_proj:.2f}."
        )

    return {
        "score": score,
        "saude_loja": {
            "status": saude_texto,
            "leituras": leituras_score,
        },
        "hoje": {
            "receita": round(hoje_resumo["receita"], 2),
            "lucro": round(hoje_resumo["lucro"], 2),
            "cmv": round(hoje_resumo["cmv_pct"], 2),
            "ticket_medio": round(hoje_resumo["ticket"], 2),
            "perdas": round(hoje_resumo["perdas"], 2),
        },
        "mes": {
            "receita": round(mes_resumo["receita"], 2),
            "lucro": round(mes_resumo["lucro"], 2),
            "cmv": round(mes_resumo["cmv_pct"], 2),
            "perdas": round(mes_resumo["perdas"], 2),
            "valor_estoque": round(estoque_valor, 2),
            "estoque_critico_qtd": estoque_qtd,
        },
        "alertas": alertas,
        "acoes_hoje": acoes_hoje,
        "motor_inteligencia": motor_inteligencia,
        "projecao": {
            "receita_final_mes": round(receita_proj, 2),
            "lucro_final_mes": round(lucro_proj, 2),
            "cmv_final_mes": round(cmv_proj, 2),
            "resumo": (
                "O mês tende a fechar saudável."
                if score >= 80
                else "O mês tende a fechar com pontos de atenção."
            ),
        },
        "produtos_destaque": produtos,
        "estoque_critico": estoque_itens[:8],
        "grafico_7_dias": grafico,
        "ia": ia,
    }


class LoginData(BaseModel):
    email: str
    senha: str


@app.post("/login")
def login(data: LoginData):
    if data.email == "admin@erp.com" and data.senha == "123456":
        return {
            "success": True,
            "token": "abc123",
            "usuario": "Ezequiel"
        }

    return {
        "success": False
    }