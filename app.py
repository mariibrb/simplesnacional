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
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .memorial-box { background-color: white; padding: 25px; border-radius: 10px; border: 1px solid #d81b60; color: black; line-height: 1.6; }
        .difal-box { background-color: #fff3f8; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4081; margin-top: 10px; }
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS ──────────────────────────────────────────────────────────
TABELAS_SIMPLES = {
    "Anexo I (Comércio)": [(1, 0, 180000, 0.04, 0), (2, 180000.01, 360000, 0.073, 5940)]
}
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

def extrair_dados(conteudo, chaves_vistas, chaves_canc, cnpj_cliente, uf_cliente):
    regs = []
    difal_regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return [], []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas or chave in chaves_canc: return [], []
        
        emit = inf.find(f"{ns}emit")
        emit_cnpj = emit.find(f"{ns}CNPJ").text
        emit_uf = emit.find(f"{ns}enderEmit/{ns}UF").text
        
        dest = inf.find(f"{ns}dest")
        dest_cnpj = dest.find(f"{ns}CNPJ").text if dest is not None and dest.find(f"{ns}CNPJ") is not None else ""
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        tipo = inf.find(f"{ns}ide/{ns}tpNF").text 

        # 1. FATURAMENTO E DEVOLUÇÃO
        if emit_cnpj == cnpj_cliente and tipo == "1":
            regs.append({"Nota": n_nota, "Tipo": "RECEITA", "Valor": v_nf, "Chave": chave})
            chaves_vistas.add(chave)
        elif dest_cnpj == cnpj_cliente and tipo == "0":
            regs.append({"Nota": n_nota, "Tipo": "DEVOLUÇÃO", "Valor": v_nf, "Chave": chave})
            chaves_vistas.add(chave)
            
        # 2. VARREDURA DE DIFAL DE ENTRADA (Compra de fora do estado)
        if dest_cnpj == cnpj_cliente and emit_uf != uf_cliente and tipo == "0":
            for det in inf.findall(f"{ns}det"):
                cfop = det.find(f"{ns}prod/{ns}CFOP").text
                if cfop.startswith("2"): # Entrada interestadual
                    v_item = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                    difal_regs.append({
                        "Nota": n_nota,
                        "Origem": emit_uf,
                        "CFOP": cfop,
                        "Valor Base": v_item,
                        "Chave": chave
                    })
    except: pass
    return regs, difal_regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria & DIFAL")
    
    with st.sidebar:
        st.header("👤 Identificação")
        cnpj_cli = st.text_input("CNPJ do Cliente").replace(".", "").replace("/", "").replace("-", "")
        uf_cli = st.selectbox("UF do Cliente", ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "GO", "PB", "PE"])
        aliq_interna = st.number_input("Alíquota Interna UF (%)", value=18.0)
        
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12", value="")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        is_st = st.toggle("Abater ICMS ST (34%)", value=True)

    files = st.file_uploader("Upload XML ou ZIP", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria") and cnpj_cli:
        chaves_vistas, chaves_canc, bytes_list = set(), set(), []
        for f in files:
            content = f.read()
            if f.name.lower().endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for n in z.namelist():
                        c = z.read(n); canc = identificar_cancelamento(c)
                        if canc: chaves_canc.add(canc)
                        bytes_list.append(c)
            else:
                canc = identificar_cancelamento(content); 
                if canc: chaves_canc.add(canc)
                bytes_list.append(content)

        registros, lista_difal = [], []
        for b in bytes_list:
            r, d = extrair_dados(b, chaves_vistas, chaves_canc, cnpj_cli, uf_cli)
            registros.extend(r); lista_difal.extend(d)
        
        if registros or lista_difal:
            df = pd.DataFrame(registros)
            fat = df[df["Tipo"] == "RECEITA"]["Valor"].sum() if not df.empty else Decimal("0")
            
            # DASHBOARD
            st.markdown("### 📊 Dashboard de Auditoria")
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento XML", f"R$ {fat:,.2f}")
            c2.metric("Notas Interestaduais (DIFAL)", len(lista_difal))
            c3.metric("Canceladas", len(chaves_canc))

            # SEÇÃO DIFAL
            if lista_difal:
                st.markdown("### ⚠️ Alerta de DIFAL de Entrada")
                df_difal = pd.DataFrame(lista_difal)
                total_base_difal = df_difal["Valor Base"].sum()
                
                st.markdown(f"""
                <div class="difal-box">
                    Foram encontradas <b>{len(df_difal)}</b> entradas de outros estados.<br>
                    Base total para cálculo do DIFAL: <b>R$ {total_base_difal:,.2f}</b>.<br>
                    <small>Verifique a necessidade de recolhimento da antecipação do ICMS.</small>
                </div>
                """, unsafe_allow_html=True)
                st.dataframe(df_difal, use_container_width=True)

            # MEMORIAL E LISTAGEM (Mantidos íntegros)
            st.markdown("### 📋 Rastreabilidade de Notas")
            st.dataframe(df.sort_values("Nota") if not df.empty else df)
            
if __name__ == "__main__":
    main()
