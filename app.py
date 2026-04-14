"""
Sentinela Ecosystem - Auditoria Simples Nacional
Foco: Rastreabilidade de Notas e Identificação de Devoluções
"""

import os
import csv
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
        .memorial-box { background-color: white; padding: 20px; border-radius: 10px; border: 1px solid #d81b60; font-family: monospace; color: black; }
    </style>
""", unsafe_allow_html=True)

# ─── TABELAS E REGRAS FISCAIS ────────────────────────────────────────────────

TABELAS_SIMPLES = {
    "Anexo I (Comércio)": [
        (Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
        (Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
        (Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
        (Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
        (Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00")),
        (Decimal("4800000.00"), Decimal("0.19"), Decimal("256500.00")),
    ],
    "Anexo III (Serviços)": [
        (Decimal("180000.00"), Decimal("0.06"), Decimal("0.00")),
        (Decimal("360000.00"), Decimal("0.112"), Decimal("9360.00")),
        (Decimal("720000.00"), Decimal("0.135"), Decimal("17640.00")),
        (Decimal("1800000.00"), Decimal("0.16"), Decimal("35640.00")),
        (Decimal("3600000.00"), Decimal("0.21"), Decimal("125640.00")),
        (Decimal("4800000.00"), Decimal("0.33"), Decimal("648000.00")),
    ]
}

# CFOPs de Receita (Saídas) e Devoluções (Entradas que abatem)
CFOPS_RECEITA = {"5101", "5102", "5403", "5405", "6102", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── PROCESSAMENTO ───────────────────────────────────────────────────────────

def calcular_aliquota_efetiva(rbt12, nome_anexo):
    tabela = TABELAS_SIMPLES[nome_anexo]
    for limite, aliq_nom, deducao in tabela:
        if rbt12 <= limite:
            if rbt12 == 0: return aliq_nom, aliq_nom, deducao
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
            return aliq_efetiva.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), aliq_nom, deducao
    return tabela[-1][1], tabela[-1][1], tabela[-1][2]

def extrair_dados_xml(conteudo, chaves_vistas):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 
        for det in inf.findall(f"{ns}det"):
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            
            # Classificação
            categoria = "IGNORADO"
            valor_final = Decimal("0.00")
            
            if tipo_op == "1" and cfop in CFOPS_RECEITA:
                categoria = "SAÍDA (RECEITA)"
                valor_final = v_prod
            elif tipo_op == "0" and cfop in CFOPS_DEVOLUCAO:
                categoria = "ENTRADA (DEVOLUÇÃO)"
                valor_final = v_prod
                
            if categoria != "IGNORADO":
                regs.append({
                    "Chave de Acesso": chave,
                    "CFOP": cfop,
                    "Tipo": categoria,
                    "Valor (R$)": valor_final
                })
        chaves_vistas.add(chave)
    except: pass
    return regs

def ceifador_zip(zip_bytes, chaves_vistas):
    all_regs = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            content = z.read(name)
            if name.lower().endswith('.zip'): all_regs.extend(ceifador_zip(content, chaves_vistas))
            elif name.lower().endswith('.xml'): all_regs.extend(extrair_dados_xml(content, chaves_vistas))
    return all_regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria e Rastreabilidade")
    
    with st.sidebar:
        st.header("1. Dados do PGDAS")
        rbt12_input = st.text_input("RBT12 (Acumulado 12 meses)", value="0,00")
        try:
            rbt12 = Decimal(rbt12_input.replace(".", "").replace(",", "."))
        except: rbt12 = Decimal("0.00")
        
        nome_anexo = st.selectbox("Anexo", options=list(TABELAS_SIMPLES.keys()))
        aliq_efetiva, aliq_nom, deducao = calcular_aliquota_efetiva(rbt12, nome_anexo)
        st.metric("Alíquota Efetiva", f"{(aliq_efetiva * 100):.4f} %")

    st.subheader("2. Arquivos para Análise")
    uploaded_files = st.file_uploader("Upload XML ou ZIP", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Auditar Agora") and uploaded_files:
        chaves_vistas = set()
        dados_fiscais = []
        
        for f in uploaded_files:
            content = f.read()
            if f.name.lower().endswith('.zip'):
                dados_fiscais.extend(ceifador_zip(content, chaves_vistas))
            else:
                dados_fiscais.extend(extrair_dados_xml(content, chaves_vistas))
        
        if not dados_fiscais:
            st.error("Nenhuma nota de Saída ou Devolução encontrada.")
            return

        df = pd.DataFrame(dados_fiscais)
        
        # Consolidação
        saidas = df[df["Tipo"] == "SAÍDA (RECEITA)"]["Valor (R$)"].sum()
        devolucoes = df[df["Tipo"] == "ENTRADA (DEVOLUÇÃO)"]["Valor (R$)"].sum()
        base_calc = max(saidas - devolucoes, Decimal("0.00"))
        imposto = (base_calc * aliq_efetiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Dashboard
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Faturamento Bruto", f"R$ {saidas:,.2f}")
        c2.metric("Total Devoluções", f"R$ {devolucoes:,.2f}")
        c3.metric("Base Líquida", f"R$ {base_calc:,.2f}")
        c4.metric("DAS APURADO", f"R$ {imposto:,.2f}")

        # Listagem Analítica
        st.markdown("### 📋 Listagem de Notas Consideradas")
        st.dataframe(df, use_container_width=True)

        # Memorial
        st.markdown("### 📝 Memorial de Cálculo")
        memorial = f"Base Líquida (R$ {base_calc:,.2f}) x Alíquota ({aliq_efetiva*100}%) = R$ {imposto:,.2f}"
        st.markdown(f'<div class="memorial-box">{memorial}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
