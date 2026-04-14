"""
Apuração do Simples Nacional - Sentinela Ecosystem
Auditoria Independente: O sistema calcula o imposto do zero para conferência humana.
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
        .stButton>button { background-color: #d81b60; color: white; border-radius: 8px; font-weight: 600; border: none; transition: 0.3s; }
        .stButton>button:hover { background-color: #ad144d; box-shadow: 0 4px 12px rgba(216, 27, 96, 0.4); }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

# ─── TABELAS DE ALÍQUOTAS (ANEXOS I E III) ────────────────────────────────────

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

def calcular_aliquota_especifica(rbt12, nome_anexo):
    """Calcula a Alíquota Efetiva com base no faturamento acumulado (RBT12)."""
    tabela = TABELAS_SIMPLES[nome_anexo]
    for limite, aliq_nom, deducao in tabela:
        if rbt12 <= limite:
            if rbt12 == 0: return aliq_nom
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
            return aliq_efetiva.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return tabela[-1][1]

# ─── CFOPs FISCAIS (LISTA INTEGRAL) ───────────────────────────────────────────

CFOPS_RECEITA_BRUTA = {
    "5101", "5102", "5103", "5104", "5105", "5106", "5109", "5110", "5111",
    "5112", "5113", "5114", "5115", "5116", "5117", "5118", "5119", "5120",
    "5122", "5123", "5124", "5125", "5403", "5405", "6101", "6102", "6403", "6404"
}
CFOPS_DEVOLUCAO_ENTRADA = {"1201", "1202", "1203", "1204", "2201", "2202"}

# ─── MÓDULO CEIFADOR E PROCESSAMENTO XML ──────────────────────────────────────

def processar_xml_bytes(conteudo, nome_arquivo):
    registros = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 
        for det in inf.findall(f"{ns}det"):
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            
            valor_receita = v_prod if (tipo_op == "1" and cfop in CFOPS_RECEITA_BRUTA) else Decimal("0.00")
            valor_devolucao = v_prod if (tipo_op == "0" and cfop in CFOPS_DEVOLUCAO_ENTRADA) else Decimal("0.00")
            
            if valor_receita > 0 or valor_devolucao > 0:
                registros.append({"cfop": cfop, "receita": valor_receita, "devolucao": valor_devolucao})
    except: pass
    return registros

def modulo_ceifador_zip(zip_bytes, nome_zip):
    all_regs = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            content = z.read(name)
            if name.lower().endswith('.zip'): all_regs.extend(modulo_ceifador_zip(content, name))
            elif name.lower().endswith('.xml'): all_regs.extend(processar_xml_bytes(content, name))
    return all_regs

# ─── INTERFACE STREAMLIT ──────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria Independente")
    st.markdown("O sistema calculará o imposto puramente pelas notas para você comparar com sua guia.")

    with st.sidebar:
        st.header("1. Regra de Cálculo (PGDAS)")
        # Ajustado para vir zerado conforme solicitado
        rbt12_input = st.text_input("Faturamento Acumulado (RBT12)", value="0,00")
        
        # Tratamento de erro para garantir que o cálculo só ocorra se houver valor
        try:
            rbt12 = Decimal(rbt12_input.replace(".", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            rbt12 = Decimal("0.00")
            
        nome_anexo = st.selectbox("Anexo da Atividade", options=list(TABELAS_SIMPLES.keys()))
        
        aliq_efetiva = calcular_aliquota_especifica(rbt12, nome_anexo)
        
        st.markdown("---")
        st.write("**Alíquota Efetiva Identificada:**")
        st.subheader(f"{(aliq_efetiva * 100):.4f} %")

    st.subheader("2. Documentos Fiscais")
    files = st.file_uploader("Arraste XMLs ou ZIPs Matrioskas", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria") and files:
        if rbt12 <= 0:
            st.warning("⚠️ O RBT12 está zerado. A alíquota aplicada será a da 1ª faixa (4% para Comércio / 6% para Serviços).")

        with st.spinner("O Ceifador está analisando os documentos..."):
            all_data = []
            for f in files:
                content = f.read()
                if f.name.lower().endswith('.zip'): 
                    all_data.extend(modulo_ceifador_zip(content, f.name))
                else: 
                    all_data.extend(processar_xml_bytes(content, f.name))
            
            if not all_data:
                st.error("Nenhuma nota fiscal de receita ou devolução encontrada nos arquivos enviados.")
                return

            total_rec = sum(d['receita'] for d in all_data)
            total_dev = sum(d['devolucao'] for d in all_data)
            base_liq = max(total_rec - total_dev, Decimal("0.00"))
            
            imposto_apurado = (base_liq * aliq_efetiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            st.markdown("---")
            st.markdown("## 📊 Resultado da Auditoria das Notas")
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento Lido (XML)", f"R$ {total_rec:,.2f}")
            c2.metric("Base de Cálculo Líquida", f"R$ {base_liq:,.2f}")
            c3.metric("IMPOSTO CALCULADO (DAS)", f"R$ {imposto_apurado:,.2f}")

            st.success(f"💡 Conferência Final: O Sentinela chegou ao valor de **R$ {imposto_apurado:,.2f}**. Veja se bate com o valor da sua guia!")

if __name__ == "__main__":
    main()
