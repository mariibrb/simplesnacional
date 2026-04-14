"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Foco: Resumo segregado por CFOP/ST sem alterar base de leitura original.
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

# ─── REGRAS FISCAIS (ANEXO I - COMÉRCIO) ─────────────────────────────────────
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
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        
        if cnpj_cliente and emit_cnpj != cnpj_cliente:
            return []
            
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 
        
        # Identificação do CFOP predominante da nota para segregação
        primeiro_det = inf.find(f"{ns}det")
        cfop_nota = primeiro_det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "") if primeiro_det is not None else "0000"
        
        regs.append({
            "Nota": n_nota,
            "Tipo": "SAÍDA" if tipo_op == "1" else "ENTRADA",
            "CFOP": cfop_nota,
            "ST": cfop_nota in CFOPS_ST,
            "Valor (vNF)": v_nf,
            "Chave": chave
        })
        chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Memorial Analítico Segregado")
    
    with st.sidebar:
        st.header("👤 Identificação")
        cnpj_input = st.text_input("CNPJ do Cliente", value="52.980.554/0001-04")
        cnpj_cli = limpar_cnpj(cnpj_input)
        
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("Faturamento Acumulado (RBT12)", placeholder="Ex: 504403.47")
        try:
            rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0.00")
        except: rbt12 = Decimal("0.00")
        
        st.info("Anexo I (Comércio)")
        is_st_toggle = st.toggle("Dedução de ICMS ST (34%)", value=True)

    # Cálculo Alíquotas
    aliq_nom, deducao = Decimal("0.073"), Decimal("5940.00")
    aliq_efetiva_cheia = ((rbt12 * aliq_nom) - deducao) / rbt12 if rbt12 > 0 else Decimal("0.04")
    aliq_st = aliq_efetiva_cheia * (Decimal("1.0") - PERC_ICMS_ANEXO_I)
    
    aliq_st_view = aliq_st.quantize(Decimal("0.000001"), ROUND_HALF_UP)
    aliq_ef_view = aliq_efetiva_cheia.quantize(Decimal("0.000001"), ROUND_HALF_UP)

    files = st.file_uploader("Upload XMLs", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Gerar Memorial") and files:
        chaves_vistas = set()
        registros = []
        for f in files:
            registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            
            # Bases de Cálculo (Inalteradas)
            fat_bruto = df[df["Tipo"] == "SAÍDA"]["Valor (vNF)"].sum()
            dev_bruto = df[df["Tipo"] == "ENTRADA"]["Valor (vNF)"].sum()
            base_liquida = max(fat_bruto - dev_bruto, Decimal("0.00"))
            
            # Segregação no DataFrame de Saída
            df_saida = df[df["Tipo"] == "SAÍDA"].copy()
            df_saida['Aliq'] = df_saida['ST'].apply(lambda x: aliq_st if is_st_toggle and x else aliq_efetiva_cheia)
            df_saida['Imp'] = df_saida.apply(lambda row: (row['Valor (vNF)'] * row['Aliq']).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)
            
            valor_das_total = df_saida['Imp'].sum()

            st.markdown("### 📊 Dashboard de Conciliação")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Faturamento (vNF)", f"R$ {fat_bruto:,.2f}")
            c2.metric("Base Líquida", f"R$ {base_liquida:,.2f}")
            c3.metric("DAS TOTAL", f"R$ {valor_das_total:,.2f}")
            c4.metric("Qtd Notas", len(df))

            # Resumo Segregado por CFOP
            st.markdown("### 📑 Resumo por Grupo de Tributação")
            resumo = df_saida.groupby(['CFOP', 'ST']).agg({'Valor (vNF)': 'sum', 'Imp': 'sum'}).reset_index()
            resumo['Descrição'] = resumo['ST'].apply(lambda x: "SUBSTITUIÇÃO TRIBUTÁRIA" if x else "TRIBUTAÇÃO NORMAL")
            resumo['Alíquota'] = resumo['ST'].apply(lambda x: f"{aliq_st_view*100:.4f}%" if x else f"{aliq_ef_view*100:.4f}%")
            
            st.table(resumo[['CFOP', 'Descrição', 'Valor (vNF)', 'Alíquota', 'Imp']])

            st.markdown("### 📋 Rastreabilidade nota a nota")
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.error(f"❌ Nenhuma nota do CNPJ {cnpj_cli} encontrada.")

if __name__ == "__main__":
    main()
