"""
Sentinela & Dizimeiro Ecosystem - Auditoria Unificada
Foco: Processamento simultâneo de Saídas (Sentinela) e Entradas (Dizimeiro)
Aparência: Montserrat Original | Fundo Radial Rosa
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão extrema para bater com o PGDAS
getcontext().prec = 60 

# ─── ESTILO RIHANNA / MONTSERRAT (ORIGINAL RESTAURADO) ───────────────────────
st.set_page_config(page_title="Sentinela & Dizimeiro", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif !important; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .memorial-box { background-color: white; padding: 20px; border-radius: 10px; border: 1px solid #d81b60; color: black; }
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS UNIFICADAS ───────────────────────────────────────────────
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}
ALIQUOTAS_INTERNAS = {
    'AC': 0.19, 'AL': 0.19, 'AM': 0.20, 'BA': 0.205, 'CE': 0.20, 'DF': 0.20, 'ES': 0.17, 'GO': 0.19, 
    'MA': 0.22, 'MG': 0.18, 'MS': 0.17, 'MT': 0.17, 'PA': 0.19, 'PB': 0.20, 'PE': 0.205, 'PI': 0.21, 
    'PR': 0.195, 'RJ': 0.22, 'RN': 0.20, 'RO': 0.195, 'RR': 0.20, 'RS': 0.17, 'SC': 0.17, 'SE': 0.19, 
    'SP': 0.18, 'TO': 0.20
}

# ─── FUNÇÕES DE APOIO ────────────────────────────────────────────────────────

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

def extrair_dados_hibridos(conteudo, cnpj_cliente):
    regs_saida, regs_entrada = [], []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return [], []
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_cnpj = limpar_cnpj(inf.find(f"{ns}dest/{ns}CNPJ").text) if inf.find(f"{ns}dest/{ns}CNPJ") is not None else ""
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        uf_emit = inf.find(f"{ns}emit/{ns}enderEmit/{ns}UF").text

        # Lógica SENTINELA (Vendas Próprias)
        if emit_cnpj == cnpj_cliente:
            v_prod_total = sum(Decimal(det.find(f"{ns}prod/{ns}vProd").text) for det in inf.findall(f"{ns}det"))
            for det in inf.findall(f"{ns}det"):
                v_p = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                cf = det.find(f"{ns}prod/{ns}CFOP").text.replace(".","")
                regs_saida.append({
                    "Nota": n_nota, "CFOP": cf, "ST": cf in CFOPS_ST,
                    "Valor Proporcional": v_nf * (v_p / v_prod_total), "Emitente": "PRÓPRIO"
                })
        
        # Lógica DIZIMEIRO (Compras de Terceiros)
        elif dest_cnpj == cnpj_cliente:
            for det in inf.findall(f"{ns}det"):
                v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                v_ipi = Decimal(det.find(f".//{ns}vIPI").text) if det.find(f".//{ns}vIPI") is not None else Decimal("0")
                cf = det.find(f"{ns}prod/{ns}CFOP").text.replace(".","")
                orig = det.find(f".//{ns}orig").text if det.find(f".//{ns}orig") is not None else "0"
                v_st_nota = Decimal(det.find(f".//{ns}vICMSST").text) if det.find(f".//{ns}vICMSST") is not None else Decimal("0")
                
                regs_entrada.append({
                    "Nota": n_nota, "Emitente": inf.find(f"{ns}emit/{ns}xNome").text,
                    "UF_Origem": uf_emit, "Base": v_prod + v_ipi, "ST_Nota": v_st_nota,
                    "Origem_CST": orig, "CFOP": cf
                })
    except: pass
    return regs_saida, regs_entrada

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Ecossistema Sentinela & Dizimeiro")
    
    if 'cnpj' not in st.session_state: st.session_state.cnpj = ""
    if 'rbt12' not in st.session_state: st.session_state.rbt12 = ""

    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_cli = limpar_cnpj(st.text_input("CNPJ", value=st.session_state.cnpj, key="cnpj"))
        uf_destino = st.selectbox("UF de Destino (DIFAL)", list(ALIQUOTAS_INTERNAS.keys()), index=25) # SP Default
        
        st.header("⚙️ Simples Nacional")
        rbt12_raw = st.text_input("RBT12", value=st.session_state.rbt12, key="rbt12")
        rbt12 = Decimal(rbt12_raw.replace(".","").replace(",",".")) if rbt12_raw else Decimal("0")
        
        if st.button("🧹 Limpar Dados"):
            st.session_state.cnpj = ""; st.session_state.rbt12 = ""; st.rerun()

    files = st.file_uploader("Upload XMLs", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria Unificada") and files:
        saidas, entradas, chaves = [], [], set()
        for f in files:
            s, e = extrair_dados_hibridos(f, cnpj_cli)
            saidas.extend(s); entradas.extend(e)
        
        col1, col2 = st.columns(2)

        # --- PROCESSAMENTO SENTINELA (SAÍDAS) ---
        with col1:
            st.markdown("### 📈 Módulo Sentinela (Saídas)")
            if saidas:
                df_s = pd.DataFrame(saidas)
                # Cálculo Alíquota Efetiva (Faixa 2 Anexo I como exemplo)
                aliq_nom, ded, p_icms = Decimal("0.073"), Decimal("5940.00"), Decimal("0.34")
                aliq_ef = ((rbt12 * aliq_nom) - ded) / rbt12 if rbt12 > 0 else Decimal("0.04")
                aliq_st = aliq_ef * (Decimal("1") - p_icms)

                res_s = df_s.groupby(['CFOP', 'ST']).agg({'Valor Proporcional': 'sum'}).reset_index()
                res_s['DAS'] = res_s.apply(lambda r: (r['Valor Proporcional'].quantize(Decimal("0.01"), ROUND_HALF_UP) * (aliq_st if r['ST'] else aliq_ef)).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)
                
                st.metric("DAS Total a Recolher", f"R$ {res_s['DAS'].sum():,.2f}")
                st.table(res_s)
            else: st.warning("Sem notas de saída.")

        # --- PROCESSAMENTO DIZIMEIRO (ENTRADAS) ---
        with col2:
            st.markdown("### 📉 Módulo Dizimeiro (DIFAL)")
            if entradas:
                df_e = pd.DataFrame(entradas)
                def calc_difal(r):
                    if r['ST_Nota'] > 0 or r['UF_Origem'] == uf_destino: return Decimal("0")
                    aliq_inter = Decimal("0.04") if r['Origem_CST'] in ['1','2','3','8'] else Decimal("0.12")
                    aliq_int = Decimal(str(ALIQUOTAS_INTERNAS[uf_destino]))
                    return (r['Base'] * (aliq_int - aliq_inter)).quantize(Decimal("0.01"), ROUND_HALF_UP)
                
                df_e['DIFAL'] = df_e.apply(calc_difal, axis=1)
                st.metric("DIFAL Total a Recolher", f"R$ {df_e['DIFAL'].sum():,.2f}")
                st.dataframe(df_e[df_e['DIFAL'] > 0][['Nota', 'Emitente', 'DIFAL']])
            else: st.warning("Sem notas de entrada.")

if __name__ == "__main__":
    main()
