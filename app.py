import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
import streamlit as st
import pandas as pd

# ─── CONFIGURAÇÃO E ESTILO ───────────────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
        .memorial-box { background-color: white; padding: 25px; border-radius: 10px; border: 1px solid #d81b60; color: black; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS ──────────────────────────────────────────────────────────
TABELA_I = [
    (1, 0, 180000, 0.04, 0),
    (2, 180000.01, 360000, 0.073, 5940),
    (3, 360000.01, 720000, 0.095, 13860),
]
CFOPS_RECEITA = {"5101", "5102", "5403", "5405", "6102", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── FUNÇÕES DE INTELIGÊNCIA ─────────────────────────────────────────────────

def identificar_cancelamento(conteudo):
    try:
        root = ET.fromstring(conteudo.lstrip())
        for ev in root.iter():
            if "tpEvento" in ev.tag and ev.text == "110111":
                ch = root.find(".//{http://www.portalfiscal.inf.br/nfe}chNFe")
                return ch.text if ch is not None else None
    except: return None

def extrair_dados(conteudo, chaves_vistas, chaves_canc, cnpj_cliente):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas or chave in chaves_canc: return []
        
        emit_cnpj = inf.find(f"{ns}emit/{ns}CNPJ").text
        dest = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = dest.text if dest is not None else ""
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        tipo = inf.find(f"{ns}ide/{ns}tpNF").text 

        categoria = None
        if emit_cnpj == cnpj_cliente and tipo == "1": categoria = "RECEITA"
        elif dest_cnpj == cnpj_cliente and tipo == "0": categoria = "DEVOLUÇÃO"
        
        if categoria:
            regs.append({"Nota": n_nota, "Tipo": categoria, "Valor": v_nf, "Chave": chave})
            chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE PRINCIPAL ─────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria Final")
    
    with st.sidebar:
        st.header("👤 Identificação")
        cnpj_cli = st.text_input("CNPJ do Cliente", value="").replace(".", "").replace("/", "").replace("-", "")
        
        st.header("⚙️ Parâmetros")
        rbt12_raw = st.text_input("RBT12", value="", placeholder="Digite o valor...")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        is_st = st.toggle("Dedução ICMS ST (34%)", value=True)

    files = st.file_uploader("Arquivos XML/ZIP", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria") and cnpj_cli:
        chaves_vistas, chaves_canc, bytes_list = set(), set(), []
        
        for f in files:
            content = f.read()
            if f.name.lower().endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for n in z.namelist():
                        c = z.read(n)
                        canc = identificar_cancelamento(c)
                        if canc: chaves_canc.add(canc)
                        bytes_list.append(c)
            else:
                canc = identificar_cancelamento(content)
                if canc: chaves_canc.add(canc)
                bytes_list.append(content)

        registros = []
        for b in bytes_list:
            registros.extend(extrair_dados(b, chaves_vistas, chaves_canc, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            fat = df[df["Tipo"] == "RECEITA"]["Valor"].sum()
            dev = df[df["Tipo"] == "DEVOLUÇÃO"]["Valor"].sum()
            base = max(fat - dev, Decimal("0"))
            
            # Cálculo alíquota simples para o exemplo
            aliq = Decimal("0.04") # Simplificado para demonstração
            if is_st: aliq = aliq * Decimal("0.66")
            
            imposto = (base * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP)
            
            st.markdown("### 📊 Dashboard")
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento (vNF)", f"R$ {fat:,.2f}")
            c2.metric("Canceladas", len(chaves_canc))
            c3.metric("DAS APURADO", f"R$ {imposto:,.2f}")
            
            st.dataframe(df.sort_values("Nota"), use_container_width=True)

if __name__ == "__main__":
    main()
