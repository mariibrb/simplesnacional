"""
Sentinela Ecosystem - Auditoria Simples Nacional
Foco: Detecção de duplicidade e Memorial de Cálculo Analítico
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

# ─── TABELAS E REGRAS FISCAIS (ANEXOS I E III) ──────────────────────────────

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

CFOPS_RECEITA_BRUTA = {
    "5101", "5102", "5103", "5104", "5105", "5106", "5109", "5110", "5111",
    "5112", "5113", "5114", "5115", "5116", "5117", "5118", "5119", "5120",
    "5122", "5123", "5124", "5125", "5403", "5405", "6101", "6102", "6403", "6404"
}
CFOPS_DEVOLUCAO_ENTRADA = {"1201", "1202", "1203", "1204", "2201", "2202"}

# ─── LÓGICA DE AUDITORIA COM TRAVA DE DUPLICIDADE ────────────────────────────

def calcular_aliquota_efetiva(rbt12, nome_anexo):
    tabela = TABELAS_SIMPLES[nome_anexo]
    for limite, aliq_nom, deducao in tabela:
        if rbt12 <= limite:
            if rbt12 == 0: return aliq_nom, aliq_nom, deducao
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
            return aliq_efetiva.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), aliq_nom, deducao
    return tabela[-1][1], tabela[-1][1], tabela[-1][2]

def processar_xml_bytes(conteudo, nome_arquivo, chaves_processadas):
    registros = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        # Identificação da Chave (Trava de Duplicidade)
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_processadas:
            return [] # Ignora se já foi processada
        
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 
        for det in inf.findall(f"{ns}det"):
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            
            val_rec = v_prod if (tipo_op == "1" and cfop in CFOPS_RECEITA_BRUTA) else Decimal("0.00")
            val_dev = v_prod if (tipo_op == "0" and cfop in CFOPS_DEVOLUCAO_ENTRADA) else Decimal("0.00")
            
            if val_rec > 0 or val_dev > 0:
                registros.append({
                    "arquivo": nome_arquivo, 
                    "chave": chave, 
                    "cfop": cfop, 
                    "receita": val_rec, 
                    "devolucao": val_dev
                })
        
        chaves_processadas.add(chave) # Registra a chave como lida
    except: pass
    return registros

def modulo_ceifador_zip(zip_bytes, chaves_processadas):
    all_regs = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            content = z.read(name)
            if name.lower().endswith('.zip'): 
                all_regs.extend(modulo_ceifador_zip(content, chaves_processadas))
            elif name.lower().endswith('.xml'): 
                all_regs.extend(processar_xml_bytes(content, name, chaves_processadas))
    return all_regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria com Trava de Duplicidade")
    
    with st.sidebar:
        st.header("1. Parâmetros PGDAS")
        rbt12_input = st.text_input("Faturamento Acumulado (RBT12)", value="0,00")
        try:
            rbt12 = Decimal(rbt12_input.replace(".", "").replace(",", "."))
        except: rbt12 = Decimal("0.00")
        
        nome_anexo = st.selectbox("Anexo da Atividade", options=list(TABELAS_SIMPLES.keys()))
        aliq_efetiva, aliq_nom, deducao = calcular_aliquota_efetiva(rbt12, nome_anexo)
        st.metric("Alíquota Efetiva", f"{(aliq_efetiva * 100):.4f} %")

    st.subheader("2. Upload de Documentos")
    files = st.file_uploader("Arraste XMLs ou ZIPs Matrioskas", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Executar Auditoria") and files:
        chaves_processadas = set() # Conjunto para evitar duplicados
        all_data = []
        
        for f in files:
            content = f.read()
            if f.name.lower().endswith('.zip'): 
                all_data.extend(modulo_ceifador_zip(content, chaves_processadas))
            else: 
                all_data.extend(processar_xml_bytes(content, f.name, chaves_processadas))
        
        total_rec = sum(d['receita'] for d in all_data)
        total_dev = sum(d['devolucao'] for d in all_data)
        base_liq = max(total_rec - total_dev, Decimal("0.00"))
        imposto_sentinela = (base_liq * aliq_efetiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # MÉTRICAS
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Notas Únicas", len(chaves_processadas))
        c2.metric("Receita Bruta (XML)", f"R$ {total_rec:,.2f}")
        c3.metric("Base Líquida", f"R$ {base_liq:,.2f}")
        c4.metric("IMPOSTO APURADO", f"R$ {imposto_sentinela:,.2f}")

        # MEMORIAL DE CÁLCULO
        st.markdown("### 📝 Memorial de Cálculo Detalhado")
        memorial = f"""
        **1. PARÂMETROS DA ALÍQUOTA (PGDAS)**
        - RBT12: R$ {rbt12:,.2f}
        - Alíquota Nominal: {aliq_nom * 100}% | Parcela a Deduzir: R$ {deducao:,.2f}
        - Fórmula: ((RBT12 * Alíq. Nominal) - Dedução) / RBT12
        - **Efetiva: {aliq_efetiva * 100}%**

        **2. LEITURA DE DOCUMENTOS (TRAVA ANTI-DUPLICIDADE ATIVA)**
        - Documentos Únicos Processados: {len(chaves_processadas)}
        - (+) Receita Bruta Total: R$ {total_rec:,.2f}
        - (-) Devoluções de Venda: R$ {total_dev:,.2f}
        - **(=) Base de Cálculo Final: R$ {base_liq:,.2f}**

        **3. APURAÇÃO FINAL**
        - Base Líquida (R$ {base_liq:,.2f}) x Alíquota ({aliq_efetiva * 100}%)
        - **VALOR DAS CALCULADO: R$ {imposto_sentinela:,.2f}**
        """
        st.markdown(f'<div class="memorial-box">{memorial}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
