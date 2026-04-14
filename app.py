"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Foco: Resumo por CFOP de emissão própria sem alteração do valor total (vNF).
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão extrema para bater com o PGDAS
getcontext().prec = 30 

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .memorial-box { background-color: white; padding: 25px; border-radius: 10px; border: 1px solid #d81b60; color: black; line-height: 1.6; }
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS ──────────────────────────────────────────────────────────
PERC_ICMS_ANEXO_I = Decimal("0.34")
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}

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
        
        # Filtro de CNPJ para Emissão Própria
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        if cnpj_cliente and emit_cnpj != cnpj_cliente:
            return []
            
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 
        
        # Pega o CFOP principal da nota (da primeira linha de detalhe)
        # Mantendo a leitura do valor TOTAL da nota (vNF) para não errar a base
        det_1 = inf.find(f"{ns}det")
        cfop_principal = det_1.find(f"{ns}prod/{ns}CFOP").text.replace(".", "") if det_1 is not None else "0000"
        
        regs.append({
            "Nota": n_nota,
            "Tipo": "SAÍDA" if tipo_op == "1" else "ENTRADA",
            "CFOP": cfop_principal,
            "ST": cfop_principal in CFOPS_ST,
            "Valor (vNF)": v_nf,
            "Chave": chave
        })
        chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Resumo por CFOP (Base vNF)")
    
    with st.sidebar:
        st.header("👤 Identificação")
        cnpj_input = st.text_input("CNPJ do Cliente", value="52.980.554/0001-04")
        cnpj_cli = limpar_cnpj(cnpj_input)
        
        st.header("⚙️ PGDAS")
        rbt12_raw = st.text_input("RBT12", value="504.403,47")
        try:
            rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0.00")
        except: rbt12 = Decimal("0.00")
        
        is_st_toggle = st.toggle("Dedução de ICMS ST (34%)", value=True)

    # Cálculo de Alíquotas
    aliq_nom, deducao = Decimal("0.073"), Decimal("5940.00")
    aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12 if rbt12 > 0 else Decimal("0.04")
    aliq_st = aliq_efetiva * (Decimal("1.0") - PERC_ICMS_ANEXO_I)

    files = st.file_uploader("Upload XMLs", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Gerar Memorial") and files:
        chaves_vistas = set()
        registros = []
        for f in files:
            registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            
            # Dashboard (Faturamento Total vNF)
            df_saida = df[df["Tipo"] == "SAÍDA"].copy()
            fat_total = df_saida["Valor (vNF)"].sum()
            
            # Cálculo do DAS Individual (Nota a Nota)
            df_saida['Aliq'] = df_saida['ST'].apply(lambda x: aliq_st if is_st_toggle and x else aliq_efetiva)
            df_saida['DAS'] = df_saida.apply(lambda r: (r['Valor (vNF)'] * r['Aliq']).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)

            st.markdown("### 📊 Dashboard de Apuração")
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento (vNF)", f"R$ {fat_total:,.2f}")
            c2.metric("DAS Total", f"R$ {df_saida['DAS'].sum():,.2f}")
            c3.metric("Notas Processadas", len(df_saida))

            # RESUMO POR CFOP (Considerando apenas emissões próprias de saída)
            st.markdown("### 📑 Resumo por CFOP (Emissões Próprias)")
            resumo = df_saida.groupby(['CFOP', 'ST']).agg({'Valor (vNF)': 'sum', 'DAS': 'sum'}).reset_index()
            resumo['Tributação'] = resumo['ST'].apply(lambda x: "ICMS ST (Dedução 34%)" if x else "Normal")
            
            st.table(resumo[['CFOP', 'Tributação', 'Valor (vNF)', 'DAS']])

            st.markdown("### 📋 Listagem Analítica")
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.error(f"❌ Nenhuma nota do CNPJ {cnpj_cli} encontrada.")

if __name__ == "__main__":
    main()
