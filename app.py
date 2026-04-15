"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Foco: Cálculo Automático de Alíquotas PGDAS (13 Casas) e Base vNF Proporcional
Incluso: Tratamento de Devoluções, Intervalos por Série e Matrioscas
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

getcontext().prec = 60 

# ─── CONFIGURAÇÕES FISCAIS ──────────────────────────────────────────────────
CFOPS_DEVOLUCAO_VENDA = {"1202", "1411", "2202", "2411"} # Deduzem a Receita
CFOPS_DEVOLUCAO_COMPRA = {"5202", "5411", "6202", "6411"} # Saídas não tributáveis
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404", "1411", "2411", "5411", "6411"}

TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]

# ─── ESTILIZAÇÃO ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
    </style>
""", unsafe_allow_html=True)

# ─── FUNÇÕES DE APOIO ────────────────────────────────────────────────────────

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

def extrair_dados_xml(conteudo, chaves_vistas, cnpj_cliente):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_cnpj = limpar_cnpj(inf.find(f"{ns}dest/{ns}CNPJ").text) if inf.find(f"{ns}dest/{ns}CNPJ") is not None else ""
        
        # Filtro Rigoroso: Se o cliente não for nem emitente nem destinatário (em caso de devolução de venda), ignora
        if cnpj_cliente and (emit_cnpj != cnpj_cliente and dest_cnpj != cnpj_cliente):
            return []
            
        ide = inf.find(f"{ns}ide")
        n_nota = int(ide.find(f"{ns}nNF").text)
        serie = ide.find(f"{ns}serie").text
        mod = ide.find(f"{ns}mod").text
        tp_nf = ide.find(f"{ns}tpNF").text # 0=Entrada, 1=Saída
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)

        v_prod_total = sum(Decimal(det.find(f"{ns}prod/{ns}vProd").text) for det in inf.findall(f"{ns}det"))

        for det in inf.findall(f"{ns}det"):
            v_p = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            prop = v_p / v_prod_total if v_prod_total > 0 else Decimal("0")
            valor_proporcional = v_nf * prop

            # Determina Categoria Fiscal
            categoria = "OUTROS"
            if tp_nf == "1":
                if cfop in CFOPS_DEVOLUCAO_COMPRA: categoria = "DEVOLUÇÃO COMPRA (NÃO TRIB)"
                else: categoria = "RECEITA BRUTA"
            else:
                if cfop in CFOPS_DEVOLUCAO_VENDA: categoria = "DEVOLUÇÃO VENDA (DEDUTÍVEL)"
            
            regs.append({
                "Nota": n_nota, "Série": serie, "Modelo": mod,
                "Tipo": "SAÍDA" if tp_nf == "1" else "ENTRADA",
                "CFOP": cfop, "ST": cfop in CFOPS_ST,
                "Valor Cru": valor_proporcional, "Categoria": categoria, "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

def processar_recursivo(arquivo_bytes, chaves_vistas, cnpj_cli):
    registros = []
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for nome in z.namelist():
                if nome.lower().endswith('.xml'):
                    with z.open(nome) as f:
                        registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
                elif nome.lower().endswith('.zip'):
                    with z.open(nome) as f:
                        registros.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
    except:
        registros.extend(extrair_dados_xml(arquivo_bytes, chaves_vistas, cnpj_cli))
    return registros

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria e Memorial (Anexo I)")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_input = st.text_input("CNPJ", value="", key=f"c_{st.session_state.reset_key}")
        cnpj_cli = limpar_cnpj(cnpj_input)
        st.header("⚙️ Receita Bruta")
        rbt12_raw = st.text_input("RBT12", value="", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        
        if st.button("🗑️ Limpar Tudo"):
            st.session_state.reset_key += 1
            st.rerun()

    # MOTOR ALÍQUOTA
    aliq_nom, deducao, p_icms = Decimal("0.04"), Decimal("0"), Decimal("0.335")
    for _, ini, fim, nom, ded, p_ic in TABELAS_SIMPLES:
        if rbt12 <= fim:
            aliq_nom, deducao, p_icms = nom, ded, p_ic
            break
    
    aliq_ef = ((rbt12 * aliq_nom) - deducao) / rbt12 if rbt12 > 0 else Decimal("0.04")
    aliq_st = aliq_ef * (Decimal("1.0") - p_icms)

    files = st.file_uploader("Upload XMLs/ZIPs", accept_multiple_files=True, type=["xml", "zip"], key=f"f_{st.session_state.reset_key}")

    if st.button("🚀 Executar Auditoria") and files:
        chaves_vistas, regs = set(), []
        for f in files: regs.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            
            # Lógica de Cálculo de Faturamento Líquido
            vendas = df[df["Categoria"] == "RECEITA BRUTA"]["Valor Cru"].sum()
            devolucoes_venda = df[df["Categoria"] == "DEVOLUÇÃO VENDA (DEDUTÍVEL)"]["Valor Cru"].sum()
            faturamento_liquido = vendas - devolucoes_venda

            # Dashboard de Intervalos por Série
            st.markdown("### 📊 Intervalos Detectados")
            df_s = df[df["Tipo"] == "SAÍDA"]
            intervalos = df_s.groupby(['Modelo', 'Série']).agg(Ini=('Nota', 'min'), Fim=('Nota', 'max'), Qtd=('Nota', 'count')).reset_index()
            c_int = st.columns(len(intervalos) if len(intervalos) < 5 else 4)
            for i, row in intervalos.iterrows():
                c_int[i%4].metric(f"Série {row['Série']}", f"{row['Ini']} a {row['Fim']}", f"{row['Qtd']} notas")

            # Resumo Financeiro
            st.markdown("### 💰 Memorial de Cálculo PGDAS")
            c1, c2, c3 = st.columns(3)
            c1.metric("Receita Bruta (Vendas)", f"R$ {vendas:,.2f}")
            c2.metric("(-) Devoluções Venda", f"R$ {devolucoes_venda:,.2f}", delta_color="inverse")
            c3.metric("(=) Base de Cálculo", f"R$ {faturamento_liquido:,.2f}")

            # Detalhamento Fiscal por CFOP
            resumo = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA (DEDUTÍVEL)"])].groupby(['CFOP', 'ST', 'Categoria']).agg({'Valor Cru': 'sum'}).reset_index()
            resumo['Valor Cru'] = resumo.apply(lambda x: x['Valor Cru'] * -1 if "DEVOLUÇÃO" in x['Categoria'] else x['Valor Cru'], axis=1)
            resumo['DAS'] = resumo.apply(lambda x: (x['Valor Cru'].quantize(Decimal("0.01")) * (aliq_st if x['ST'] else aliq_ef)).quantize(Decimal("0.01")), axis=1)
            
            st.table(resumo[['CFOP', 'Categoria', 'Valor Cru', 'DAS']])
            st.dataframe(df.sort_values(["Modelo", "Série", "Nota"]), use_container_width=True)
        else:
            st.error("Nenhum dado encontrado.")

if __name__ == "__main__":
    main()
