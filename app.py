import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
import streamlit as st
import pandas as pd

# ─── ESTILO E CONFIGURAÇÃO ───────────────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
        .memorial-box { background-color: white; padding: 25px; border-radius: 10px; border: 1px solid #d81b60; color: black; line-height: 1.6; }
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS ──────────────────────────────────────────────────────────
# Percentual de ICMS na repartição (Anexo I - Comércio)
PERC_ICMS_ANEXO_I = Decimal("0.34")

# ─── FUNÇÕES DE AUDITORIA ────────────────────────────────────────────────────

def extrair_dados_analiticos(conteudo, chaves_vistas, chaves_canc, cnpj_cliente):
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

        v_item_normal = Decimal("0")
        v_item_st = Decimal("0")
        v_total_dev = Decimal("0")
        
        # 1. SAÍDAS - SEGREGAÇÃO POR ITEM (CST/CSOSN)
        if emit_cnpj == cnpj_cliente and tipo_op == "1":
            for det in inf.findall(f"{ns}det"):
                v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                # Verifica CSOSN (Simples Nacional)
                csosn = det.find(f".//{ns}CSOSN")
                # CSOSN 500 = ICMS cobrado anteriormente por ST
                if csosn is not None and csosn.text == "500":
                    v_item_st += v_prod
                else:
                    v_item_normal += v_prod
            
            regs.append({
                "Nota": n_nota, "Tipo": "SAÍDA", 
                "Normal": v_item_normal, "ST": v_item_st, 
                "Devolucao": Decimal("0"), "Chave": chave
            })
            chaves_vistas.add(chave)

        # 2. ENTRADAS - DEVOLUÇÕES
        elif dest_cnpj == cnpj_cliente and tipo_op == "0":
            v_total_dev = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vProd").text)
            regs.append({
                "Nota": n_nota, "Tipo": "DEVOLUÇÃO", 
                "Normal": Decimal("0"), "ST": Decimal("0"), 
                "Devolucao": v_total_dev, "Chave": chave
            })
            chaves_vistas.add(chave)
                
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria de Precisão")
    
    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_input = st.text_input("CNPJ do Cliente")
        cnpj_cli = "".join(filter(str.isdigit, cnpj_input))
        
        st.header("⚙️ PGDAS")
        rbt12_raw = st.text_input("RBT12 Acumulado")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")

    files = st.file_uploader("Upload de Notas", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Auditar Lote") and cnpj_cli:
        chaves_vistas, chaves_canc, bytes_list = set(), set(), []
        # (Lógica de unificação de arquivos e identificação de canceladas mantida)
        # ...
        
        registros = [] # (Simulação de preenchimento após leitura dos arquivos)
        # registros = extrair_dados_analiticos(...)

        if registros:
            df = pd.DataFrame(registros)
            rec_normal = df["Normal"].sum()
            rec_st = df["ST"].sum()
            devolucoes = df["Devolucao"].sum()
            
            # Alíquota Efetiva (Faixa 2 como exemplo)
            aliq_efetiva = Decimal("0.0498") # Exemplo de alíquota calculada
            aliq_st = (aliq_efetiva * (Decimal("1.0") - PERC_ICMS_ANEXO_I)).quantize(Decimal("0.000001"), ROUND_HALF_UP)
            
            das_normal = (max(rec_normal - devolucoes, Decimal("0")) * aliq_efetiva).quantize(Decimal("0.01"), ROUND_HALF_UP)
            das_st = (rec_st * aliq_st).quantize(Decimal("0.01"), ROUND_HALF_UP)
            total_guia = das_normal + das_st

            st.markdown("### 📊 Dashboard de Precisão")
            c1, c2, c3 = st.columns(3)
            c1.metric("Receita Tributada (ICMS Cheio)", f"R$ {rec_normal:,.2f}")
            c2.metric("Receita ST (ICMS Zerado)", f"R$ {rec_st:,.2f}")
            c3.metric("VALOR DAS", f"R$ {total_guia:,.2f}")

            st.markdown("### 📝 Memorial de Cálculo")
            st.markdown(f"""
            <div class="memorial-box">
                <b>Segregação de Receitas:</b><br>
                • Base ICMS Normal: R$ {rec_normal:,.2f} x {aliq_efetiva*100:.4f}% = R$ {das_normal:,.2f}<br>
                • Base ICMS ST: R$ {rec_st:,.2f} x {aliq_st*100:.4f}% = R$ {das_st:,.2f}<br>
                • <b>Total DAS: <span class="highlight">R$ {total_guia:,.2f}</span></b>
            </div>
            """, unsafe_allow_html=True)
            
            st.dataframe(df.sort_values("Nota"), use_container_width=True)

if __name__ == "__main__":
    main()
