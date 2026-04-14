import os
import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import streamlit as st

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
    </style>
""", unsafe_allow_html=True)

# ─── TABELAS E CÁLCULO DE ALÍQUOTA ───────────────────────────────────────────
TABELAS = {
    "Anexo I (Comércio)": [
        (Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
        (Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
        (Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
        (Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
        (Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00")),
        (Decimal("4800000.00"), Decimal("0.19"), Decimal("256500.00")),
    ]
}

def calcular_aliquota_especifica(rbt12, anexo):
    tabela = TABELAS[anexo]
    for limite, aliq_nom, deducao in tabela:
        if rbt12 <= limite:
            if rbt12 == 0: return aliq_nom
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
            return aliq_efetiva.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return tabela[-1][1]

# ─── MÓDULO CEIFADOR E CFOPs ──────────────────────────────────────────────────
CFOPS_RECEITA = {"5101", "5102", "5403", "5405", "6101", "6102"}

def processar_xml(conteudo):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        tipo = inf.find(f"{ns}ide/{ns}tpNF").text
        for det in inf.findall(f"{ns}det"):
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            if tipo == "1" and cfop in CFOPS_RECEITA:
                regs.append(v_prod)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────
def main():
    st.title("🛡️ Sentinela - Auditoria Fiscal")
    
    with st.sidebar:
        st.header("1. Dados do PGDAS")
        # CAMPO ZERADO COMO VOCÊ PEDIU
        rbt12_in = st.text_input("Faturamento Acumulado (RBT12)", value="0,00")
        try:
            rbt12 = Decimal(rbt12_in.replace(".", "").replace(",", "."))
        except:
            rbt12 = Decimal("0.00")
            
        anexo = st.selectbox("Anexo", list(TABELAS.keys()))
        aliq = calcular_aliquota_especifica(rbt12, anexo)
        st.metric("Alíquota Calculada", f"{aliq * 100}%")

    st.subheader("2. Upload de XMLs")
    files = st.file_uploader("Suba os arquivos", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Calcular Imposto") and files:
        faturamento_lido = Decimal("0.00")
        for f in files:
            # Lógica simplificada de leitura para o exemplo
            faturamento_lido += sum(processar_xml(f.read()))
        
        imposto = (faturamento_lido * aliq).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        st.markdown("### Resultado da Auditoria")
        c1, c2 = st.columns(2)
        c1.metric("Total das Notas", f"R$ {faturamento_lido:,.2f}")
        c2.metric("IMPOSTO CALCULADO", f"R$ {imposto:,.2f}")
        
        st.info(f"Compare esse valor de **R$ {imposto:,.2f}** com o seu DAS para ver se as notas batem!")

if __name__ == "__main__":
    main()
