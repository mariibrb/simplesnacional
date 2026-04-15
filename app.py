"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Versão: 3.0 - Rigor Total em Segregação de ST e Redução de Base
Foco: Anexo I e II, Redução de ICMS/ST, Matrioscas e Devoluções
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão de 60 casas decimais para bater com os centavos do PGDAS
getcontext().prec = 60 

# ─── REGRAS FISCAIS UNIVERSAIS ──────────────────────────────────────────────
# ANEXO I - COMÉRCIO (Partilha ICMS: 33,5%)
TABELA_ANEXO_I = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3350")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]

# ANEXO II - INDÚSTRIA (Partilha ICMS: 32,0%)
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

def calcular_dados_pgdas(rbt12, tabela):
    aliq_nom, deducao, p_icms = tabela[0][3], tabela[0][4], tabela[0][5]
    for _, ini, fim, nom, ded, p_ic in tabela:
        if rbt12 <= fim:
            aliq_nom, deducao, p_icms = nom, ded, p_ic
            break
    aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12 if rbt12 > 0 else aliq_nom
    return aliq_efetiva, p_icms

def extrair_dados_xml(conteudo, chaves_vistas, cnpj_cliente):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        emit_cnpj = re.sub(r'\D', '', inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_node = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = re.sub(r'\D', '', dest_node.text) if dest_node is not None else ""
        
        if cnpj_cliente and (emit_cnpj != cnpj_cliente and dest_cnpj != cnpj_cliente):
            return []
            
        ide = inf.find(f"{ns}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns}nNF").text), ide.find(f"{ns}serie").text, ide.find(f"{ns}mod").text
        tp_nf, v_nf = ide.find(f"{ns}tpNF").text, Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)

        dets = inf.findall(f"{ns}det")
        v_prod_total = sum(Decimal(d.find(f"{ns}prod/{ns}vProd").text) for d in dets)

        for det in dets:
            v_p = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            prop = v_p / v_prod_total if v_prod_total > 0 else Decimal("0")
            
            anexo = "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I"
            is_st = cfop in CFOPS_ST
            
            categoria = "OUTROS"
            if tp_nf == "1":
                categoria = "RECEITA BRUTA"
            elif cfop in CFOPS_DEVOLUCAO_VENDA:
                categoria = "DEVOLUÇÃO VENDA"
            
            regs.append({
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": is_st, "Anexo": anexo,
                "Valor Cru": v_nf * prop, "Categoria": categoria, "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

def processar_recursivo(arquivo_bytes, chaves_vistas, cnpj_cli):
    registros = []
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for nome in z.namelist():
                if nome.lower().endswith('.xml'):
                    with z.open(nome) as f: registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
                elif nome.lower().endswith('.zip'):
                    with z.open(nome) as f: registros.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
    except: registros.extend(extrair_dados_xml(arquivo_bytes, chaves_vistas, cnpj_cli))
    return registros

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria PGDAS (Full)")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_cli = re.sub(r'\D', '', st.text_input("CNPJ Emitente", key=f"c_{st.session_state.reset_key}"))
        st.header("⚙️ Parâmetros")
        rbt12_raw = st.text_input("RBT12 Acumulado", value="", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        if st.button("🗑️ Resetar Sistema"):
            st.session_state.reset_key += 1
            st.rerun()

    # Cálculo Antecipado das Alíquotas por Anexo (Com Redução ST Embutida na Lógica)
    aliq_ef1, p_icms1 = calcular_dados_pgdas(rbt12, TABELA_ANEXO_I)
    aliq_st1 = aliq_ef1 * (Decimal("1.0") - p_icms1)
    
    aliq_ef2, p_icms2 = calcular_dados_pgdas(rbt12, TABELA_ANEXO_II)
    aliq_st2 = aliq_ef2 * (Decimal("1.0") - p_icms2)

    files = st.file_uploader("Upload XMLs/ZIPs", accept_multiple_files=True, type=["xml", "zip"], key=f"f_{st.session_state.reset_key}")

    if st.button("🚀 Executar Auditoria") and files:
        chaves_vistas, regs = set(), []
        for f in files: regs.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df_fiscal = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()
            
            def processar_fiscal_linha(row):
                base_bruta = row['Valor Cru'].quantize(Decimal("0.01"), ROUND_HALF_UP)
                multiplicador = Decimal("-1") if row['Categoria'] == "DEVOLUÇÃO VENDA" else Decimal("1")
                base_final = base_bruta * multiplicador
                
                # Seleção Rigorosa da Alíquota (Com Redução se ST)
                if row['Anexo'] == "ANEXO I":
                    aliq = aliq_st1 if row['ST'] else aliq_ef1
                else:
                    aliq = aliq_st2 if row['ST'] else aliq_ef2
                
                return base_final, aliq, (base_final * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP)

            calc_data = df_fiscal.apply(processar_fiscal_linha, axis=1, result_type='expand')
            df_fiscal['Base_Calculo'], df_fiscal['Aliq_Final'], df_fiscal['DAS_Item'] = calc_data[0], calc_data[1], calc_data[2]

            st.markdown("### 📑 Memorial Detalhado: Segregação e Redução de ST")
            
            # Tabela de Resumo por CFOP
            resumo = df_fiscal.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({
                'Base_Calculo': 'sum', 
                'DAS_Item': 'sum', 
                'Aliq_Final': 'first'
            }).reset_index()
            
            resumo['Alíquota (%)'] = resumo['Aliq_Final'].apply(lambda x: f"{(x*100):.13f}%")
            
            # Exibição organizada
            tab_show = resumo[['Anexo', 'CFOP', 'ST', 'Categoria', 'Alíquota (%)', 'Base_Calculo', 'DAS_Item']].copy()
            tab_show['ST'] = tab_show['ST'].map({True: "SIM (ICMS Retido)", False: "NÃO (Integral)"})
            st.table(tab_show)

            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("Base de Cálculo Total (Líquida)", f"R$ {df_fiscal['Base_Calculo'].sum():,.2f}")
            c2.metric("Total DAS Gerado", f"R$ {df_fiscal['DAS_Item'].sum():,.2f}")
            
            st.markdown("### 📋 Rastreabilidade de Itens (Conferência Unitária)")
            st.dataframe(df_fiscal.sort_values(["Anexo", "Nota"]), use_container_width=True)
        else:
            st.error("Nenhum dado válido encontrado para o CNPJ e arquivos enviados.")

if __name__ == "__main__":
    main()
