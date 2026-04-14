"""
Sentinela Ecosystem - Auditoria e Rastreabilidade
Foco: Conciliação de Valores (vProd vs vNF) e Agrupamento por Nota
"""

import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
import streamlit as st
import pandas as pd

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
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

# ─── CONFIGURAÇÕES FISCAIS ───────────────────────────────────────────────────

TABELAS_SIMPLES = {
    "Anexo I (Comércio)": [
        (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
        (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
        (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
        (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
        (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00")),
        (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.19"), Decimal("256500.00")),
    ]
}

CFOPS_RECEITA = {"5101", "5102", "5403", "5405", "6102", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── PROCESSAMENTO ANALÍTICO ─────────────────────────────────────────────────

def extrair_dados_xml(conteudo, chaves_vistas):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 
        
        # Valor Total da Nota (vNF) para conferência
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        
        for det in inf.findall(f"{ns}det"):
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            
            categoria = "OUTROS"
            if tipo_op == "1" and cfop in CFOPS_RECEITA: categoria = "SAÍDA (RECEITA)"
            elif tipo_op == "0" and cfop in CFOPS_DEVOLUCAO: categoria = "ENTRADA (DEVOLUÇÃO)"
                
            regs.append({
                "Nota": n_nota,
                "CFOP": cfop,
                "Tipo": categoria,
                "Valor Itens (vProd)": v_prod,
                "Valor Total Nota (vNF)": v_nf,
                "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Conciliação de Faturamento")
    
    with st.sidebar:
        rbt12_input = st.text_input("RBT12", value="0,00")
        rbt12 = Decimal(rbt12_input.replace(".", "").replace(",", "."))
        nome_anexo = "Anexo I (Comércio)" # Fixo para o exemplo
        
        aliq_efetiva = Decimal("0.00")
        for num, inicio, fim, aliq_nom, deducao in TABELAS_SIMPLES[nome_anexo]:
            if rbt12 <= fim:
                aliq_efetiva = (((rbt12 * aliq_nom) - deducao) / rbt12) if rbt12 > 0 else aliq_nom
                break
        st.metric("Alíquota Efetiva", f"{(aliq_efetiva * 100):.4f} %")

    files = st.file_uploader("Upload XMLs", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Auditar") and files:
        chaves_vistas = set()
        bruto_regs = []
        for f in files:
            bruto_regs.extend(extrair_dados_xml(f.read(), chaves_vistas))
        
        if bruto_regs:
            df = pd.DataFrame(bruto_regs)
            
            # AGRUPAMENTO PARA CONCILIAÇÃO: Uma linha por Nota/CFOP
            df_conciliado = df.groupby(["Nota", "Chave", "Tipo", "Valor Total Nota (vNF)"]).agg({
                "Valor Itens (vProd)": "sum"
            }).reset_index()

            # Cálculos Finais
            saidas = df_conciliado[df_conciliado["Tipo"] == "SAÍDA (RECEITA)"]["Valor Itens (vProd)"].sum()
            devolucoes = df_conciliado[df_conciliado["Tipo"] == "ENTRADA (DEVOLUÇÃO)"]["Valor Itens (vProd)"].sum()
            base_liq = max(saidas - devolucoes, Decimal("0.00"))
            
            # DASHBOARD
            c1, c2, c3 = st.columns(3)
            c1.metric("Total vProd (Receita)", f"R$ {saidas:,.2f}")
            c2.metric("Total vNF (Notas)", f"R$ {df_conciliado[df_conciliado['Tipo'] == 'SAÍDA (RECEITA)']['Valor Total Nota (vNF)'].sum():,.2f}")
            c3.metric("Diferença vNF vs vProd", f"R$ {(df_conciliado[df_conciliado['Tipo'] == 'SAÍDA (RECEITA)']['Valor Total Nota (vNF)'].sum() - saidas):,.2f}")

            st.markdown("### 📋 Tabela de Conferência (Agrupada por Nota)")
            st.dataframe(df_conciliado.sort_values("Nota"), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
