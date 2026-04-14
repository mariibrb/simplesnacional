"""
Sentinela Ecosystem - Auditoria Simples Nacional
Foco: Otimização de input (RBT12 limpo) e Base vNF
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
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .faixa-box { background-color: white; padding: 15px; border-radius: 8px; border: 1px solid #d81b60; margin-bottom: 10px; min-height: 100px; }
        .faixa-ativa { background-color: #ffe6f0; border: 2px solid #d81b60; font-weight: bold; }
        .memorial-box { background-color: white; padding: 20px; border-radius: 10px; border: 1px solid #d81b60; font-family: monospace; color: black; }
    </style>
""", unsafe_allow_html=True)

# ─── TABELAS OFICIAIS ────────────────────────────────────────────────────────

TABELAS_SIMPLES = {
    "Anexo I (Comércio)": [
        (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
        (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
        (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
        (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
        (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00")),
        (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.19"), Decimal("256500.00")),
    ],
    "Anexo III (Serviços)": [
        (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.06"), Decimal("0.00")),
        (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.112"), Decimal("9360.00")),
        (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.135"), Decimal("17640.00")),
        (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.16"), Decimal("35640.00")),
        (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.21"), Decimal("125640.00")),
        (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.33"), Decimal("648000.00")),
    ]
}

CFOPS_RECEITA = {"5101", "5102", "5403", "5405", "6102", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── LÓGICA DE PROCESSAMENTO ─────────────────────────────────────────────────

def extrair_dados_xml(conteudo, nome_arquivo, chaves_vistas):
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
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        
        tem_receita = False
        tem_devolucao = False
        
        for det in inf.findall(f"{ns}det"):
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            if tipo_op == "1" and cfop in CFOPS_RECEITA: tem_receita = True
            elif tipo_op == "0" and cfop in CFOPS_DEVOLUCAO: tem_devolucao = True
                
        if tem_receita:
            regs.append({"Nota": n_nota, "Tipo": "SAÍDA (RECEITA)", "Valor Base (vNF)": v_nf, "Chave": chave})
        elif tem_devolucao:
            regs.append({"Nota": n_nota, "Tipo": "ENTRADA (DEVOLUÇÃO)", "Valor Base (vNF)": v_nf, "Chave": chave})
            
        chaves_vistas.add(chave)
    except: pass
    return regs

def ceifador_zip(zip_bytes, chaves_vistas):
    all_regs = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            content = z.read(name)
            if name.lower().endswith('.zip'): all_regs.extend(ceifador_zip(content, chaves_vistas))
            elif name.lower().endswith('.xml'): all_regs.extend(extrair_dados_xml(content, name, chaves_vistas))
    return all_regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria e Rastreabilidade")
    
    with st.sidebar:
        st.header("1. Parâmetros PGDAS")
        
        # CAMPO LIMPO: Alterado para iniciar vazio e facilitar a digitação
        rbt12_raw = st.text_input("Faturamento Acumulado (RBT12)", value="", placeholder="Digite o valor aqui...")
        
        # Conversão segura do input vazio
        try:
            if rbt12_raw.strip() == "":
                rbt12 = Decimal("0.00")
            else:
                rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", "."))
        except:
            rbt12 = Decimal("0.00")
        
        nome_anexo = st.selectbox("Anexo Principal", options=list(TABELAS_SIMPLES.keys()))
        
        aliq_efetiva = Decimal("0.00")
        faixa_ativa_num = 1
        for num, inicio, fim, aliq_nom, deducao in TABELAS_SIMPLES[nome_anexo]:
            if rbt12 <= fim:
                faixa_ativa_num = num
                aliq_efetiva = (((rbt12 * aliq_nom) - deducao) / rbt12) if rbt12 > 0 else aliq_nom
                break
        
        aliq_efetiva = max(aliq_efetiva, Decimal("0.00")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        st.metric("Alíquota Efetiva", f"{(aliq_efetiva * 100):.4f} %")

    st.subheader("2. Arquivos do Mês")
    files = st.file_uploader("Upload XML ou ZIP", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria") and files:
        chaves_vistas = set()
        registros = []
        for f in files:
            content = f.read()
            if f.name.lower().endswith('.zip'): registros.extend(ceifador_zip(content, chaves_vistas))
            else: registros.extend(extrair_dados_xml(content, f.name, chaves_vistas))
        
        if not registros:
            st.error("Nenhuma nota fiscal de faturamento encontrada.")
            return

        df = pd.DataFrame(registros)
        saidas = df[df["Tipo"] == "SAÍDA (RECEITA)"]["Valor Base (vNF)"].sum()
        devolucoes = df[df["Tipo"] == "ENTRADA (DEVOLUÇÃO)"]["Valor Base (vNF)"].sum()
        base_liq = max(saidas - devolucoes, Decimal("0.00"))
        imposto = (base_liq * aliq_efetiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        nota_min, nota_max = df["Nota"].min(), df["Nota"].max()

        st.markdown("### 📊 Resultado da Auditoria (Base vNF)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Faixa de Notas", f"{nota_min} a {nota_max}")
        c2.metric("Faturamento (vNF)", f"R$ {saidas:,.2f}")
        c3.metric("Base Líquida", f"R$ {base_liq:,.2f}")
        c4.metric("IMPOSTO CALCULADO", f"R$ {imposto:,.2f}")

        st.markdown("### 📋 Rastreabilidade das Notas")
        st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
