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
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS (ANEXO I) ────────────────────────────────────────────────
TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
]
PERC_ICMS_ANEXO_I = Decimal("0.34")
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── FUNÇÕES DE PROCESSAMENTO ────────────────────────────────────────────────

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
        if emit_cnpj == cnpj_cliente and tipo == "1":
            categoria = "RECEITA"
        elif dest_cnpj == cnpj_cliente and tipo == "0":
            for det in inf.findall(f"{ns}det"):
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                if cfop in CFOPS_DEVOLUCAO:
                    categoria = "DEVOLUÇÃO"
                    break
        
        if categoria:
            regs.append({"Nota": n_nota, "Tipo": categoria, "Valor": v_nf, "Chave": chave})
            chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Memorial e Sequencial")
    
    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_cli = st.text_input("CNPJ (apenas números)").replace(".", "").replace("/", "").replace("-", "")
        
        st.header("⚙️ PGDAS")
        rbt12_raw = st.text_input("RBT12", value="0,00")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", "."))
        is_st = st.toggle("Dedução ICMS ST (34%)", value=False)

    files = st.file_uploader("Arquivos XML/ZIP", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Gerar Auditoria") and cnpj_cli:
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

        registros = []
        for b in bytes_list:
            registros.extend(extrair_dados(b, chaves_vistas, chaves_canc, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            fat = df[df["Tipo"] == "RECEITA"]["Valor"].sum()
            dev = df[df["Tipo"] == "DEVOLUÇÃO"]["Valor"].sum()
            base = max(fat - dev, Decimal("0"))
            
            # 1. Alíquota Efetiva
            aliq_nom, deducao, faixa = Decimal("0.04"), Decimal("0"), 1
            for f_n, ini, fim, nom, ded in TABELAS_SIMPLES:
                if rbt12 <= fim:
                    faixa, aliq_nom, deducao = f_n, nom, ded
                    break
            
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12 if rbt12 > 0 else aliq_nom
            if is_st: aliq_efetiva = aliq_efetiva * (Decimal("1.0") - PERC_ICMS_ANEXO_I)
            
            aliq_efetiva = aliq_efetiva.quantize(Decimal("0.000001"), ROUND_HALF_UP)
            imposto = (base * aliq_efetiva).quantize(Decimal("0.01"), ROUND_HALF_UP)

            # DASHBOARD
            st.markdown("### 📊 Dashboard de Conferência")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Nota Inicial", df["Nota"].min())
            c2.metric("Nota Final", df["Nota"].max())
            c3.metric("Faturamento Líquido", f"R$ {base:,.2f}")
            c4.metric("DAS Calculado", f"R$ {imposto:,.2f}")

            # MEMORIAL DE CÁLCULO
            st.markdown("### 📝 Memorial de Cálculo Detalhado")
            st.markdown(f"""
            <div class="memorial-box">
                <b>PASSO 1: ALÍQUOTA (FAIXA {faixa})</b><br>
                • RBT12 Informado: R$ {rbt12:,.2f}<br>
                • Alíquota Nominal: {aliq_nom*100}% | Parcela a Deduzir: R$ {deducao:,.2f}<br>
                • Alíquota Efetiva: (({rbt12} * {aliq_nom}) - {deducao}) / {rbt12} = <b>{aliq_efetiva*100:.4f}%</b> {'(Com abatimento ST)' if is_st else ''}<br><br>
                
                <b>PASSO 2: BASE DE CÁLCULO</b><br>
                • Faturamento Bruto (Saídas): R$ {fat:,.2f}<br>
                • Devoluções (Entradas): R$ {dev:,.2f}<br>
                • <b>Base de Cálculo Líquida: R$ {base:,.2f}</b><br><br>
                
                <b>PASSO 3: RESULTADO FINAL</b><br>
                • R$ {base:,.2f} * {aliq_efetiva*100:.4f}% = <span class="highlight" style="font-size: 1.2em;">R$ {imposto:,.2f}</span>
            </div>
            """, unsafe_allow_html=True)

            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
