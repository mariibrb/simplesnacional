import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
import streamlit as st
import pandas as pd

# ─── CONFIGURAÇÃO E ESTILO (Rihanna / Montserrat) ───────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .memorial-box { background-color: white; padding: 25px; border-radius: 10px; border: 1px solid #d81b60; color: black; line-height: 1.6; }
        .difal-box { background-color: #fff3f8; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4081; margin-top: 10px; color: #4a0024; }
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS ──────────────────────────────────────────────────────────
TABELAS_SIMPLES = {
    "Anexo I (Comércio)": [
        (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
        (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
        (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
        (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
    ]
}
PERC_ICMS_ANEXO_I = Decimal("0.34")
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
    regs, difal_regs = [], []
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

        # 1. FATURAMENTO E DEVOLUÇÃO (Baseado no CNPJ do Cliente)
        if emit_cnpj == cnpj_cliente and tipo == "1":
            regs.append({"Nota": n_nota, "Tipo": "RECEITA", "Valor": v_nf, "Chave": chave})
            chaves_vistas.add(chave)
        elif dest_cnpj == cnpj_cliente and tipo == "0":
            # Verifica se algum item é devolução
            for det in inf.findall(f"{ns}det"):
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                if cfop in CFOPS_DEVOLUCAO:
                    regs.append({"Nota": n_nota, "Tipo": "DEVOLUÇÃO", "Valor": v_nf, "Chave": chave})
                    chaves_vistas.add(chave)
                    break
            
        # 2. VARREDURA DE DIFAL DE ENTRADA (Interestadual)
        if dest_cnpj == cnpj_cliente and emit_uf != uf_cliente and tipo == "0":
            for det in inf.findall(f"{ns}det"):
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                if cfop.startswith("2"):
                    v_item = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                    difal_regs.append({"Nota": n_nota, "Origem": emit_uf, "Valor Base": v_item, "Chave": chave})
                    break
    except: pass
    return regs, difal_regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Nova Apuração")
    
    with st.sidebar:
        st.header("👤 Identificação")
        cnpj_input = st.text_input("CNPJ do Cliente (Apenas números)", value="")
        cnpj_cli = "".join(filter(str.isdigit, cnpj_input))
        uf_cli = st.selectbox("UF do Cliente", ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "GO", "PB", "PE"])
        
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 (Acumulado)", value="", placeholder="Ex: 250000.00")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        is_st = st.toggle("Abater ICMS ST (34%)", value=False)

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
                canc = identificar_cancelamento(content)
                if canc: chaves_canc.add(canc)
                bytes_list.append(content)

        registros, lista_difal = [], []
        for b in bytes_list:
            r, d = extrair_dados(b, chaves_vistas, chaves_canc, cnpj_cli, uf_cli)
            registros.extend(r); lista_difal.extend(d)
        
        if registros or lista_difal:
            df = pd.DataFrame(registros)
            fat = df[df["Tipo"] == "RECEITA"]["Valor"].sum() if not df.empty else Decimal("0")
            dev = df[df["Tipo"] == "DEVOLUÇÃO"]["Valor"].sum() if not df.empty else Decimal("0")
            base = max(fat - dev, Decimal("0"))
            
            # Cálculo Alíquota
            aliq_nom, deducao, faixa_n = Decimal("0.04"), Decimal("0"), 1
            for num, ini, fim, nom, ded in TABELAS_SIMPLES["Anexo I (Comércio)"]:
                if rbt12 <= fim:
                    faixa_n, aliq_nom, deducao = num, nom, ded
                    break
            
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12 if rbt12 > 0 else aliq_nom
            if is_st: aliq_efetiva = aliq_efetiva * (Decimal("1.0") - PERC_ICMS_ANEXO_I)
            
            aliq_efetiva = aliq_efetiva.quantize(Decimal("0.000001"), ROUND_HALF_UP)
            imposto = (base * aliq_efetiva).quantize(Decimal("0.01"), ROUND_HALF_UP)

            # 1. DASHBOARD PRINCIPAL
            st.markdown("### 📊 Dashboard de Auditoria")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Faixa de Notas", f"{df['Nota'].min()} a {df['Nota'].max()}" if not df.empty else "N/A")
            c2.metric("Faturamento (vNF)", f"R$ {fat:,.2f}")
            c3.metric("Canceladas", len(chaves_canc))
            c4.metric("DAS APURADO", f"R$ {imposto:,.2f}")

            # 2. SEÇÃO DIFAL
            if lista_difal:
                st.markdown("### ⚠️ Varredura de DIFAL de Entrada")
                df_difal = pd.DataFrame(lista_difal)
                st.markdown(f'<div class="difal-box">Base total DIFAL: <b>R$ {df_difal["Valor Base"].sum():,.2f}</b></div>', unsafe_allow_html=True)
                st.dataframe(df_difal, use_container_width=True, hide_index=True)

            # 3. MEMORIAL
            st.markdown("### 📝 Memorial de Cálculo")
            st.markdown(f"""
            <div class="memorial-box">
                <b>Alíquota Faixa {faixa_n}:</b> {aliq_efetiva*100:.4f}% | <b>Base Líquida:</b> R$ {base:,.2f}<br>
                <b>Cálculo:</b> R$ {base:,.2f} x {aliq_efetiva*100:.4f}% = <span class="highlight">R$ {imposto:,.2f}</span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ Nenhuma nota autorizada vinculada a este CNPJ foi encontrada.")

if __name__ == "__main__":
    main()
