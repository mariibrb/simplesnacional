"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo (VERSÃO INTEGRAL)
Foco: PGDAS Anexos I e II, Redução de ST, Matrioscas e Controle de Continuidade
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão de 60 casas para cálculos fiscais de alta fidelidade
getcontext().prec = 60 

# ─── REGRAS FISCAIS UNIVERSAIS ──────────────────────────────────────────────
TABELA_ANEXO_I = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3350")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]

TABELA_ANEXO_II = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.045"), Decimal("0.00"), Decimal("0.3200")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.078"), Decimal("5940.00"), Decimal("0.3200")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.10"), Decimal("13860.00"), Decimal("0.3200")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.112"), Decimal("22500.00"), Decimal("0.3200")),
]

CFOPS_INDUSTRIA = {"5101", "6101", "5103", "5105", "5401", "6401"}
CFOPS_DEVOLUCAO_VENDA = {"1201", "1202", "1411", "2201", "2202", "2411"}
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404", "1411", "2411", "5411", "6411"}

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
    </style>
""", unsafe_allow_html=True)

# ─── FUNÇÕES DE APOIO ────────────────────────────────────────────────────────

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

def extrair_dados_xml(conteudo, chaves_vistas, chaves_canceladas, cnpj_cliente):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns_nfe = "{http://www.portalfiscal.inf.br/nfe}"
        
        if "procEventoNFe" in root.tag or "eventoNFe" in root.tag:
            inf_evento = root.find(f".//{ns_nfe}infEvento")
            if inf_evento is not None:
                tp_evento = inf_evento.find(f"{ns_nfe}tpEvento").text
                if tp_evento == "110111": 
                    ch_canc = inf_evento.find(f"{ns_nfe}chNFe").text
                    chaves_canceladas.add(ch_canc)
            return []

        inf = root.find(f".//{ns_nfe}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns_nfe}emit/{ns_nfe}CNPJ").text)
        dest_node = inf.find(f"{ns_nfe}dest/{ns_nfe}CNPJ")
        dest_cnpj = limpar_cnpj(dest_node.text) if dest_node is not None else ""
        
        if cnpj_cliente and (emit_cnpj != cnpj_cliente and dest_cnpj != cnpj_cliente):
            return []
            
        ide = inf.find(f"{ns_nfe}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns_nfe}nNF").text), ide.find(f"{ns_nfe}serie").text, ide.find(f"{ns_nfe}mod").text
        tp_nf = ide.find(f"{ns_nfe}tpNF").text 

        for det in inf.findall(f"{ns_nfe}det"):
            prod = det.find(f"{ns_nfe}prod")
            v_p = Decimal(prod.find(f"{ns_nfe}vProd").text)
            
            v_desc = Decimal(prod.find(f"{ns_nfe}vDesc").text) if prod.find(f"{ns_nfe}vDesc") is not None else Decimal("0")
            v_outro = Decimal(prod.find(f"{ns_nfe}vOutro").text) if prod.find(f"{ns_nfe}vOutro") is not None else Decimal("0")
            v_frete = Decimal(prod.find(f"{ns_nfe}vFrete").text) if prod.find(f"{ns_nfe}vFrete") is not None else Decimal("0")
            
            base_item = (v_p - v_desc + v_outro + v_frete).quantize(Decimal("0.01"), ROUND_HALF_UP)
            cfop = prod.find(f"{ns_nfe}CFOP").text.replace(".", "")
            
            regs.append({
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, 
                "Anexo": "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I",
                "Valor_Produto_XML": v_p, 
                "Base_Tributavel_Item": base_item,
                "Tipo": "SAÍDA" if tp_nf == "1" else "ENTRADA",
                "Categoria": "RECEITA BRUTA" if tp_nf == "1" else ("DEVOLUÇÃO VENDA" if cfop in CFOPS_DEVOLUCAO_VENDA else "OUTROS"),
                "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

def processar_recursivo(arquivo_bytes, chaves_vistas, chaves_canceladas, cnpj_cli):
    registros = []
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for nome in z.namelist():
                content = z.read(nome)
                if nome.lower().endswith('.xml'):
                    registros.extend(extrair_dados_xml(content, chaves_vistas, chaves_canceladas, cnpj_cli))
                elif nome.lower().endswith('.zip'):
                    registros.extend(processar_recursivo(content, chaves_vistas, chaves_canceladas, cnpj_cli))
    except:
        registros.extend(extrair_dados_xml(arquivo_bytes, chaves_vistas, chaves_canceladas, cnpj_cli))
    return registros

# ─── MOTOR DE CÁLCULO E INTERFACE ────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria e Memorial")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente Auditado")
        cnpj_cli = limpar_cnpj(st.text_input("CNPJ", key=f"c_{st.session_state.reset_key}"))
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 Total", value="", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        if st.button("🗑️ Resetar Tudo"):
            st.session_state.reset_key += 1
            st.rerun()

    files = st.file_uploader("Upload XMLs/ZIPs", accept_multiple_files=True, type=["xml", "zip"], key=f"f_{st.session_state.reset_key}")

    if st.button("🚀 Iniciar Auditoria") and files:
        chaves_vistas, chaves_canceladas, regs = set(), set(), []
        for f in files:
            regs.extend(processar_recursivo(f.read(), chaves_vistas, chaves_canceladas, cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df['Cancelada'] = df['Chave'].isin(chaves_canceladas)
            df.loc[df['Cancelada'], ['Valor_Produto_XML', 'Base_Tributavel_Item']] = Decimal("0")

            # ─── RESUMO DE CONTINUIDADE (RESTAURADO) ────────────────────────
            st.subheader("📊 Resumo de Continuidade (Por Tipo e Série)")
            resumo_series = df.groupby(['Tipo', 'Modelo', 'Série']).agg(
                Nota_Inicial=('Nota', 'min'),
                Nota_Final=('Nota', 'max'),
                Qtd_Notas=('Nota', 'nunique')
            ).reset_index()
            st.table(resumo_series)

            # ─── MOTOR DE CÁLCULO FISCAL ────────────────────────────────────
            df_fiscal = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()

            def obter_aliquota(row, rbt12_val):
                tabela = TABELA_ANEXO_I if row['Anexo'] == "ANEXO I" else TABELA_ANEXO_II
                aliq_nom, deducao, p_icms = tabela[0][3], tabela[0][4], tabela[0][5]
                for _, ini, fim, nom, ded, p_ic in tabela:
                    if rbt12_val <= fim:
                        aliq_nom, deducao, p_icms = nom, ded, p_ic
                        break
                aliq_ef = ((rbt12_val * aliq_nom) - deducao) / rbt12_val if rbt12_val > 0 else aliq_nom
                return aliq_ef * (Decimal("1.0") - p_icms) if row['ST'] else aliq_ef

            resumo_cfop = df_fiscal.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({
                'Valor_Produto_XML': 'sum',
                'Base_Tributavel_Item': 'sum'
            }).reset_index()

            resumo_cfop['Base_PGDAS_Líquida'] = resumo_cfop.apply(
                lambda x: (x['Base_Tributavel_Item'] * Decimal("-1") if x['Categoria'] == "DEVOLUÇÃO VENDA" else x['Base_Tributavel_Item']).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1
            )

            resumo_cfop['Aliq_Final'] = resumo_cfop.apply(lambda x: obter_aliquota(x, rbt12), axis=1)
            resumo_cfop['DAS'] = resumo_cfop.apply(
                lambda row: (row['Base_PGDAS_Líquida'] * row['Aliq_Final']).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1
            )
            
            resumo_cfop['Alíquota (%)'] = resumo_cfop['Aliq_Final'].apply(lambda x: f"{(x*100):.13f}%")
            
            st.subheader("📑 Resumo Analítico por CFOP")
            st.table(resumo_cfop[['Anexo', 'CFOP', 'ST', 'Categoria', 'Alíquota (%)', 'Valor_Produto_XML', 'Base_PGDAS_Líquida', 'DAS']])

            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("Base PGDAS Líquida", f"R$ {resumo_cfop['Base_PGDAS_Líquida'].sum():,.2f}")
            c2.metric("Total DAS", f"R$ {resumo_cfop['DAS'].sum():,.2f}")

            st.subheader("📋 Rastreabilidade Geral")
            st.dataframe(df_fiscal[['Nota', 'Série', 'Modelo', 'CFOP', 'Valor_Produto_XML', 'Base_Tributavel_Item', 'Cancelada', 'Chave']], use_container_width=True)
        else:
            st.error("Nenhuma nota processada.")

if __name__ == "__main__":
    main()
