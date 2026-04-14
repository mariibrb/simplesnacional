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

# ─── REGRAS FISCAIS UNIVERSAIS (ANEXO I) ─────────────────────────────────────
TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]

CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── FUNÇÕES DE AUDITORIA ────────────────────────────────────────────────────

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
        dest_cnpj = dest.text if dest is not None and dest.find(f"{ns}CNPJ") is not None else ""
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 

        v_normal, v_st, v_dev = Decimal("0"), Decimal("0"), Decimal("0")
        
        if emit_cnpj == cnpj_cliente and tipo_op == "1":
            for det in inf.findall(f"{ns}det"):
                v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                csosn = det.find(f".//{ns}CSOSN")
                if (csosn is not None and csosn.text == "500") or cfop in CFOPS_ST:
                    v_st += v_prod
                else:
                    v_normal += v_prod
            regs.append({"Nota": n_nota, "Tipo": "SAÍDA", "Normal": v_normal, "ST": v_st, "Dev": Decimal("0"), "Chave": chave})
            chaves_vistas.add(chave)
        elif dest_cnpj == cnpj_cliente and tipo_op == "0":
            for det in inf.findall(f"{ns}det"):
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                if cfop in CFOPS_DEVOLUCAO:
                    v_dev += Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            if v_dev > 0:
                regs.append({"Nota": n_nota, "Tipo": "DEVOLUÇÃO", "Normal": Decimal("0"), "ST": Decimal("0"), "Dev": v_dev, "Chave": chave})
                chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria Universal")
    
    with st.sidebar:
        st.header("👤 Novo Cliente")
        cnpj_input = st.text_input("CNPJ do Cliente (Auditoria Atual)")
        cnpj_cli = "".join(filter(str.isdigit, cnpj_input))
        
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 Acumulado", value="")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")

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

        registros = []
        for b in bytes_list:
            registros.extend(extrair_dados(b, chaves_vistas, chaves_canc, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            t_norm = df["Normal"].sum(); t_st = df["ST"].sum(); t_dev = df["Dev"].sum()
            
            # Cálculo Alíquota
            aliq_nom, ded, f_n, p_icms = Decimal("0.04"), Decimal("0"), 1, Decimal("0.335")
            for num, ini, fim, nom, d_val, p_val in TABELAS_SIMPLES:
                if rbt12 <= fim:
                    f_n, aliq_nom, ded, p_icms = num, nom, d_val, p_val
                    break
            
            aliq_ef = ((rbt12 * aliq_nom) - ded) / rbt12 if rbt12 > 0 else aliq_nom
            aliq_st = (aliq_ef * (Decimal("1.0") - p_icms)).quantize(Decimal("0.000001"), ROUND_HALF_UP)
            
            imp_norm = (max(t_norm - t_dev, Decimal("0")) * aliq_ef).quantize(Decimal("0.01"), ROUND_HALF_UP)
            imp_st = (t_st * aliq_st).quantize(Decimal("0.01"), ROUND_HALF_UP)
            
            st.markdown("### 📊 Dashboard Analítico")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Faixa de Notas", f"{df['Nota'].min()} a {df['Nota'].max()}")
            c2.metric("Receita Normal", f"R$ {t_norm:,.2f}")
            c3.metric("Receita ST", f"R$ {t_st:,.2f}")
            c4.metric("DAS TOTAL", f"R$ {imp_norm + imp_st:,.2f}")

            st.markdown("### 📝 Memorial de Cálculo Detalhado")
            st.markdown(f"""
            <div class="memorial-box">
                <b>1. ALÍQUOTA (FAIXA {f_n}):</b><br>
                • Efetiva Cheia: {aliq_ef*100:.4f}% | Efetiva c/ Abatimento ST: {aliq_st*100:.4f}%<br><br>
                <b>2. RESUMO POR TIPO DE RECEITA:</b><br>
                • Normal (vNF): (R$ {t_norm:,.2f} - R$ {t_dev:,.2f} dev) * {aliq_ef*100:.4f}% = R$ {imp_norm:,.2f}<br>
                • ST (vNF): R$ {t_st:,.2f} * {aliq_st*100:.4f}% = R$ {imp_st:,.2f}<br>
                • <b>TOTAL DAS APURADO: <span class="highlight">R$ {imp_norm + imp_st:,.2f}</span></b>
            </div>
            """, unsafe_allow_html=True)
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ Nenhuma nota autorizada para este CNPJ encontrada.")

if __name__ == "__main__":
    main()
