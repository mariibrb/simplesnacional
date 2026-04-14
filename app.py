import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd
import re

# Precisão extrema para bater com o PGDAS (Hierarquia fiscal respeitada)
getcontext().prec = 30 

# ─── ESTILO RIHANNA / MONTSERRAT ─────────────────────────────────────────────
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

# ─── REGRAS FISCAIS UNIVERSAIS (ANEXO I - COMÉRCIO) ──────────────────────────
TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── FUNÇÕES DE AUDITORIA E PROCESSAMENTO ────────────────────────────────────

def limpar_cnpj(cnpj):
    """Remove caracteres não numéricos para comparação segura."""
    return re.sub(r'\D', '', str(cnpj))

def identificar_cancelamento(conteudo):
    """Detecta eventos de cancelamento para expurgar notas da base."""
    try:
        root = ET.fromstring(conteudo.lstrip())
        for ev in root.iter():
            if "tpEvento" in ev.tag and ev.text == "110111":
                ch = root.find(".//{http://www.portalfiscal.inf.br/nfe}chNFe")
                return ch.text if ch is not None else None
    except: return None

def extrair_dados(conteudo, chaves_vistas, chaves_canc, cnpj_cliente, uf_cliente):
    """Extrai dados com tratamento rigoroso de CNPJ e CFOP."""
    regs, difal_regs = [], []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return [], []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas or chave in chaves_canc: return [], []
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        emit_uf = inf.find(f"{ns}enderEmit/{ns}UF").text
        dest_node = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = limpar_cnpj(dest_node.text) if dest_node is not None else ""
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 

        if emit_cnpj == cnpj_cliente and tipo_op == "1":
            for det in inf.findall(f"{ns}det"):
                v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                csosn = det.find(f".//{ns}CSOSN")
                is_st = (csosn is not None and csosn.text == "500") or cfop in CFOPS_ST
                regs.append({"Nota": n_nota, "Tipo": "SAÍDA", "CFOP": cfop, "Valor": v_prod, "ST": is_st, "Chave": chave})
            chaves_vistas.add(chave)
        elif dest_cnpj == cnpj_cliente and tipo_op == "0":
            for det in inf.findall(f"{ns}det"):
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                if cfop in CFOPS_DEVOLUCAO:
                    regs.append({"Nota": n_nota, "Tipo": "DEVOLUÇÃO", "CFOP": cfop, "Valor": v_prod, "ST": False, "Chave": chave})
                elif emit_uf != uf_cliente and cfop.startswith("2"):
                    difal_regs.append({"Nota": n_nota, "Origem": emit_uf, "Valor Base": v_prod, "Chave": chave})
            chaves_vistas.add(chave)
    except: pass
    return regs, difal_regs

# ─── INTERFACE STREAMLIT ─────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria Universal")
    
    with st.sidebar:
        st.header("👤 Parâmetros da Empresa")
        cnpj_input = st.text_input("CNPJ do Cliente (Ex: 52.980.554/0001-04)")
        cnpj_cli = limpar_cnpj(cnpj_input)
        uf_cli = st.selectbox("UF do Cliente", ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "GO", "PB", "PE"])
        
        st.header("⚙️ Configurações PGDAS")
        rbt12_raw = st.text_input("RBT12 Acumulado (Ex: 504403.47)")
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

        registros, lista_difal = [], []
        for b in bytes_list:
            r, d = extrair_dados(b, chaves_vistas, chaves_canc, cnpj_cli, uf_cli)
            registros.extend(r); lista_difal.extend(d)
        
        if registros:
            df = pd.DataFrame(registros)
            
            # Cálculo de Alíquotas com Precisão de 13 casas decimais
            aliq_nom, ded, f_n, p_icms = Decimal("0.04"), Decimal("0"), 1, Decimal("0.335")
            for num, ini, fim, nom, d_val, p_val in TABELAS_SIMPLES:
                if rbt12 <= fim:
                    f_n, aliq_nom, ded, p_icms = num, nom, d_val, p_val
                    break
            
            aliq_ef = ((rbt12 * aliq_nom) - ded) / rbt12 if rbt12 > 0 else aliq_nom
            aliq_ef = aliq_ef.quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)
            aliq_st = (aliq_ef * (Decimal("1.0") - p_icms)).quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)
            
            # Totais Brutos
            fat_bruto_total = df[df['Tipo'] == "SAÍDA"]['Valor'].sum()
            val_st_total = df[df['ST'] == True]['Valor'].sum()
            
            # Resumo por CFOP com Subtração Real de Base ST da Base Normal
            resumo_cfop = []
            for cfop in df['CFOP'].unique():
                tipo = df[df['CFOP'] == cfop]['Tipo'].iloc[0]
                is_st = df[df['CFOP'] == cfop]['ST'].any()
                v_bruto = df[df['CFOP'] == cfop]['Valor'].sum()
                
                v_liq = v_bruto - val_st_total if (not is_st and tipo == "SAÍDA") else v_bruto
                aliq = aliq_st if is_st else (Decimal("0") if tipo == "DEVOLUÇÃO" else aliq_ef)
                imp = (v_liq * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP)
                
                resumo_cfop.append({
                    "CFOP": cfop, "Tipo": tipo, "ST": is_st, 
                    "Valor Bruto": v_bruto, "Base Líquida": v_liq, 
                    "Alíquota": f"{aliq*100:.13f}%", "Imposto": imp
                })

            # ─── DASHBOARD ───────────────────────────────────────────────────
            st.markdown("### 📊 Dashboard de Auditoria")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Faturamento Bruto", f"R$ {fat_bruto_total:,.2f}")
            c2.metric("Base Normal Líquida", f"R$ {fat_bruto_total - val_st_total:,.2f}")
            c3.metric("Base ICMS ST", f"R$ {val_st_total:,.2f}")
            c4.metric("DAS TOTAL", f"R$ {sum(r['Imposto'] for r in resumo_cfop):,.2f}")

            # ─── MEMORIAL DETALHADO ──────────────────────────────────────────
            st.markdown("### 📝 Memorial de Cálculo (Resumo por CFOP)")
            st.table(pd.DataFrame(resumo_cfop))
            
            if lista_difal:
                st.info(f"⚠️ **DIFAL Detectado:** R$ {pd.DataFrame(lista_difal)['Valor Base'].sum():,.2f}")

            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.error(f"❌ Nenhuma nota encontrada para o CNPJ {cnpj_cli}. Verifique os arquivos.")

if __name__ == "__main__":
    main()
