"""
Sentinela & Dizimeiro Ecosystem - Auditoria Fiscal 360°
Módulos: Sentinela (Saídas/Simples) | Dizimeiro (Entradas/DIFAL)
Design: Rihanna Original | Tipografia: Montserrat
"""

import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile
from decimal import Decimal, ROUND_HALF_UP, getcontext

# --- CONFIGURAÇÃO GLOBAL ---
getcontext().prec = 60
st.set_page_config(page_title="DIZIMEIRO & SENTINELA", layout="wide", page_icon="🛡️")

# --- ESTILO RIHANNA ORIGINAL UNIFICADO ---
def aplicar_estilo_unificado():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;800&family=Plus+Jakarta+Sans:wght@400;700&display=swap');
        header, [data-testid="stHeader"], .stDeployButton { display: none !important; }
        .stApp { background: radial-gradient(circle at top right, #FFDEEF 0%, #F8F9FA 100%) !important; }
        [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #FFDEEF !important; min-width: 400px !important; }
        * { font-family: 'Montserrat', sans-serif !important; }
        h1, h2, h3 { font-weight: 800 !important; color: #FF69B4 !important; text-align: center; }
        div.stButton > button {
            color: #6C757D !important; background-color: #FFFFFF !important; 
            border: 1px solid #DEE2E6 !important; border-radius: 15px !important;
            font-weight: 800 !important; height: 50px !important; width: 100%;
            text-transform: uppercase; transition: all 0.4s ease;
        }
        div.stButton > button:hover { transform: translateY(-3px) !important; border-color: #FF69B4 !important; color: #FF69B4 !important; }
        [data-testid="stFileUploader"] { border: 2px dashed #FF69B4 !important; border-radius: 20px !important; background: #FFFFFF !important; }
        .instrucoes-card { background-color: rgba(255, 255, 255, 0.7); border-radius: 15px; padding: 20px; border-left: 5px solid #FF69B4; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

# --- REGRAS FISCAIS DIZIMEIRO ---
ALIQUOTAS_INTERNAS = {
    'AC': 19.0, 'AL': 19.0, 'AM': 20.0, 'AP': 18.0, 'BA': 20.5, 'CE': 20.0, 'DF': 20.0,
    'ES': 17.0, 'GO': 19.0, 'MA': 22.0, 'MG': 18.0, 'MS': 17.0, 'MT': 17.0, 'PA': 19.0,
    'PB': 20.0, 'PE': 20.5, 'PI': 21.0, 'PR': 19.5, 'RJ': 22.0, 'RN': 20.0, 'RO': 19.5,
    'RR': 20.0, 'RS': 17.0, 'SC': 17.0, 'SE': 19.0, 'SP': 18.0, 'TO': 20.0
}
SUL_SUDESTE_ORIGEM = ['SP', 'RJ', 'MG', 'PR', 'RS', 'SC']
ESTADOS_BASE_DUPLA = ['MG', 'PR', 'RS', 'SC', 'SP', 'BA', 'PE', 'GO', 'MS', 'AL', 'SE']

# --- REGRAS FISCAIS SENTINELA ---
TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
]
CFOPS_ST_SENTINELA = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}

# --- FUNÇÕES CORE ---
def limpar_cnpj(texto):
    return re.sub(r'\D', '', str(texto)).strip()

def buscar_tag(tag, no):
    for elemento in no.iter():
        if elemento.tag.split('}')[-1] == tag: return elemento
    return None

def extrair_xmls_recursivo(uploaded_files):
    xml_contents = []
    def process_zip(file_obj):
        try:
            with zipfile.ZipFile(file_obj) as z:
                for name in z.namelist():
                    if name.startswith('__MACOSX') or '/.' in name: continue 
                    content = z.read(name)
                    if name.lower().endswith('.xml'): xml_contents.append(io.BytesIO(content))
                    elif name.lower().endswith('.zip'): process_zip(io.BytesIO(content))
        except: pass
    for f in uploaded_files:
        if f.name.lower().endswith('.zip'): process_zip(f)
        else: xml_contents.append(f)
    return xml_contents

# --- MÓDULO SENTINELA ---
def extrair_sentinela(conteudo, chaves_vistas, cnpj_cliente):
    regs = []
    try:
        root = ET.fromstring(conteudo.read().lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None or limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text) != cnpj_cliente: return []
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        itens = []
        v_total_prod = Decimal("0")
        for det in inf.findall(f"{ns}det"):
            v_p = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            itens.append({'cfop': det.find(f"{ns}prod/{ns}CFOP").text.replace(".",""), 'valor': v_p})
            v_total_prod += v_p
        for it in itens:
            prop = it['valor'] / v_total_prod if v_total_prod > 0 else Decimal("0")
            regs.append({
                "Nota": int(inf.find(f"{ns}ide/{ns}nNF").text),
                "CFOP": it['cfop'], "ST": it['cfop'] in CFOPS_ST_SENTINELA,
                "Valor Cru": v_nf * prop, "Tipo": "SAÍDA" if inf.find(f"{ns}ide/{ns}tpNF").text == "1" else "ENTRADA"
            })
    except: pass
    return regs

# --- MÓDULO DIZIMEIRO ---
def extrair_dizimeiro(xml_io, cnpj_alvo):
    try:
        xml_str = xml_io.read().decode('utf-8', errors='ignore')
        xml_str = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', xml_str)
        root = ET.fromstring(xml_str)
        emit = buscar_tag('emit', root)
        dest = buscar_tag('dest', root)
        if limpar_cnpj(buscar_tag('CNPJ', dest).text) != cnpj_alvo: return []
        itens = []
        for det in root.findall('.//det'):
            prod = buscar_tag('prod', det)
            imp = buscar_tag('imposto', det)
            icms = list(buscar_tag('ICMS', imp))[0]
            itens.append({
                'Nota': int(buscar_tag('nNF', root).text), 'Emitente': buscar_tag('xNome', emit).text,
                'UF_Origem': buscar_tag('UF', emit).text, 'CFOP_XML': str(buscar_tag('CFOP', prod).text),
                'Base': float(buscar_tag('vProd', prod).text) + (float(buscar_tag('vIPI', imp).text) if buscar_tag('vIPI', imp) is not None else 0),
                'Origem_CST': buscar_tag('orig', icms).text if buscar_tag('orig', icms) is not None else "0",
                'V_ST_Nota': float(buscar_tag('vICMSST', icms).text) if buscar_tag('vICMSST', icms) is not None else 0
            })
        return itens
    except: return []

def calc_dizimeiro(row, regime, uf_dest):
    if row['V_ST_Nota'] > 0.1 or row['UF_Origem'] == uf_dest: return 0.0, "Isento/Retido"
    aliq_inter = 0.04 if str(row['Origem_CST']) in ['1','2','3','8'] else (0.07 if row['UF_Origem'] in SUL_SUDESTE_ORIGEM and uf_dest not in SUL_SUDESTE_ORIGEM else 0.12)
    aliq_int = ALIQUOTAS_INTERNAS[uf_dest]/100
    if regime == "Regime Normal":
        if uf_dest in ESTADOS_BASE_DUPLA:
            v_ori = round(row['Base'] * aliq_inter, 2)
            base_ch = (row['Base'] - v_ori) / (1 - aliq_int)
            return round(max(0, (base_ch * aliq_int) - v_ori), 2), "Base Dupla"
    return round(max(0, row['Base'] * (aliq_int - aliq_inter)), 2), "DIFAL/Antecipação"

# --- MAIN APP ---
def main():
    aplicar_estilo_unificado()
    
    if 'cnpj_val' not in st.session_state: st.session_state.cnpj_val = ""
    if 'rbt12_val' not in st.session_state: st.session_state.rbt12_val = ""

    with st.sidebar:
        st.markdown("<h1>🛡️ ECOSSISTEMA</h1>", unsafe_allow_html=True)
        st.session_state.cnpj_val = st.text_input("CNPJ CLIENTE", value=st.session_state.cnpj_val)
        cnpj_limpo = limpar_cnpj(st.session_state.cnpj_val)
        
        modulo = st.radio("SELECIONE O MÓDULO", ["SENTINELA (Saídas)", "DIZIMEIRO (Entradas)"])
        
        if modulo == "SENTINELA (Saídas)":
            st.session_state.rbt12_val = st.text_input("RBT12 ACUMULADO", value=st.session_state.rbt12_val)
        else:
            regime = st.selectbox("REGIME FISCAL", ["Simples Nacional", "Regime Normal"])
            uf_dest = st.selectbox("UF DESTINO", list(ALIQUOTAS_INTERNAS.keys()), index=25)

        if st.button("🧹 LIMPAR TUDO"):
            st.session_state.cnpj_val = ""; st.session_state.rbt12_val = ""; st.rerun()

    if not cnpj_limpo:
        st.info("👈 Insira o CNPJ na barra lateral para começar.")
        return

    st.markdown(f"<h2>MODO: {modulo}</h2>", unsafe_allow_html=True)
    files = st.file_uploader("UPLOAD XMLs / ZIPs", accept_multiple_files=True)

    if st.button("🚀 INICIAR APURAÇÃO DIAMANTE") and files:
        xmls = extrair_xmls_recursivo(files)
        
        if modulo == "SENTINELA (Saídas)":
            rbt12 = Decimal(st.session_state.rbt12_val.replace(".","").replace(",",".")) if st.session_state.rbt12_val else Decimal("0")
            aliq_nom, ded, p_icms = Decimal("0.073"), Decimal("5940.00"), Decimal("0.34")
            for n, i, f, nm, d, pi in TABELAS_SIMPLES:
                if rbt12 <= f: aliq_nom, ded, p_icms = nm, d, pi; break
            aliq_ef = ((rbt12 * aliq_nom) - ded) / rbt12 if rbt12 > 0 else Decimal("0.04")
            aliq_st = aliq_ef * (Decimal("1") - p_icms)
            
            regs = []
            for x in xmls: regs.extend(extrair_sentinela(x, set(), cnpj_limpo))
            if regs:
                df = pd.DataFrame(regs)
                res = df[df['Tipo'] == "SAÍDA"].groupby(['CFOP', 'ST']).agg({'Valor Cru': 'sum'}).reset_index()
                res['DAS'] = res.apply(lambda r: (r['Valor Cru'].quantize(Decimal("0.01"), ROUND_HALF_UP) * (aliq_st if r['ST'] else aliq_ef)).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)
                st.markdown(f"<h3>TOTAL DAS: R$ {res['DAS'].sum():,.2f}</h3>", unsafe_allow_html=True)
                st.table(res)
        
        else:
            regs = []
            for x in xmls: regs.extend(extrair_dizimeiro(x, cnpj_limpo))
            if regs:
                df = pd.DataFrame(regs)
                df['Recolher'], df['Analise'] = zip(*df.apply(lambda r: calc_dizimeiro(r, regime, uf_dest), axis=1))
                st.markdown(f"<h3>TOTAL DIFAL: R$ {df['Recolher'].sum():,.2f}</h3>", unsafe_allow_html=True)
                st.dataframe(df[df['Recolher'] > 0][['Nota', 'Emitente', 'Analise', 'Recolher']])

if __name__ == "__main__":
    main()
