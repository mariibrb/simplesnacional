"""
Apuração do Simples Nacional - Sentinela Ecosystem
Auditoria Independente de XMLs (NF-e, CT-e, NFC-e) vs Regras do PGDAS
"""

import os
import csv
import zipfile
import logging
import io
import re
from datetime import datetime
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import streamlit as st

# ─── ESTILIZAÇÃO E INTERFACE (Tema Rihanna / Montserrat) ──────────────────────
st.set_page_config(page_title="Sentinela - Auditoria Simples Nacional", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4, h5, h6 { color: #d81b60 !important; font-weight: 800; }
        .stButton>button { background-color: #d81b60; color: white; border-radius: 8px; font-weight: 600; border: none; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
    </style>
""", unsafe_allow_html=True)

# ─── TABELAS OFICIAIS (ANEXO I - COMÉRCIO) ───────────────────────────────────
# Tabela para cálculo da Alíquota Efetiva Progressiva
TABELA_ANEXO_I = [
    (Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
    (Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
    (Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
    (Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
    (Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00")),
    (Decimal("4800000.00"), Decimal("0.19"), Decimal("256500.00")),
]

# ─── CFOPs RELEVANTES (LISTA COMPLETA) ────────────────────────────────────────

CFOPS_RECEITA_BRUTA = {
    "5101", "5102", "5103", "5104", "5105", "5106", "5109", "5110", "5111",
    "5112", "5113", "5114", "5115", "5116", "5117", "5118", "5119", "5120",
    "5122", "5123", "5124", "5125", "5403", "5405", "6101", "6102", "6103", 
    "6104", "6105", "6106", "6107", "6108", "6109", "6110", "6111", "6112", 
    "6113", "6114", "6115", "6116", "6117", "6118", "6119", "6120", "6122", 
    "6123", "6124", "6125", "6403", "6404", "6405", "7101", "7102"
}

CFOPS_DEVOLUCAO_ENTRADA = {
    "1201", "1202", "1203", "1204", "1205", "1206", "1207",
    "2201", "2202", "2203", "2204", "2205", "2206", "2207"
}

# ─── MÓDULOS DE CÁLCULO E PROCESSAMENTO ───────────────────────────────────────

def calcular_aliquota_efetiva(rbt12):
    """Aplica a fórmula oficial do PGDAS: (RBT12 * AliqNominal - ParcelaDedução) / RBT12"""
    for limite, aliq_nom, deducao in TABELA_ANEXO_I:
        if rbt12 <= limite:
            if rbt12 == 0: return Decimal("0.04")
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
            return aliq_efetiva.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return Decimal("0.19")

def decimal_seguro(valor_str):
    if not valor_str: return Decimal("0.00")
    try:
        # Trata formatos 1.256,76 ou 1256.76
        limpo = valor_str.strip().replace(".", "").replace(",", ".")
        return Decimal(limpo).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except: return Decimal("0.00")

def processar_xml_bytes(conteudo, nome_arquivo):
    registros = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []

        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text # 1=Saída, 0=Entrada
        for det in inf.findall(f"{ns}det"):
            prod = det.find(f"{ns}prod")
            cfop = prod.find(f"{ns}CFOP").text.replace(".", "")
            v_prod = Decimal(prod.find(f"{ns}vProd").text)
            
            val_rec = Decimal("0.00")
            val_dev = Decimal("0.00")
            
            if tipo_op == "1" and cfop in CFOPS_RECEITA_BRUTA:
                val_rec = v_prod
            elif tipo_op == "0" and cfop in CFOPS_DEVOLUCAO_ENTRADA:
                val_dev = v_prod
                
            registros.append({
                "arquivo": nome_arquivo,
                "cfop": cfop,
                "receita": val_rec,
                "devolucao": val_dev,
                "chave": inf.attrib.get('Id', '')[3:]
            })
    except: pass
    return registros

def modulo_ceifador_zip(zip_bytes, nome_zip):
    all_regs = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                content = z.read(name)
                if name.lower().endswith('.zip'):
                    all_regs.extend(modulo_ceifador_zip(content, name))
                elif name.lower().endswith('.xml'):
                    all_regs.extend(processar_xml_bytes(content, name))
    except: pass
    return all_regs

# ─── INTERFACE STREAMLIT ──────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria Fiscal Independente")
    st.markdown("Cálculo automático baseado nas notas fiscais e na faixa de faturamento.")

    with st.sidebar:
        st.header("1. Parâmetro do PGDAS")
        # O único dado necessário do PDF de Março
        rbt12_input = st.text_input("Faturamento Acumulado (RBT12 - Página 1)", value="256.852,76")
        rbt12 = decimal_seguro(rbt12_input)
        
        aliq_efetiva = calcular_aliquota_efetiva(rbt12)
        
        st.markdown("---")
        st.write("**Alíquota Detectada para Auditoria:**")
        st.subheader(f"{(aliq_efetiva * 100):.4f} %")
        st.caption("Fórmula aplicada sobre a Tabela do Anexo I.")

    st.subheader("2. Documentação do Mês")
    files = st.file_uploader("Arraste XMLs ou ZIPs Matrioskas", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Executar Auditoria") and files:
        with st.spinner("Processando arquivos..."):
            all_data = []
            for f in files:
                content = f.read()
                if f.name.lower().endswith('.zip'):
                    all_data.extend(modulo_ceifador_zip(content, f.name))
                else:
                    all_data.extend(processar_xml_bytes(content, f.name))
            
            if not all_data:
                st.error("Nenhum documento fiscal processado.")
                return

            # Consolidação Financeira
            total_receita = sum(d['receita'] for d in all_data)
            total_devolucoes = sum(d['devolucao'] for d in all_data)
            base_calculo = max(total_receita - total_devolucoes, Decimal("0.00"))
            
            # O CÁLCULO INDEPENDENTE DO SENTINELA
            imposto_calculado = (base_calculo * aliq_efetiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            st.markdown("---")
            st.markdown("## 📊 Resultado da Auditoria")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total das Notas (Faturamento)", f"R$ {total_receita:,.2f}")
            with col2:
                st.metric("Base de Cálculo Líquida", f"R$ {base_calculo:,.2f}")
            with col3:
                st.metric("IMPOSTO CALCULADO", f"R$ {imposto_calculado:,.2f}")

            st.info(f"💡 Compare agora com o seu sistema: O valor de **R$ {imposto_sentinela:,.2f}** é o que de fato deveria estar na sua guia com base nas notas fornecidas.")
            
            with st.expander("Ver detalhamento nota a nota"):
                st.dataframe(all_data)

if __name__ == "__main__":
    main()
