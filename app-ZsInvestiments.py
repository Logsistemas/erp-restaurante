import sqlite3
from pathlib import Path
from datetime import date
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st

DB_PATH = Path('estoque_restaurante.db')
META_CMV = 36.0
st.set_page_config(page_title='Estoque Restaurante | PEPS + CMV', layout='wide')

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c=conn(); cur=c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE NOT NULL, categoria TEXT,
        unidade TEXT DEFAULT 'UN', estoque_minimo REAL DEFAULT 0, preco_venda REAL DEFAULT 0, ativo INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS lotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER NOT NULL, data_entrada TEXT NOT NULL,
        qtd_inicial REAL NOT NULL, qtd_restante REAL NOT NULL, valor_unitario REAL NOT NULL,
        fornecedor TEXT, chave_nfe TEXT, observacao TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS movimentacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, produto_id INTEGER NOT NULL, tipo TEXT NOT NULL,
        quantidade REAL NOT NULL, valor_unitario REAL, valor_total REAL, receita_venda REAL DEFAULT 0,
        cmv_peps REAL DEFAULT 0, custo_medio_atual REAL DEFAULT 0, fornecedor TEXT, chave_nfe TEXT, observacao TEXT)""")
    cur.execute('PRAGMA table_info(movimentacoes)')
    cols=[r[1] for r in cur.fetchall()]
    if 'receita_venda' not in cols:
        cur.execute('ALTER TABLE movimentacoes ADD COLUMN receita_venda REAL DEFAULT 0')
    c.commit(); c.close()

def seed():
    lista=[('Croissant Queijo Presunto','Croissant','UN',10,0),('Croissant Carne','Croissant','UN',10,0),('Croissant Ricota','Croissant','UN',10,0),('Pastel Carne','Pastel','UN',20,0),('Pastel Queijo','Pastel','UN',20,0),('Pastel Natural Frango','Pastel','UN',20,0),('Açaí','Açaí','UN',10,0),('Torta Frango','Torta','UN',10,0)]
    c=conn(); cur=c.cursor()
    for p in lista:
        cur.execute('INSERT OR IGNORE INTO produtos (nome,categoria,unidade,estoque_minimo,preco_venda) VALUES (?,?,?,?,?)', p)
    c.commit(); c.close()

def produtos_df():
    c=conn(); df=pd.read_sql_query('SELECT * FROM produtos WHERE ativo=1 ORDER BY nome', c); c.close(); return df

def get_or_create(nome,categoria='Mercadoria',unidade='UN'):
    c=conn(); cur=c.cursor(); cur.execute('SELECT id FROM produtos WHERE nome=?',(nome,)); r=cur.fetchone()
    if r: c.close(); return r['id']
    cur.execute('INSERT INTO produtos (nome,categoria,unidade) VALUES (?,?,?)',(nome,categoria,unidade)); c.commit(); i=cur.lastrowid; c.close(); return i

def moeda(v): return f'R$ {float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X','.')

def estoque_produto(pid):
    c=conn(); cur=c.cursor(); cur.execute('SELECT COALESCE(SUM(qtd_restante),0) qtd, COALESCE(SUM(qtd_restante*valor_unitario),0) valor FROM lotes WHERE produto_id=? AND qtd_restante>0',(pid,)); r=cur.fetchone(); c.close()
    qtd=float(r['qtd'] or 0); val=float(r['valor'] or 0); return qtd,val,(val/qtd if qtd else 0)

def entrada(pid,data_mov,qtd,vu,fornecedor='',obs='',chave=''):
    c=conn(); cur=c.cursor(); total=float(qtd)*float(vu)
    cur.execute('INSERT INTO lotes (produto_id,data_entrada,qtd_inicial,qtd_restante,valor_unitario,fornecedor,chave_nfe,observacao) VALUES (?,?,?,?,?,?,?,?)',(pid,str(data_mov),qtd,qtd,vu,fornecedor,chave,obs))
    cur.execute("INSERT INTO movimentacoes (data,produto_id,tipo,quantidade,valor_unitario,valor_total,receita_venda,fornecedor,chave_nfe,observacao) VALUES (?,?,'Entrada',?,?,?,?,?,?,?)",(str(data_mov),pid,qtd,vu,total,0,fornecedor,chave,obs))
    c.commit(); c.close()

def saida_peps(pid,data_mov,qtd,preco_venda,obs=''):
    c=conn(); cur=c.cursor(); cur.execute('SELECT id,qtd_restante,valor_unitario FROM lotes WHERE produto_id=? AND qtd_restante>0 ORDER BY date(data_entrada) ASC, id ASC',(pid,)); lotes=cur.fetchall()
    rest=float(qtd); cmv=0.0
    for l in lotes:
        if rest<=0: break
        disp=float(l['qtd_restante']); cons=min(rest,disp); cmv += cons*float(l['valor_unitario']); cur.execute('UPDATE lotes SET qtd_restante=? WHERE id=?',(disp-cons,l['id'])); rest-=cons
    if rest>0:
        c.rollback(); c.close(); raise ValueError(f'Estoque insuficiente. Faltam {rest:.2f} unidades.')
    c.commit(); c.close()
    _,_,cm=estoque_produto(pid); receita=float(qtd)*float(preco_venda or 0)
    c=conn(); cur=c.cursor(); cur.execute("INSERT INTO movimentacoes (data,produto_id,tipo,quantidade,valor_unitario,valor_total,receita_venda,cmv_peps,custo_medio_atual,observacao) VALUES (?,?,'Saída',?,?,?,?,?,?,?)",(str(data_mov),pid,qtd,preco_venda,receita,receita,cmv,cm,obs)); c.commit(); c.close()

def estoque_df():
    c=conn(); df=pd.read_sql_query("""SELECT p.id,p.nome Produto,p.categoria Categoria,p.unidade Unidade,p.estoque_minimo 'Estoque Mínimo',COALESCE(SUM(l.qtd_restante),0) 'Qtd Atual',COALESCE(SUM(l.qtd_restante*l.valor_unitario),0) 'Valor Estoque' FROM produtos p LEFT JOIN lotes l ON l.produto_id=p.id AND l.qtd_restante>0 WHERE p.ativo=1 GROUP BY p.id ORDER BY p.nome""",c); c.close()
    df['Custo Médio Atual']=df.apply(lambda r: r['Valor Estoque']/r['Qtd Atual'] if r['Qtd Atual'] else 0,axis=1); df['Alerta']=df.apply(lambda r:'⚠️ Baixo' if r['Qtd Atual']<=r['Estoque Mínimo'] else 'OK',axis=1); return df

def mov_df():
    c=conn(); df=pd.read_sql_query("""SELECT m.id,m.data Data,p.nome Produto,p.categoria Categoria,m.tipo Tipo,m.quantidade Quantidade,m.valor_unitario 'Valor Unitário',m.valor_total 'Valor Total',m.receita_venda 'Receita Venda',m.cmv_peps 'CMV PEPS',m.custo_medio_atual 'Custo Médio Após Saída',m.fornecedor Fornecedor,m.chave_nfe 'Chave NF-e',m.observacao Observação FROM movimentacoes m JOIN produtos p ON p.id=m.produto_id ORDER BY date(m.data) DESC,m.id DESC""",c); c.close(); return df

def lotes_df():
    c=conn(); df=pd.read_sql_query("""SELECT l.id,p.nome Produto,p.categoria Categoria,l.data_entrada 'Data Entrada',l.qtd_inicial 'Qtd Inicial',l.qtd_restante 'Qtd Restante',l.valor_unitario 'Valor Unitário',l.qtd_restante*l.valor_unitario 'Valor Restante',l.fornecedor Fornecedor,l.chave_nfe 'Chave NF-e',l.observacao Observação FROM lotes l JOIN produtos p ON p.id=l.produto_id ORDER BY p.nome,date(l.data_entrada),l.id""",c); c.close(); return df

def resumo_cmv(ano,mes):
    ini=f'{ano}-{mes:02d}-01'; fim=f'{ano+1}-01-01' if mes==12 else f'{ano}-{mes+1:02d}-01'
    c=conn(); df=pd.read_sql_query("""SELECT p.nome Produto,p.categoria Categoria,SUM(CASE WHEN m.tipo='Saída' THEN m.quantidade ELSE 0 END) 'Qtd Vendida',SUM(CASE WHEN m.tipo='Saída' THEN m.receita_venda ELSE 0 END) Receita,SUM(CASE WHEN m.tipo='Saída' THEN m.cmv_peps ELSE 0 END) CMV FROM movimentacoes m JOIN produtos p ON p.id=m.produto_id WHERE date(m.data)>=date(?) AND date(m.data)<date(?) GROUP BY p.id HAVING Receita>0 OR CMV>0 ORDER BY CMV DESC""",c,params=(ini,fim)); c.close()
    if df.empty: return df
    df['CMV %']=df.apply(lambda r:(r['CMV']/r['Receita']*100) if r['Receita'] else 0,axis=1); df['Lucro Bruto']=df['Receita']-df['CMV']; df['Margem Bruta %']=df.apply(lambda r:(r['Lucro Bruto']/r['Receita']*100) if r['Receita'] else 0,axis=1); df['Status']=df['CMV %'].apply(lambda x:'✅ OK' if x<=META_CMV else '⚠️ Acima da meta'); return df

def lname(tag): return tag.split('}')[-1]
def txt(root,name):
    for e in root.iter():
        if lname(e.tag)==name: return e.text or ''
    return ''
def fnum(x): return float(str(x or '0').replace(',','.'))
def ler_xml(b):
    root=ET.fromstring(b); chave=''; fornecedor=''; data_em=str(date.today())
    for e in root.iter():
        if lname(e.tag)=='infNFe': chave=e.attrib.get('Id','').replace('NFe','')
        if lname(e.tag)=='emit':
            for ch in e.iter():
                if lname(ch.tag)=='xNome': fornecedor=ch.text or ''; break
    dh=txt(root,'dhEmi') or txt(root,'dEmi')
    if dh: data_em=dh[:10]
    itens=[]
    for det in root.iter():
        if lname(det.tag)!='det': continue
        prod=None
        for ch in det:
            if lname(ch.tag)=='prod': prod=ch; break
        if prod is None: continue
        it={'Produto':'','Código':'','NCM':'','CFOP':'','Unidade':'UN','Quantidade':0.0,'Valor Unitário':0.0,'Valor Total':0.0}
        for ch in prod:
            n=lname(ch.tag); t=ch.text or ''
            if n=='xProd': it['Produto']=t.strip()
            elif n=='cProd': it['Código']=t.strip()
            elif n=='NCM': it['NCM']=t.strip()
            elif n=='CFOP': it['CFOP']=t.strip()
            elif n=='uCom': it['Unidade']=t.strip()
            elif n=='qCom': it['Quantidade']=fnum(t)
            elif n=='vUnCom': it['Valor Unitário']=fnum(t)
            elif n=='vProd': it['Valor Total']=fnum(t)
        itens.append(it)
    return {'fornecedor':fornecedor,'data_emissao':data_em,'chave':chave,'itens':pd.DataFrame(itens)}

init_db(); seed()
st.title('📦 Sistema de Estoque Restaurante — PEPS + CMV')
st.caption('Controle permitido: PEPS + CMV mensal. Meta ideal configurada: 36%.')
menu=st.sidebar.radio('Menu',['Painel CMV','Produtos','Importar Nota','Entrada Manual','Saída PEPS','Estoque Atual','Lotes','Movimentações','Exportar'])
pdf=produtos_df()

if menu=='Painel CMV':
    hoje=date.today(); c1,c2=st.columns(2); ano=int(c1.number_input('Ano',2020,2100,hoje.year)); mes=int(c2.selectbox('Mês',list(range(1,13)),index=hoje.month-1))
    res=resumo_cmv(ano,mes); est=estoque_df(); receita=res['Receita'].sum() if not res.empty else 0; cmv=res['CMV'].sum() if not res.empty else 0; lucro=receita-cmv; cmvp=(cmv/receita*100) if receita else 0; margem=(lucro/receita*100) if receita else 0
    a,b,c,d,e=st.columns(5); a.metric('Receita do Mês',moeda(receita)); b.metric('CMV PEPS',moeda(cmv)); c.metric('CMV %',f'{cmvp:.2f}%'); d.metric('Meta CMV','36,00%'); e.metric('Lucro Bruto',moeda(lucro),f'Margem {margem:.2f}%')
    if receita==0: st.warning('Ainda não há saídas com valor de venda neste mês.')
    elif cmvp<=META_CMV: st.success(f'CMV dentro da meta: {cmvp:.2f}%')
    else: st.error(f'CMV acima da meta: {cmvp:.2f}%')
    st.subheader('Resumo por Produto'); st.dataframe(res,use_container_width=True)
    st.subheader('Estoque Atual'); st.dataframe(est.drop(columns=['id']),use_container_width=True)
elif menu=='Produtos':
    st.subheader('Cadastrar Produto')
    with st.form('prod'):
        nome=st.text_input('Nome'); cat=st.text_input('Categoria'); un=st.selectbox('Unidade',['UN','KG','G','L','ML','CX']); minimo=st.number_input('Estoque mínimo',min_value=0.0,step=1.0); preco=st.number_input('Preço de venda padrão',min_value=0.0,step=0.5); ok=st.form_submit_button('Salvar')
        if ok:
            c=conn(); cur=c.cursor()
            try: cur.execute('INSERT INTO produtos (nome,categoria,unidade,estoque_minimo,preco_venda) VALUES (?,?,?,?,?)',(nome,cat,un,minimo,preco)); c.commit(); st.success('Produto cadastrado.')
            except Exception as e: st.warning(f'Não salvei: {e}')
            c.close()
    st.dataframe(produtos_df().drop(columns=['ativo']),use_container_width=True)
elif menu=='Importar Nota':
    st.subheader('Importar XML de NF-e/NFC-e')
    arq=st.file_uploader('Envie o XML da nota',type=['xml'])
    if arq:
        try:
            d=ler_xml(arq.getvalue()); st.write(f"Fornecedor: **{d['fornecedor'] or '-'}** | Data: **{d['data_emissao']}** | Chave: **{d['chave'] or '-'}**"); st.dataframe(d['itens'],use_container_width=True); cat=st.text_input('Categoria padrão para produtos novos','Mercadoria')
            if st.button('Confirmar entrada no estoque'):
                for _,it in d['itens'].iterrows():
                    pid=get_or_create(str(it['Produto']).strip(),cat,str(it['Unidade']).strip() or 'UN'); entrada(pid,d['data_emissao'],float(it['Quantidade']),float(it['Valor Unitário']),d['fornecedor'],f"XML Código {it['Código']} NCM {it['NCM']} CFOP {it['CFOP']}",d['chave'])
                st.success('Nota lançada no estoque.')
        except Exception as e: st.error(f'Erro ao ler XML: {e}')
elif menu=='Entrada Manual':
    st.subheader('Entrada de Estoque')
    op=dict(zip(pdf['nome'],pdf['id']))
    with st.form('ent'):
        dt=st.date_input('Data',date.today()); prod=st.selectbox('Produto',list(op)); qtd=st.number_input('Quantidade',min_value=0.01,step=1.0); vu=st.number_input('Valor unitário de compra',min_value=0.01,step=0.5); forn=st.text_input('Fornecedor'); obs=st.text_area('Observação'); ok=st.form_submit_button('Lançar entrada')
        if ok: entrada(op[prod],dt,qtd,vu,forn,obs); st.success('Entrada lançada.')
elif menu=='Saída PEPS':
    st.subheader('Saída / Venda — PEPS')
    op=dict(zip(pdf['nome'],pdf['id'])); prec=dict(zip(pdf['nome'],pdf['preco_venda']))
    with st.form('sai'):
        dt=st.date_input('Data',date.today()); prod=st.selectbox('Produto',list(op)); qtd=st.number_input('Quantidade vendida',min_value=0.01,step=1.0); preco=st.number_input('Valor unitário de venda',min_value=0.0,step=0.5,value=float(prec.get(prod,0) or 0)); st.write(f'Receita desta venda: **{moeda(qtd*preco)}**'); obs=st.text_area('Observação'); ok=st.form_submit_button('Lançar saída')
        if ok:
            try: saida_peps(op[prod],dt,qtd,preco,obs); st.success('Saída lançada e CMV calculado.')
            except Exception as e: st.error(str(e))
elif menu=='Estoque Atual': st.dataframe(estoque_df().drop(columns=['id']),use_container_width=True)
elif menu=='Lotes': st.dataframe(lotes_df(),use_container_width=True)
elif menu=='Movimentações': st.dataframe(mov_df(),use_container_width=True)
elif menu=='Exportar':

    arquivo = 'relatorio_estoque_peps_cmv.xlsx'

    estoque = estoque_df()
    movimentacoes = mov_df()
    lotes = lotes_df()
    resumo = resumo_cmv(date.today().year, date.today().month)

    with pd.ExcelWriter(arquivo, engine='openpyxl') as w:

        # Aba obrigatória
        pd.DataFrame({
            'Sistema': ['Estoque Restaurante PEPS + CMV'],
            'Data': [str(date.today())],
            'Observação': ['Relatório gerado automaticamente']
        }).to_excel(w, sheet_name='Resumo', index=False)

        estoque.to_excel(w, sheet_name='Estoque Atual', index=False)

        if not movimentacoes.empty:
            movimentacoes.to_excel(w, sheet_name='Movimentações', index=False)

        if not lotes.empty:
            lotes.to_excel(w, sheet_name='Lotes', index=False)

        if not resumo.empty:
            resumo.to_excel(w, sheet_name='CMV Mês Atual', index=False)

    with open(arquivo, 'rb') as f:
        st.download_button(
            'Baixar relatório Excel',
            f,
            'relatorio_estoque_peps_cmv.xlsx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
