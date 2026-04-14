"""
Sentinela & Dizimeiro Ecosystem - Auditoria Unificada
Foco: Leitura Universal de XML/ZIP e Cruzamento de Dados
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

# ─── ESTILO RIHANNA / MONTSERRAT (ORIGINAL) ──────────────────────────────────
st.set_page_config(page_title="Sentinela & Dizimeiro", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif !important; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .stButton>button { background-color: #d81b60; color: white; border-radius: 8px; font-weight: 600; width: 100%; }
        .memorial-box { background-color: white; padding: 20px; border-radius: 10px; border: 1px solid #d81b60; color: black; }
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
TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
]

# ─── FUNÇÕES DE APOIO E RECURSIVIDADE ────────────────────────────────────────

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

def extrair_xmls_zip(file_list):
    xml_contents = []
    def recursive_zip(file_obj):
        try:
            with zipfile.ZipFile(file_obj) as z:
                for name in z.namelist():
                    if name.lower().endswith('.xml'):
                        xml_contents.append(z.read(name))
                    elif name.lower().endswith('.zip'):
                        recursive_zip(io.BytesIO(z.read(name)))
        except: pass
    for f in file_list:
        if f.name.lower().endswith('.zip'): recursive_zip(f)
        else: xml_contents.append(f.read())
    return xml_contents

def extrair_dados_unificados(conteudo, cnpj_alvo):
    saida, entrada = [], []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return [], []
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_node = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = limpar_cnpj(dest_node.text) if dest_node is not None else ""
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        uf_emit = inf.find(f"{ns}emit/{ns}enderEmit/{ns}UF").text
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text # 1=Saída, 0=Entrada

        # MÓDULO SENTINELA (Vendas do Cliente)
        if emit_cnpj == cnpj_alvo and tipo_op == "1":
            dets = inf.findall(f"{ns}det")
            v_prod_total = sum(Decimal(d.find(f"{ns}prod/{ns}vProd").text) for d in dets)
            for d in dets:
                v_p = Decimal(d.find(f"{ns}prod/{ns}vProd").text)
                cf = d.find(f"{ns}prod/{ns}CFOP").text.replace(".","")
                saida.append({
                    "Nota": n_nota, "CFOP": cf, "ST": cf in CFOPS_ST,
                    "Valor Proporcional": v_nf * (v_p / v_prod_total) if v_prod_total > 0 else Decimal("0")
                })
        
        # MÓDULO DIZIMEIRO (Compras do Cliente)
        elif dest_cnpj == cnpj_alvo and tipo_op == "0":
            for d in inf.findall(f"{ns}det"):
                v_p = Decimal(d.find(f"{ns}prod/{ns}vProd").text)
                v_ipi = Decimal(d.find(f".//{ns}vIPI").text) if d.find(f".//{ns}vIPI") is not None else Decimal("0")
                cf = d.find(f"{ns}prod/{ns}CFOP").text.replace(".","")
                orig = d.find(f".//{ns}orig").text if d.find(f".//{ns}orig") is not None else "0"
                v_st_nota = Decimal(d.find(f".//{ns}vICMSST").text) if d.find(f".//{ns}vICMSST") is not None else Decimal("0")
                entrada.append({
                    "Nota": n_nota, "Emitente": inf.find(f"{ns}emit/{ns}xNome").text,
                    "UF_Origem": uf_emit, "Base": v_p + v_ipi, "ST_Nota": v_st_nota,
                    "Origem_CST": orig, "CFOP": cf
                })
    except: pass
    return saida, entrada

# ─── INTERFACE PRINCIPAL ─────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela & Dizimeiro - Auditoria Diamante")
    
    if 'cnpj' not in st.session_state: st.session_state.cnpj = ""
    if 'rbt12' not in st.session_state: st.session_state.rbt12 = ""

    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_input = st.text_input("CNPJ CLIENTE", value=st.session_state.cnpj, key="cnpj")
        cnpj_alvo = limpar_cnpj(cnpj_input)
        uf_destino = st.selectbox("UF DESTINO (DIFAL)", list(ALIQUOTAS_INTERNAS.keys()), index=25)
        
        st.header("⚙️ Simples Nacional")
        rbt12_raw = st.text_input("RBT12 ACUMULADO", value=st.session_state.rbt12, key="rbt12")
        rbt12 = Decimal(rbt12_raw.replace(".","").replace(",",".")) if rbt12_raw else Decimal("0")
        
        if st.button("🧹 LIMPAR CAMPOS"):
            st.session_state.cnpj = ""; st.session_state.rbt12 = ""; st.rerun()

    files = st.file_uploader("Upload XMLs ou ZIPs", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 INICIAR AUDITORIA UNIFICADA") and files and cnpj_alvo:
        xml_contents = extrair_xmls_zip(files)
        todas_saidas, todas_entradas = [], []
        
        for xml in xml_contents:
            s, e = extrair_dados_unificados(xml, cnpj_alvo)
            todas_saidas.extend(s); todas_entradas.extend(e)
            
        col1, col2 = st.columns(2)

        # --- PROCESSAMENTO SENTINELA ---
        with col1:
            st.markdown("### 📈 Sentinela (Saídas Próprias)")
            if todas_saidas:
                df_s = pd.DataFrame(todas_saidas)
                # Cálculo de Alíquotas 13 Casas
                aliq_nom, ded, p_icms = Decimal("0.073"), Decimal("5940.00"), Decimal("0.34")
                for n, i, f, nm, d, pi in TABELAS_SIMPLES:
                    if rbt12 <= f: aliq_nom, ded, p_icms = nm, d, pi; break
                aliq_ef = ((rbt12 * aliq_nom) - ded) / rbt12 if rbt12 > 0 else Decimal("0.04")
                aliq_st = aliq_ef * (Decimal("1") - p_icms)

                res_s = df_s.groupby(['CFOP', 'ST']).agg({'Valor Proporcional': 'sum'}).reset_index()
                res_s['DAS'] = res_s.apply(lambda r: (r['Valor Proporcional'].quantize(Decimal("0.01"), ROUND_HALF_UP) * (aliq_st if r['ST'] else aliq_ef)).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)
                
                st.metric("DAS Simples Nacional", f"R$ {res_s['DAS'].sum():,.2f}")
                st.table(res_s[['CFOP', 'Valor Proporcional', 'DAS']])
            else: st.warning("Sem notas de saída para este CNPJ.")

        # --- PROCESSAMENTO DIZIMEIRO ---
        with col2:
            st.markdown("### 📉 Dizimeiro (Entradas de Terceiros)")
            if todas_entradas:
                df_e = pd.DataFrame(todas_entradas)
                aliq_int = Decimal(str(ALIQUOTAS_INTERNAS[uf_destino]))
                
                def calc_difal(r):
                    if r['ST_Nota'] > 0 or r['UF_Origem'] == uf_destino: return Decimal("0")
                    aliq_inter = Decimal("0.04") if r['Origem_CST'] in ['1','2','3','8'] else Decimal("0.12")
                    return (r['Base'] * (aliq_int - aliq_inter)).quantize(Decimal("0.01"), ROUND_HALF_UP)
                
                df_e['DIFAL'] = df_e.apply(calc_difal, axis=1)
                st.metric("DIFAL a Recolher", f"R$ {df_e['DIFAL'].sum():,.2f}")
                st.dataframe(df_e[df_e['DIFAL'] > 0][['Nota', 'Emitente', 'DIFAL']])
            else: st.warning("Sem notas de entrada para este CNPJ.")
            
    elif files and not cnpj_alvo:
        st.error("Por favor, informe o CNPJ do cliente para filtrar os XMLs.")

if __name__ == "__main__":
    main()
