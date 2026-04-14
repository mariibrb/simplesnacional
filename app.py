"""
Sentinela Ecosystem - Auditoria e Rastreabilidade
Foco: Correção de TypeError e Dashboard de Faixas Progressivas
"""

import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
import streamlit as st
import pandas as pd

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .faixa-box { background-color: white; padding: 15px; border-radius: 8px; border: 1px solid #d81b60; margin-bottom: 10px; min-height: 100px; }
        .faixa-ativa { background-color: #ffe6f0; border: 2px solid #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── TABELAS OFICIAIS ────────────────────────────────────────────────────────

TABELAS_SIMPLES = {
    "Anexo I (Comércio)": [
        (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00")),
        (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00")),
        (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00")),
        (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00")),
        (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00")),
        (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.19"), Decimal("256500.00")),
    ],
    "Anexo III (Serviços)": [
        (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.06"), Decimal("0.00")),
        (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.112"), Decimal("9360.00")),
        (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.135"), Decimal("17640.00")),
        (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.16"), Decimal("35640.00")),
        (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.21"), Decimal("125640.00")),
        (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.33"), Decimal("648000.00")),
    ]
}

CFOPS_RECEITA = {"5101", "5102", "5403", "5405", "6102", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── LÓGICA DE PROCESSAMENTO ─────────────────────────────────────────────────

def extrair_dados_xml(conteudo, nome_arquivo, chaves_vistas):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        n_nota = inf.find(f"{ns}ide/{ns}nNF").text
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 
        
        for det in inf.findall(f"{ns}det"):
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            
            categoria = None
            if tipo_op == "1" and cfop in CFOPS_RECEITA: categoria = "SAÍDA (RECEITA)"
            elif tipo_op == "0" and cfop in CFOPS_DEVOLUCAO: categoria = "ENTRADA (DEVOLUÇÃO)"
                
            if categoria:
                regs.append({
                    "Nota": n_nota,
                    "CFOP": cfop,
                    "Tipo": categoria,
                    "Valor (R$)": v_prod,
                    "Chave de Acesso": chave,
                    "Arquivo Original": nome_arquivo
                })
        chaves_vistas.add(chave)
    except: pass
    return regs

def ceifador_zip(zip_bytes, chaves_vistas):
    all_regs = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            content = z.read(name)
            if name.lower().endswith('.zip'): 
                all_regs.extend(ceifador_zip(content, chaves_vistas))
            elif name.lower().endswith('.xml'): 
                all_regs.extend(extrair_dados_xml(content, name, chaves_vistas))
    return all_regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria e Rastreabilidade")
    
    with st.sidebar:
        st.header("1. Parâmetros PGDAS")
        rbt12_input = st.text_input("RBT12 (Acumulado 12 meses)", value="0,00")
        try:
            rbt12 = Decimal(rbt12_input.replace(".", "").replace(",", "."))
        except: rbt12 = Decimal("0.00")
        
        nome_anexo = st.selectbox("Anexo Principal", options=list(TABELAS_SIMPLES.keys()))
        
        # Identificar Faixa Ativa e Alíquota
        faixa_ativa_num = 1
        aliq_efetiva = Decimal("0.00")
        for num, inicio, fim, aliq_nom, deducao in TABELAS_SIMPLES[nome_anexo]:
            if rbt12 <= fim:
                faixa_ativa_num = num
                if rbt12 > 0:
                    aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
                else:
                    aliq_efetiva = aliq_nom # Primeira faixa
                break
        
        aliq_efetiva = max(aliq_efetiva, Decimal("0.00")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        st.metric("Alíquota Efetiva", f"{(aliq_efetiva * 100):.4f} %")

    st.subheader("2. Upload de Arquivos")
    files = st.file_uploader("Arraste XMLs ou ZIPs Matrioskas", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria") and files:
        chaves_vistas = set()
        dados_fiscais = []
        
        for f in files:
            content = f.read()
            if f.name.lower().endswith('.zip'):
                dados_fiscais.extend(ceifador_zip(content, chaves_vistas))
            else:
                dados_fiscais.extend(extrair_dados_xml(content, f.name, chaves_vistas))
        
        if not dados_fiscais:
            st.error("Nenhuma nota fiscal relevante encontrada nos arquivos.")
            return

        df = pd.DataFrame(dados_fiscais)
        saidas = df[df["Tipo"] == "SAÍDA (RECEITA)"]["Valor (R$)"].sum()
        devolucoes = df[df["Tipo"] == "ENTRADA (DEVOLUÇÃO)"]["Valor (R$)"].sum()
        base_liq = max(saidas - devolucoes, Decimal("0.00"))
        imposto = (base_liq * aliq_efetiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # ─── DASHBOARD DE FAIXAS ─────────────────────────────────────────────
        st.markdown("### 📈 Faixas de Faturamento (Simples Nacional)")
        cols_faixas = st.columns(6)
        for i, (num, inicio, fim, aliq_nom, deducao) in enumerate(TABELAS_SIMPLES[nome_anexo]):
            com_estilo = "faixa-ativa" if num == faixa_ativa_num else ""
            with cols_faixas[i]:
                st.markdown(f"""
                <div class="faixa-box {com_estilo}">
                    <center>
                    <small>Faixa {num}</small><br>
                    <b>Até {fim/1000:,.0f}k</b><br>
                    <small>{aliq_nom*100}%</small>
                    </center>
                </div>
                """, unsafe_allow_html=True)

        # ─── RESULTADOS PRINCIPAIS ──────────────────────────────────────────
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Faturamento XML", f"R$ {saidas:,.2f}")
        c2.metric("Devoluções XML", f"R$ {devolucoes:,.2f}")
        c3.metric("Base Líquida", f"R$ {base_liq:,.2f}")
        c4.metric("IMPOSTO CALCULADO", f"R$ {imposto:,.2f}")

        # ─── LISTAGEM ANALÍTICA ─────────────────────────────────────────────
        st.markdown("### 📋 Rastreabilidade nota a nota")
        df_display = df[["Nota", "CFOP", "Tipo", "Valor (R$)", "Chave de Acesso"]]
        st.dataframe(df_display, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
