"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo (VERSÃO INTEGRAL)
Foco: PGDAS Anexos I e II, Redução de ICMS/ST, Matrioscas e Auditoria de Base por CFOP
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
        
        # Filtro Rigoroso de Identidade
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
            
            # Cálculo de Proporcionalidade Fiscal (vNF distribuído por item)
            prop = v_p / v_prod_total if v_prod_total > 0 else Decimal("0")
            valor_base_item = (v_nf * prop)

            anexo = "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I"
            
            # Classificação por Categoria
            categoria = "OUTROS"
            if tp_nf == "1":
                categoria = "RECEITA BRUTA"
            elif cfop in CFOPS_DEVOLUCAO_VENDA:
                categoria = "DEVOLUÇÃO VENDA"
            
            regs.append({
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, "Anexo": anexo,
                "Valor_Produto_XML": v_p,
                "Valor_Proporcional_NF": valor_base_item,
                "Categoria": categoria, "Chave": chave
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

# ─── INTERFACE E MOTOR DE CÁLCULO ────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria Integral")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente Auditado")
        cnpj_cli = re.sub(r'\D', '', st.text_input("CNPJ Emitente", key=f"c_{st.session_state.reset_key}"))
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 Acumulado", value="", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        if st.button("🗑️ Resetar Tudo"):
            st.session_state.reset_key += 1
            st.rerun()

    # Cálculo Antecipado de Alíquotas com Redução de ST
    aliq_ef1, p_icms1 = calcular_dados_pgdas(rbt12, TABELA_ANEXO_I)
    aliq_st1 = aliq_ef1 * (Decimal("1.0") - p_icms1)
    
    aliq_ef2, p_icms2 = calcular_dados_pgdas(rbt12, TABELA_ANEXO_II)
    aliq_st2 = aliq_ef2 * (Decimal("1.0") - p_icms2)

    files = st.file_uploader("Upload XMLs/ZIPs", accept_multiple_files=True, type=["xml", "zip"], key=f"f_{st.session_state.reset_key}")

    if st.button("🚀 Iniciar Auditoria") and files:
        chaves_vistas, regs = set(), []
        for f in files: regs.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df_fiscal = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()
            
            def aplicar_logica_fiscal(row):
                # Valor proporcional considerando frete/desconto/vNF
                base_calculo = row['Valor_Proporcional_NF'].quantize(Decimal("0.01"), ROUND_HALF_UP)
                multiplicador = Decimal("-1") if row['Categoria'] == "DEVOLUÇÃO VENDA" else Decimal("1")
                
                # Para o XML Bruto também aplicamos o sinal da devolução para bater o líquido
                xml_bruto = (row['Valor_Produto_XML'] * multiplicador).quantize(Decimal("0.01"), ROUND_HALF_UP)
                base_final = base_calculo * multiplicador
                
                # Seleção de Alíquota Específica
                if row['Anexo'] == "ANEXO I":
                    aliq = aliq_st1 if row['ST'] else aliq_ef1
                else:
                    aliq = aliq_st2 if row['ST'] else aliq_ef2
                
                return base_final, aliq, (base_final * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP), xml_bruto

            calc_data = df_fiscal.apply(aplicar_logica_fiscal, axis=1, result_type='expand')
            df_fiscal['Base_Liquida'], df_fiscal['Aliq_Final'], df_fiscal['DAS'], df_fiscal['XML_Bruto_Calc'] = calc_data[0], calc_data[1], calc_data[2], calc_data[3]

            # ─── APRESENTAÇÃO DOS DADOS ──────────────────────────────────────
            st.subheader("📊 Resumo Analítico por CFOP e Categoria")
            resumo = df_fiscal.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({
                'XML_Bruto_Calc': 'sum',
                'Base_Liquida': 'sum',
                'DAS': 'sum',
                'Aliq_Final': 'first'
            }).reset_index()
            
            resumo['Alíquota (%)'] = resumo['Aliq_Final'].apply(lambda x: f"{(x*100):.13f}%")
            
            # Renomeando para clareza na tabela
            resumo = resumo.rename(columns={'XML_Bruto_Calc': 'Faturamento XML Bruto'})
            
            res_show = resumo[['Anexo', 'CFOP', 'ST', 'Categoria', 'Alíquota (%)', 'Faturamento XML Bruto', 'Base_Liquida', 'DAS']].copy()
            res_show['ST'] = res_show['ST'].map({True: "SIM", False: "NÃO"})
            st.table(res_show)

            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento XML Bruto Total", f"R$ {df_fiscal['XML_Bruto_Calc'].sum():,.2f}")
            c2.metric("Base PGDAS (vNF Líquido)", f"R$ {df_fiscal['Base_Liquida'].sum():,.2f}")
            c3.metric("Total DAS", f"R$ {df_fiscal['DAS'].sum():,.2f}")
            
            st.subheader("📋 Rastreabilidade de Notas e Séries")
            df_saida = df[df["Categoria"] == "RECEITA BRUTA"]
            if not df_saida.empty:
                intervalos = df_saida.groupby(['Modelo', 'Série']).agg(
                    Inicio=('Nota', 'min'), Fim=('Nota', 'max'), Notas=('Nota', 'nunique')
                ).reset_index()
                st.dataframe(intervalos, hide_index=True)

            st.dataframe(df_fiscal.sort_values(["Nota"]), use_container_width=True)
        else:
            st.error("Nenhuma nota processada para o CNPJ informado.")

if __name__ == "__main__":
    main()
