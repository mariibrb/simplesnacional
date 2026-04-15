"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Versão: Multi-Anexo (I e II) - Integral e Detalhada
Foco: Segregação automática por CFOP, Matrioscas e Alíquotas 13 casas
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão de 60 casas para cálculos fiscais
getcontext().prec = 60 

# ─── REGRAS FISCAIS UNIVERSAIS ──────────────────────────────────────────────
# ANEXO I - COMÉRCIO
TABELA_ANEXO_I = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]

# ANEXO II - INDÚSTRIA
TABELA_ANEXO_II = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.045"), Decimal("0.00"), Decimal("0.3200")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.078"), Decimal("5940.00"), Decimal("0.3200")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.10"), Decimal("13860.00"), Decimal("0.3250")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.112"), Decimal("22500.00"), Decimal("0.3250")),
]

CFOPS_INDUSTRIA = {"5101", "6101", "5103", "5105", "5401", "6401"}
CFOPS_DEVOLUCAO_VENDA = {"1201", "1202", "1411", "2201", "2202", "2411"}
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404", "1411", "2411", "5411", "6411"}

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

def calcular_aliq_efetiva(rbt12, tabela):
    aliq_nom, deducao, p_icms = tabela[0][3], tabela[0][4], tabela[0][5]
    for _, ini, fim, nom, ded, p_ic in tabela:
        if rbt12 <= fim:
            aliq_nom, deducao, p_icms = nom, ded, p_ic
            break
    if rbt12 > 0:
        efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
    else:
        efetiva = aliq_nom
    return efetiva, p_icms

def extrair_dados_xml(conteudo, chaves_vistas, cnpj_cliente):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        emit_cnpj = re.sub(r'\D', '', inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_node = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = re.sub(r'\D', '', dest_node.text) if dest_node is not None else ""
        
        if cnpj_cliente and (emit_cnpj != cnpj_cliente and dest_cnpj != cnpj_cliente):
            return []
            
        ide = inf.find(f"{ns}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns}nNF").text), ide.find(f"{ns}serie").text, ide.find(f"{ns}mod").text
        tp_nf, v_nf = ide.find(f"{ns}tpNF").text, Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)

        dets = inf.findall(f"{ns}det")
        v_prod_total = sum(Decimal(d.find(f"{ns}prod/{ns}vProd").text) for d in dets)

        for det in dets:
            v_p = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            prop = v_p / v_prod_total if v_prod_total > 0 else Decimal("0")
            
            anexo = "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I"
            categoria = "OUTROS"
            if tp_nf == "1":
                categoria = "RECEITA BRUTA"
            elif cfop in CFOPS_DEVOLUCAO_VENDA:
                categoria = "DEVOLUÇÃO VENDA"
            
            regs.append({
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, "Anexo": anexo,
                "Valor Cru": v_nf * prop, "Categoria": categoria, "Chave": chave
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
                    with z.open(nome) as f: registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
                elif nome.lower().endswith('.zip'):
                    with z.open(nome) as f: registros.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
    except: registros.extend(extrair_dados_xml(arquivo_bytes, chaves_vistas, cnpj_cli))
    return registros

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria Multi-Anexo")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_cli = re.sub(r'\D', '', st.text_input("CNPJ", key=f"c_{st.session_state.reset_key}"))
        st.header("⚙️ Parâmetros")
        rbt12_raw = st.text_input("RBT12 Total", value="", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        if st.button("🗑️ Resetar"):
            st.session_state.reset_key += 1
            st.rerun()

    # Cálculo das Alíquotas por Anexo
    aliq_ef1, p_icms1 = calcular_aliq_efetiva(rbt12, TABELA_ANEXO_I)
    aliq_st1 = aliq_ef1 * (Decimal("1.0") - p_icms1)
    
    aliq_ef2, p_icms2 = calcular_aliq_efetiva(rbt12, TABELA_ANEXO_II)
    aliq_st2 = aliq_ef2 * (Decimal("1.0") - p_icms2)

    files = st.file_uploader("Upload XMLs/ZIPs", accept_multiple_files=True, type=["xml", "zip"], key=f"f_{st.session_state.reset_key}")

    if st.button("🚀 Executar Auditoria") and files:
        chaves_vistas, regs = set(), []
        for f in files: regs.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df_fiscal = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()
            
            # Aplicação das Alíquotas Específicas
            def calcular_das(row):
                base = row['Valor Cru'].quantize(Decimal("0.01"), ROUND_HALF_UP)
                if row['Categoria'] == "DEVOLUÇÃO VENDA": base *= -1
                
                if row['Anexo'] == "ANEXO I":
                    aliq = aliq_st1 if row['ST'] else aliq_ef1
                else:
                    aliq = aliq_st2 if row['ST'] else aliq_ef2
                
                return base, aliq, (base * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP)

            res_vals = df_fiscal.apply(calcular_das, axis=1, result_type='expand')
            df_fiscal['Base'], df_fiscal['Aliq_Usada'], df_fiscal['DAS'] = res_vals[0], res_vals[1], res_vals[2]

            st.markdown("### 📑 Memorial Segregado por Anexo e CFOP")
            resumo = df_fiscal.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({'Base': 'sum', 'DAS': 'sum', 'Aliq_Usada': 'first'}).reset_index()
            resumo['Alíquota (%)'] = resumo['Aliq_Usada'].apply(lambda x: f"{(x*100):.13f}%")
            
            st.table(resumo[['Anexo', 'CFOP', 'Categoria', 'Alíquota (%)', 'Base', 'DAS']])

            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("Total Base (Líquida)", f"R$ {df_fiscal['Base'].sum():,.2f}")
            c2.metric("Total DAS", f"R$ {df_fiscal['DAS'].sum():,.2f}")
            
            st.markdown("### 📋 Rastreabilidade")
            st.dataframe(df.sort_values(["Anexo", "Nota"]), use_container_width=True)
        else:
            st.error("Nenhum dado encontrado.")

if __name__ == "__main__":
    main()
